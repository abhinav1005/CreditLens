"""Insight-card grounding.

For each card:
1. summary_in_evidence: every number in the summary matches (within rounding) a value in
   that card's evidence list.
2. evidence_matches_tools: every evidence item names a tool that was actually called and a
   dot-path field that resolves to the same value in that call's real output. This stops a
   model from inventing evidence to satisfy check 1.
3. factor_in_top_factors: the card's factor_code is one of the profile's top factors.
"""

from evals.cases import Case
from evals.scorers.base import CaseOutput, Check
from evals.scorers.grounding import extract_numbers, is_grounded

_MISSING = object()


def resolve(output, path: str):
    """Follow a dot path like 'cards.1.utilization_pct' into a tool output."""
    node = output
    for part in path.split("."):
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return _MISSING
    return node


def values_equal(claimed, actual) -> bool:
    if isinstance(actual, bool) or isinstance(claimed, bool):
        return claimed == actual
    if isinstance(actual, int | float):
        try:
            return abs(float(claimed) - float(actual)) < 1e-9
        except (TypeError, ValueError):
            return False
    return str(claimed) == str(actual)


def score_insight_cards(case: Case, out: CaseOutput) -> list[Check]:
    if case.kind != "insights" or not out.cards:
        return []
    outputs = {c["name"]: c["output"] for c in out.tool_calls}
    top = outputs.get("get_credit_profile", {}).get("top_factors", [])
    checks = []
    for i, card in enumerate(out.cards):
        evidence_values = set()
        for e in card["evidence"]:
            try:
                evidence_values.add(float(e["value"]))
            except (TypeError, ValueError):
                pass
        missing = [
            raw
            for v, d, raw in extract_numbers(card["summary"])
            if not is_grounded(v, d, evidence_values)
        ]
        checks.append(
            Check(
                f"card{i}:summary_in_evidence",
                "insights",
                not missing,
                f"not in evidence: {missing}" if missing else "",
            )
        )

        bad = []
        for e in card["evidence"]:
            actual = resolve(outputs[e["tool"]], e["field"]) if e["tool"] in outputs else _MISSING
            if actual is _MISSING or not values_equal(e["value"], actual):
                shown = "missing" if actual is _MISSING else actual
                bad.append(f"{e['tool']}.{e['field']}={e['value']!r} (actual: {shown!r})")
        checks.append(Check(f"card{i}:evidence_matches_tools", "insights", not bad, "; ".join(bad)))
        checks.append(
            Check(
                f"card{i}:factor_in_top_factors",
                "insights",
                card["factor_code"] in top,
                f"{card['factor_code']} vs {top}",
            )
        )
    return checks
