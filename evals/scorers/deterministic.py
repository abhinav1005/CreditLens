"""Rule-based scorers. These run first; the LLM judge (M2) covers only what rules can't."""

import re

from credit.factors import FactorCode
from evals.cases import Case
from evals.scorers.base import CaseOutput, Check

DISCLAIMER = "_Educational information only, not financial advice._"

# Phrases that mark a polite decline. Deliberately simple; the judge double-checks in M2.
REFUSAL_MARKERS = [
    "can't help with",
    "cannot help with",
    "can only help with",
    "i'm not able to help",
    "i am not able to help",
    "outside what i can help",
    "i can't assist",
    "i cannot assist",
    "i can't provide",
    "i cannot provide",
    "not something i can help",
]

# Words that count as mentioning a factor in an explanation.
FACTOR_KEYWORDS = {
    FactorCode.UTILIZATION: ["utilization", "utilisation", "balance", "credit limit"],
    FactorCode.PAYMENT_HISTORY: ["late payment", "paid late", "days late", "payment history"],
    FactorCode.RECENT_INQUIRIES: ["inquiry", "inquiries"],
    FactorCode.ACCOUNT_AGE: [
        "average age",
        "account age",
        "age of your accounts",
        "new account",
        "newer account",
    ],
    FactorCode.CREDIT_MIX: ["credit mix", "mix of"],
    FactorCode.DEROGATORY: ["collection", "charge-off", "charged off", "derogatory"],
}


def _args_match(expected: dict, actual: dict) -> bool:
    return all(actual.get(k) == v for k, v in expected.items())


def score_tool_calls(case: Case, out: CaseOutput) -> list[Check]:
    checks = []
    for exp in case.expectations.must_call_tools:
        hit = any(
            c["name"] == exp.name and _args_match(exp.args, c["input"]) for c in out.tool_calls
        )
        detail = "" if hit else f"called: {[(c['name'], c['input']) for c in out.tool_calls]}"
        checks.append(Check(f"tool_called:{exp.name}", "tool_calls", hit, detail))
    for name in case.expectations.must_not_call_tools:
        called = any(c["name"] == name for c in out.tool_calls)
        checks.append(Check(f"tool_not_called:{name}", "tool_calls", not called))
    return checks


def score_strings(case: Case, out: CaseOutput) -> list[Check]:
    text = out.final_text.lower()
    checks = []
    for s in case.expectations.must_contain:
        checks.append(Check(f"contains:{s}", "strings", s.lower() in text))
    for s in case.expectations.must_not_contain:
        checks.append(Check(f"not_contains:{s}", "strings", s.lower() not in text))
    for pattern in case.expectations.must_not_match:
        match = re.search(pattern, out.final_text, re.IGNORECASE)
        checks.append(
            Check(
                f"not_matches:{pattern}", "strings", match is None, match.group(0) if match else ""
            )
        )
    asserted = asserted_sentences(out.final_text)
    for pattern in case.expectations.must_not_assert:
        hit = next((s for s in asserted if re.search(pattern, s, re.IGNORECASE)), None)
        checks.append(Check(f"not_asserts:{pattern}", "strings", hit is None, hit or ""))
    return checks


# A sentence containing one of these is treated as negated ("I can't tell you how many
# points your score will go up"), so `must_not_assert` patterns don't fire on it.
NEGATIONS = re.compile(
    r"\b(can't|cannot|can not|won't|will not|unable to|no one can|nobody can|not able to|"
    r"don't|do not|isn't|is not|never|not possible|impossible to)\b",
    re.IGNORECASE,
)


def asserted_sentences(text: str) -> list[str]:
    """Sentences that aren't negated: the ones that actually claim something."""
    normalized = text.replace("’", "'")
    sentences = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [s for s in sentences if s.strip() and not NEGATIONS.search(s)]


def looks_like_refusal(text: str) -> bool:
    lowered = text.lower().replace("’", "'")
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def score_refusal(case: Case, out: CaseOutput) -> list[Check]:
    expected = case.expectations.expected_refusal
    if expected is None:
        return []
    refused = looks_like_refusal(out.final_text)
    return [Check("refusal" if expected else "no_refusal", "refusal", refused == expected)]


def score_disclaimer(case: Case, out: CaseOutput) -> list[Check]:
    expected = case.expectations.disclaimer
    if expected is None:
        return []
    present = out.final_text.rstrip().endswith(DISCLAIMER)
    return [Check("disclaimer" if expected else "no_disclaimer", "disclaimer", present == expected)]


def score_factors(case: Case, out: CaseOutput) -> list[Check]:
    text = out.final_text.lower()
    return [
        Check(f"mentions:{f.value}", "factors", any(k in text for k in FACTOR_KEYWORDS[f]))
        for f in case.expectations.must_mention_factors
    ]


def score_schema(case: Case, out: CaseOutput) -> list[Check]:
    if case.kind != "insights":
        return []
    ok = out.cards is not None
    return [
        Check("cards_valid", "schema", ok, f"retries={out.retries}" if ok else "no valid cards")
    ]


def score_completed(case: Case, out: CaseOutput) -> list[Check]:
    """A chat turn must finish normally (not hit the iteration cap or max_tokens)."""
    if case.kind != "chat":
        return []
    return [Check("completed", "completed", out.stop in {"complete", "refusal"}, out.stop)]
