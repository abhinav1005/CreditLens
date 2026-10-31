"""PII redaction with Presidio plus custom recognizers.

Detected values are replaced with typed, numbered placeholders (<SSN_1>, <EMAIL_1>, ...).
The same value always gets the same placeholder within a conversation, so the model can
still say "the SSN you shared". The original values are never stored or logged: the
value→placeholder map lives only in the request's memory.

Presidio covers emails, Luhn-valid card numbers, SSNs, phone numbers and person names (via the small
spaCy English model). Custom recognizers cover what matters here and Presidio would miss or
over-match: fake-but-realistic SSNs and 555 phone numbers, street addresses, long account
or routing numbers, and dates of birth (a date counts only when a word like "born" or
"DOB" is near it, so "my score in March 2026" is left alone).

Allowed on purpose: masked account numbers (****4821), and the synthetic creditor names
(so "my Northwind Bank card" isn't redacted as a person's name).
"""

import logging
import re
from functools import lru_cache

from credit.generate import CARD_ISSUERS, LOAN_LENDERS
from guardrails.base import GuardrailResult, passed

logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

PLACEHOLDER_TYPE = {
    "US_SSN": "SSN",
    "FAKE_SSN": "SSN",
    "CREDIT_CARD": "CARD_NUMBER",
    "CARD_LIKE": "CARD_NUMBER",
    "ACCOUNT_NUMBER": "ACCOUNT_NUMBER",
    "PHONE_NUMBER": "PHONE",
    "US_PHONE": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "DATE_OF_BIRTH": "DOB",
    "STREET_ADDRESS": "ADDRESS",
    "PERSON": "NAME",
}
INPUT_ENTITIES = sorted(PLACEHOLDER_TYPE)
# In replies, person-name detection is off: replies name creditors and accounts, and the
# small NER model would mangle them. Everything structured is still caught.
OUTPUT_ENTITIES = [e for e in INPUT_ENTITIES if e != "PERSON"]
SCORE_THRESHOLD = 0.5
ALLOWED_NAMES = set(CARD_ISSUERS) | {n for names in LOAN_LENDERS.values() for n in names}
PLACEHOLDER = re.compile(r"<[A-Z_]+_\d+>")


@lru_cache(maxsize=1)
def analyzer():
    """Build the Presidio analyzer once (loading spaCy takes about a second)."""
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    ).create_engine()
    engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    custom = [
        PatternRecognizer("FAKE_SSN", patterns=[Pattern("ssn", r"\b\d{3}-\d{2}-\d{4}\b", 0.7)]),
        PatternRecognizer(
            "US_PHONE",
            patterns=[
                Pattern("phone", r"(?<!\d)(?:\(\d{3}\)\s?|\d{3}[-. ])\d{3}[-. ]\d{4}\b", 0.6)
            ],
        ),
        PatternRecognizer(
            "CARD_LIKE", patterns=[Pattern("card", r"\b(?:\d{4}[ -]){3}\d{4}\b", 0.7)]
        ),
        PatternRecognizer(
            "ACCOUNT_NUMBER",
            patterns=[Pattern("digits", r"(?<![\d*])\d{8,19}\b", 0.4)],
            context=["account", "acct", "routing", "card", "number", "bank"],
        ),
        PatternRecognizer(
            "STREET_ADDRESS",
            patterns=[
                Pattern(
                    "street",
                    r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Way|Court|Ct|Place|Pl)\b\.?",
                    0.7,
                )
            ],
        ),
    ]
    for r in custom:
        engine.registry.add_recognizer(r)
    return engine


DATE = r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4})"
# A date counts as a date of birth only when a birth keyword comes shortly before it.
# (Done with a plain regex: Presidio's context matching uses lemmas, and spaCy lemmatizes
# "born" to "bear".)
DOB = re.compile(
    r"\b(?:born|birth|dob|birthday|birthdate)\b[^.\n]{0,25}?(" + DATE + ")", re.IGNORECASE
)


def _dob_spans(text: str) -> list[tuple[int, int, str, float]]:
    return [(m.start(1), m.end(1), "DATE_OF_BIRTH", 0.9) for m in DOB.finditer(text)]


def _looks_like_full_name(value: str) -> bool:
    """The small NER model tags stray capitalized words ("Email ...") as PERSON, so a name
    must be at least two capitalized words. Single first names are missed (measured in M3.3)."""
    words = value.split()
    return len(words) >= 2 and all(w[:1].isupper() for w in words)


def detect(text: str, entities: list[str]) -> list[tuple[int, int, str]]:
    """Non-overlapping (start, end, entity) spans, highest score then longest span wins."""
    results = analyzer().analyze(
        text=text, language="en", entities=entities, score_threshold=SCORE_THRESHOLD
    )
    candidates = [(r.start, r.end, r.entity_type, r.score) for r in results]
    if "DATE_OF_BIRTH" in entities:
        candidates += _dob_spans(text)
    spans = []
    for start, end, entity, _score in sorted(candidates, key=lambda c: (-c[3], -(c[1] - c[0]))):
        value = text[start:end]
        if entity == "PERSON" and (
            not _looks_like_full_name(value) or any(value in n or n in value for n in ALLOWED_NAMES)
        ):
            continue
        if PLACEHOLDER.fullmatch(value) or "****" in text[max(0, start - 4) : start]:
            continue
        if any(not (end <= s or start >= e) for s, e, _ in spans):
            continue
        spans.append((start, end, entity))
    return sorted(spans)


class PIIRedactor:
    """Redacts PII in user input (stage input) and in replies (stage output)."""

    name = "pii"

    def check(self, text: str, context: dict) -> GuardrailResult:
        entities = OUTPUT_ENTITIES if context.get("stage") == "output" else INPUT_ENTITIES
        spans = detect(text, entities)
        if not spans:
            return passed(self.name, text)
        mapping = context.setdefault("pii_map", {})  # value → placeholder, request memory only
        counts = context.setdefault("pii_counts", {})
        out, last, found = [], 0, []
        for start, end, entity in spans:
            value = text[start:end]
            kind = PLACEHOLDER_TYPE[entity]
            if value not in mapping:
                counts[kind] = counts.get(kind, 0) + 1
                mapping[value] = f"<{kind}_{counts[kind]}>"
            out += [text[last:start], mapping[value]]
            last = end
            found.append(kind)
        out.append(text[last:])
        return GuardrailResult(
            self.name,
            True,
            "redact",
            "".join(out),
            sorted(set(found)),
            {"spans": float(len(spans))},
        )
