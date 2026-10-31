"""Numeric grounding: every number in the answer must come from somewhere legitimate.

A number in the final answer is grounded if it matches (within rounding, see
policy/constants.yaml) any of:
1. a numeric value in a tool result from this conversation (free-text fields excluded)
2. a month string from a tool result ("2026-04" grounds 2026 and 4)
3. the length of a list in a tool result (e.g. number of accounts)
4. a difference between two values of the same field across items of one list
   (e.g. two months of score history), or a *_before / *_after pair; the total of a field
   across a list, overall or per account type (e.g. all credit-card balances); an account's
   age as of the data month (months, or years rounded either way)
5. utilization recomputed as balance ÷ limit (as a percentage)
6. a number the user wrote in the conversation
7. an allowed educational constant from policy/constants.yaml, written with the same
   unit (a "12 months" constant does not ground "12%")

8. the last four digits of a masked account seen in tool results ("account ending 5512")

Which sentences are checked:
- If the assistant had the person's data this turn (a profile tool result), EVERY sentence.
- If it didn't, only sentences that make a claim about the person ("your", "you have"):
  general education ("bankruptcies can stay 7 to 10 years") isn't a claim about them, and
  its accuracy is graded by the judge's groundedness dimension. Any "your ..." number
  stated without data is still ungrounded and fails.
- Never: markdown list numbering ("1. "), or explicitly hypothetical example sentences
  ("For example, a $300 balance on a $1,000 limit is 30%") that don't mention "your".
Anything else counts as ungrounded and fails the check.
"""

import json
import re
from functools import lru_cache
from itertools import combinations
from pathlib import Path

import yaml

from credit.months import months_between
from evals.cases import Case
from evals.scorers.base import CaseOutput, Check

