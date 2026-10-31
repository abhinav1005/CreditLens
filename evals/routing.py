"""Misroute check for the model router, against the golden set's own labels (no API calls).

    uv run python -m evals route-check

A chat case "needs data" if its expectations show it depends on the person's profile:
it must call a tool, must state a profile number, or must end with the disclaimer (which
the system prompt requires only for replies about the person's credit).
- misroute: sent to the SMALL model but needs data (quality risk)
- missed saving: sent to the BIG model but doesn't need data (cost, not quality)
"""

from assistant.router import route
from evals.cases import Case


def needs_data(case: Case) -> bool:
    e = case.expectations
    return bool(e.must_call_tools or e.numeric_facts or e.disclaimer)


def route_check(cases: list[Case]) -> dict:
    chat = [c for c in cases if c.kind == "chat"]
    rows = [(c, route(c.conversation)[0], needs_data(c)) for c in chat]
    misroutes = [c.id for c, tier, need in rows if tier == "small" and need]
    missed = [c.id for c, tier, need in rows if tier == "big" and not need]
    small = sum(tier == "small" for _, tier, _ in rows)
    return {
        "n_chat_cases": len(rows),
        "routed_small": small,
        "routed_small_share": round(small / len(rows), 4) if rows else None,
        "misroutes": misroutes,
        "misroute_rate": round(len(misroutes) / len(rows), 4) if rows else None,
        "missed_savings": len(missed),
    }
