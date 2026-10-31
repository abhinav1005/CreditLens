"""Compliance guardrail for replies (policy: policy/compliance.md, rules R1-R4).

Two layers, like the injection guardrail:
- Sentence rules (deterministic, before anything is streamed): a sentence that clearly
  breaks R1-R3 is dropped. Negated sentences ("I can't promise your score will rise") are
  not violations.
- Final check (LLM classifier, Haiku 5.5): the finished reply is checked against R1-R4.
  run_turn regenerates once with the broken rule named, then falls back to a safe reply.

Classifier verdicts are cached on disk like the injection classifier's.
"""

import hashlib
import json
import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from assistant.prompts import PROMPTS_DIR
from assistant.schema import inline_refs
from guardrails.base import GuardrailResult, passed

CLASSIFIER_MODEL = "claude-haiku-5-5"
PROMPT_FILE = PROMPTS_DIR / "guardrails" / "compliance_v1.md"
RULE_IDS = [
    "no_score_promises",
    "no_product_recommendations",
    "no_protected_characteristics",
    "no_legal_advice",
]

SENTENCE_RULES = {
    "no_score_promises": [
        r"\b(will|would|should|is going to)\s+(definitely\s+|likely\s+|probably\s+)?(raise|increase|boost|improve|lift|bump|jump)\s+your\s+(credit\s+)?score",
        r"\byour\s+(credit\s+)?score\s+(will|would|should|is going to)\s+(definitely\s+|likely\s+|probably\s+)?(go up|rise|increase|improve|jump|recover|climb|hit|reach|be)\b",
        r"\b(gain|go up|rise|increase|jump|climb)\s+(by\s+)?(about\s+|roughly\s+|around\s+|up to\s+)?\d+\s*(points|pts)\b",
        r"\byou(?:'ll| will)\s+(have|be at|hit|reach|get)\s+(a\s+)?(score of\s+)?\d{3}\b",
    ],
    "no_product_recommendations": [
        r"\b(i\s+recommend|i'd\s+recommend|i\s+suggest|you\s+should\s+(apply|sign up|go with)|apply\s+for\s+the|go\s+with)\s+[A-Z][\w&]+",
    ],
    "no_protected_characteristics": [
        r"\b(married|single|divorced|women|men|older|younger|religio\w*|race|ethnic\w*|immigrants?)\b[^.]{0,40}\b(tend to|usually|often|typically)\s+(have|get)\s+(better|worse|higher|lower)\s+(credit\s+)?scores?",
    ],
}
_COMPILED = {
    rule: [re.compile(p, re.IGNORECASE) for p in pats] for rule, pats in SENTENCE_RULES.items()
}
NEGATIONS = re.compile(
    r"\b(can't|cannot|can not|won't|will not|unable to|no one can|nobody can|not able to|don't|do not|"
    r"isn't|is not|aren't|are not|never|not possible|impossible to|no way to|not a factor)\b",
    re.IGNORECASE,
)


def sentence_violations(sentence: str) -> list[str]:
    normalized = sentence.replace("’", "'")
    if NEGATIONS.search(normalized):
        return []
    return [rule for rule, pats in _COMPILED.items() if any(p.search(normalized) for p in pats)]


class ComplianceVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str
    violated_rules: list[
        Literal[
            "no_score_promises",
            "no_product_recommendations",
            "no_protected_characteristics",
            "no_legal_advice",
        ]
    ]
    verdict: Literal["compliant", "violation"]


@lru_cache(maxsize=1)
def _prompt() -> tuple[str, str]:
    text = PROMPT_FILE.read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


def classify_reply(text: str, provider=None, cache_dir=None) -> tuple[list[str], str, float]:
    """(violated rule ids, rationale, cost_usd). Empty list = compliant."""
    from assistant.config import ROOT, load_pricing, request_cost
    from assistant.providers import ProviderRequest, get_provider
    from evals.cache import ResponseCache

    system, prompt_hash = _prompt()
    cache = ResponseCache(cache_dir or ROOT / ".cache" / "guardrails")
    key = hashlib.sha256(
        json.dumps(["compliance", text, CLASSIFIER_MODEL, prompt_hash]).encode()
    ).hexdigest()
    hit = cache.get(key)
    if hit:
        return hit["violated_rules"], hit["rationale"], 0.0
    provider = provider or get_provider(CLASSIFIER_MODEL)
    response = provider.complete(
        ProviderRequest(
            model=CLASSIFIER_MODEL,
            system=system,
            messages=[{"role": "user", "content": f"<reply>\n{text}\n</reply>"}],
            max_tokens=1500,
            effort="low",
            output_schema=inline_refs(ComplianceVerdict.model_json_schema()),
        )
    )
    try:
        v = ComplianceVerdict.model_validate_json(response.text)
        violated = sorted(set(v.violated_rules)) if v.verdict == "violation" else []
        rationale = v.rationale
    except ValueError:
        violated, rationale = ["unparseable_verdict"], "classifier output invalid; failing closed"
    cost = request_cost(load_pricing(), CLASSIFIER_MODEL, response.usage)
    cache.put(key, {"violated_rules": violated, "rationale": rationale})
    return violated, rationale, cost


class ComplianceGuard:
    """Output guardrail. `check` runs per sentence; `final_check` runs on the whole reply."""

    name = "compliance"

    def __init__(self, use_llm: bool = True, provider=None, cache_dir=None):
        self.use_llm = use_llm
        self.provider = provider
        self.cache_dir = cache_dir

    def check(self, text: str, context: dict) -> GuardrailResult:
        rules = sentence_violations(text)
        if rules:
            return GuardrailResult(self.name, False, "block", text, rules, {"layer_rules": 1.0})
        return passed(self.name, text)

    def final_check(self, text: str) -> tuple[list[str], dict]:
        rules = sorted(
            {r for s in re.split(r"(?<=[.!?])\s+|\n+", text) for r in sentence_violations(s)}
        )
        if rules:
            return rules, {"layer": "rules"}
        if not self.use_llm or not text.strip():
            return [], {"layer": "rules"}
        violated, rationale, cost = classify_reply(text, self.provider, self.cache_dir)
        return violated, {"layer": "llm", "rationale": rationale, "cost": cost}