CONSTANTS_PATH = Path(__file__).resolve().parents[2] / "policy" / "constants.yaml"
FREE_TEXT_FIELDS = {
    "creditor_name",
    "notes",
    "message",
    "description",
    "explanation",
    "title",
    "note",
}
MONTH = re.compile(r"\b(\d{4})-(\d{2})\b")
MASKED = re.compile(r"\*{4}\d{4}")
# A number not glued to a word or underscore (skips acc_03, p_001). Masked account numbers
# are removed before this runs, so markdown bold like **40.8%** is still read. Hyphens are
# not excluded, so both ends of a range like "300-999" get checked.
NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![\w])")
# Markdown numbered-list markers ("1. ", "2) ") at the start of a line are not claims.
LIST_MARKER = re.compile(r"^(\s*)\d+[.)](?=\s)", re.M)
# A sentence that is explicitly a hypothetical example ("For example, a $300 balance on a
# $1,000 limit...") makes no claim about the person, so it is exempt UNLESS it also talks
# about "your"/"you have", which would make it a claim about them.
EXAMPLE_MARKERS = re.compile(
    r"\b(for example|for instance|e\.g\.|say you|imagine|suppose|if you had)\b", re.I
)
ABOUT_THE_PERSON = re.compile(r"\b(your|you have|you've|you owe)\b", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def strip_hypotheticals(text: str) -> str:
    kept = [
        s
        for s in SENTENCE_SPLIT.split(text)
        if not (EXAMPLE_MARKERS.search(s) and not ABOUT_THE_PERSON.search(s))
    ]
    return "\n".join(kept)


UNIT_AFTER = [
    ("percent", re.compile(r"\s?(%|percent)", re.I)),
    ("years", re.compile(r"[\s-]?years?\b", re.I)),
    ("months", re.compile(r"[\s-]?months?\b", re.I)),
    ("days", re.compile(r"[\s-]?days?\b", re.I)),
]


@lru_cache(maxsize=1)
def allowed_constants() -> dict[str, set[float]]:
    """unit → allowed values."""
    data = yaml.safe_load(CONSTANTS_PATH.read_text())
    by_unit: dict[str, set[float]] = {}
    for item in data["allowed_numbers"]:
        by_unit.setdefault(item["unit"], set()).add(float(item["value"]))
    return by_unit


def _unit_after(text: str, end: int) -> str:
    for unit, pattern in UNIT_AFTER:
        if pattern.match(text, end):
            return unit
    return "none"


def extract_numbers(text: str) -> list[tuple[float, int, str]]:
    """(value, decimals, raw) for each number. Masked numbers are skipped; months split."""
    return [(v, d, raw) for v, d, raw, _ in extract_numbers_with_units(text)]


def extract_numbers_with_units(text: str) -> list[tuple[float, int, str, str]]:
    text = MASKED.sub(" ", text)
    text = LIST_MARKER.sub(r"\1", text)
    found = []
    for year, month in MONTH.findall(text):
        found.append((float(year), 0, f"{year}-{month}", "none"))
        found.append((float(month), 0, f"{year}-{month}", "none"))
    text = MONTH.sub(" ", text)
    for m in NUMBER.finditer(text):
        whole, frac = m.group(1), m.group(2) or ""
        value = float(whole.replace(",", "") + frac)
        found.append(
            (value, len(frac) - 1 if frac else 0, whole + frac, _unit_after(text, m.end()))
        )
    return found


def _walk(node, key: str | None, values: set[float]) -> None:
    if isinstance(node, bool):
        return
    if isinstance(node, int | float):
        values.add(float(node))
    elif isinstance(node, str):
        if key not in FREE_TEXT_FIELDS:
            for year, month in MONTH.findall(node):
                values.update({float(year), float(month)})
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk(v, k, values)
        before_after = [k[: -len("_before")] for k in node if k.endswith("_before")]
        for stem in before_after:
            a, b = node.get(stem + "_before"), node.get(stem + "_after")
            if isinstance(a, int | float) and isinstance(b, int | float):
                values.add(abs(float(a) - float(b)))
        for bal, lim in [("balance", "credit_limit"), ("total_balance", "total_limit")]:
            if isinstance(node.get(bal), int | float) and node.get(lim):
                values.add(round(100 * node[bal] / node[lim], 1))
    elif isinstance(node, list):
        values.add(float(len(node)))
        for item in node:
            _walk(item, key, values)
        dict_items = [i for i in node if isinstance(i, dict)]
        fields = {
            k
            for i in dict_items
            for k, v in i.items()
            if isinstance(v, int | float) and not isinstance(v, bool)
        }
        for field in fields:
            series = [i[field] for i in dict_items if isinstance(i.get(field), int | float)]
            for a, b in combinations(series, 2):
                values.add(abs(float(a) - float(b)))
            # Totals: across all items, and per account type (e.g. all credit-card balances).
            values.add(float(sum(series)))
            for t in {i.get("type") for i in dict_items if i.get("type")}:
                values.add(
                    float(
                        sum(
                            i[field]
                            for i in dict_items
                            if i.get("type") == t and isinstance(i.get(field), int | float)
                        )
                    )
                )
        # Overall utilization recomputed from card totals (sum of balances ÷ sum of limits),
        # e.g. "you owe $8,052 across $11,000 in limits, about 73%".
        cards = [
            i
            for i in dict_items
            if isinstance(i.get("balance"), int | float) and i.get("credit_limit")
        ]
        if cards:
            values.add(
                round(
                    100 * sum(i["balance"] for i in cards) / sum(i["credit_limit"] for i in cards),
                    1,
                )
            )


def _account_ages(output: dict, values: set[float]) -> None:
    """Age of each account as of the data month, in months and in whole/rounded years."""
    as_of = output.get("as_of") if isinstance(output, dict) else None
    if not as_of:
        return
    for account in output.get("accounts", []):
        months = months_between(account["opened"], as_of)
        values.update({float(months), float(months // 12), float(round(months / 12))})


def grounded_values(case: Case, out: CaseOutput) -> set[float]:
    """Values grounded by data (tools and user messages), regardless of unit."""
    values: set[float] = set()
    for call in out.tool_calls:
        _walk(call.get("output", {}), None, values)
        _account_ages(call.get("output", {}), values)
    # Tool results inside the case's fixed earlier turns count too.
    for m in case.conversation:
        if m.get("role") == "user":
            values.update(v for v, _, _ in extract_numbers(m["content"]))
        if m.get("role") == "tool":
            for r in m["results"]:
                try:
                    _walk(json.loads(r["content"]), None, values)
                except (ValueError, TypeError):
                    pass
    return values


def is_grounded(value: float, decimals: int, candidates: set[float]) -> bool:
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    return any(abs(value - c) <= tolerance for c in candidates)


PROFILE_TOOLS = {"get_credit_profile", "get_score_history", "get_utilization", "simulate_payoff"}
WORD_NUMBERS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve".split()
    )
}


def number_words(text: str) -> list[tuple[float, int, str]]:
    """Spelled-out small counts ("two late payments"), for checking expected facts."""
    return [
        (float(WORD_NUMBERS[w.lower()]), 0, w)
        for w in re.findall(r"\b(" + "|".join(WORD_NUMBERS) + r")\b", text, re.I)
    ]


def masked_numbers_in_outputs(out: CaseOutput) -> set[str]:
    found = set()
    for call in out.tool_calls:
        found.update(MASKED.findall(str(call.get("output", ""))))
    return found


def saw_profile_data(case: Case, out: CaseOutput) -> bool:
    """Did the assistant have this person's data (a profile tool result) in this turn?"""
    if any(c["name"] in PROFILE_TOOLS for c in out.tool_calls):
        return True
    return any(m.get("role") == "tool" for m in case.conversation)


def sentences_to_check(case: Case, out: CaseOutput) -> str:
    """With the person's data in hand, every sentence is checked (minus explicit examples).
    Without it, only sentences that make claims about the person ("your", "you have") are:
    general education like "bankruptcies can stay 7 to 10 years" isn't a claim about them,
    and its accuracy is the judge's groundedness dimension."""
    text = strip_hypotheticals(out.final_text)
    if saw_profile_data(case, out):
        return text
    return "\n".join(s for s in SENTENCE_SPLIT.split(text) if ABOUT_THE_PERSON.search(s))


def last_four(masked: set[str]) -> set[float]:
    return {float(m[-4:]) for m in masked}


def score_grounding(case: Case, out: CaseOutput) -> list[Check]:
    if case.kind != "chat":
        return []
    text = out.final_text
    known_masked = masked_numbers_in_outputs(out) | {
        mm for m in case.conversation if m.get("role") == "tool" for mm in MASKED.findall(str(m))
    }
    # "card ending 9054" written by the user also identifies a masked account.
    user_last4 = {
        f"****{d}"
        for m in case.conversation
        if m.get("role") == "user"
        for d in re.findall(r"ending (?:in )?(\d{4})\b", m["content"])
    }
    known_masked |= user_last4
    candidates = grounded_values(case, out) | last_four(known_masked)
    constants = allowed_constants()
    ungrounded = [
        raw
        for value, dec, raw, unit in extract_numbers_with_units(sentences_to_check(case, out))
        if not is_grounded(value, dec, candidates)
        and not is_grounded(value, dec, constants.get(unit, set()))
    ]
    checks = [
        Check(
            "numeric_grounding",
            "grounding",
            not ungrounded,
            f"ungrounded: {ungrounded}" if ungrounded else "",
        )
    ]
    unknown_masked = [m for m in MASKED.findall(text) if m not in known_masked]
    if MASKED.search(text):
        checks.append(
            Check("masked_numbers_known", "grounding", not unknown_masked, str(unknown_masked))
        )
    stated_values = extract_numbers(text) + number_words(text)
    for fact in case.expectations.numeric_facts:
        stated = any(is_grounded(fact.value, dec, {v}) for v, dec, _ in stated_values)
        checks.append(Check(f"states:{fact.value:g}", "numeric_facts", stated, fact.description))
    return checks
