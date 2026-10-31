from assistant.insights import gather_tool_data
from evals.cases import Case
from evals.scorers.base import CaseOutput
from evals.scorers.insights import resolve, score_insight_cards

CASE = Case.model_validate(
    {
        "id": "ins_001",
        "kind": "insights",
        "category": "insight_grounding",
        "profile_id": "story_001",
        "expectations": {},
        "authored_by": "human",
    }
)
CALLS = gather_tool_data("story_001")


def card(summary, evidence, factor="UTILIZATION"):
    return {
        "title": "t",
        "summary": summary,
        "factor_code": factor,
        "evidence": evidence,
        "suggested_next_step": "s",
        "disclaimer_required": True,
    }


def run(cards):
    return {
        c.name: c
        for c in score_insight_cards(CASE, CaseOutput("insights", tool_calls=CALLS, cards=cards))
    }


def test_resolve_paths():
    util = next(c["output"] for c in CALLS if c["name"] == "get_utilization")
    assert resolve(util, "overall_utilization_pct") == 40.8
    assert resolve(util, "cards.1.utilization_pct") == 92.5
    # Out-of-range index, unknown key and non-numeric index all give the same "missing" sentinel.
    assert (
        resolve(util, "cards.9.utilization_pct")
        is resolve(util, "nope")
        is resolve(util, "cards.x")
    )


def test_good_card_passes_all():
    r = run(
        [
            card(
                "Overall utilization is 40.8%, with one card at 92.5%.",
                [
                    {"tool": "get_utilization", "field": "overall_utilization_pct", "value": 40.8},
                    {"tool": "get_utilization", "field": "cards.1.utilization_pct", "value": 92.5},
                ],
            )
        ]
    )
    assert all(c.passed for c in r.values()), r


def test_number_missing_from_evidence():
    r = run(
        [
            card(
                "Utilization is 40.8% and your score is 739.",
                [
                    {"tool": "get_utilization", "field": "overall_utilization_pct", "value": 40.8},
                ],
            )
        ]
    )
    assert not r["card0:summary_in_evidence"].passed


def test_invented_evidence_caught():
    r = run(
        [
            card(
                "Utilization is 12.0%.",
                [
                    {"tool": "get_utilization", "field": "overall_utilization_pct", "value": 12.0},
                ],
            )
        ]
    )
    assert r["card0:summary_in_evidence"].passed  # consistent with its own evidence...
    assert not r["card0:evidence_matches_tools"].passed  # ...but the evidence is false


def test_evidence_from_uncalled_tool():
    r = run([card("x", [{"tool": "simulate_payoff", "field": "applied_amount", "value": 1}])])
    assert not r["card0:evidence_matches_tools"].passed


def test_factor_must_be_top_factor():
    ev = [{"tool": "get_utilization", "field": "overall_utilization_pct", "value": 40.8}]
    assert not run([card("40.8%", ev, factor="DEROGATORY")])["card0:factor_in_top_factors"].passed


def test_month_evidence_grounds_month_in_summary():
    r = run(
        [
            card(
                "Your newest account was opened in 2026-04.",
                [
                    {
                        "tool": "get_credit_profile",
                        "field": "accounts.2.opened",
                        "value": "2026-04",
                    },
                ],
                factor="ACCOUNT_AGE",
            )
        ]
    )
    assert r["card0:summary_in_evidence"].passed and r["card0:evidence_matches_tools"].passed


def test_constants_allowed_in_summaries_but_counts_need_evidence():
    ev = [{"tool": "get_utilization", "field": "overall_utilization_pct", "value": 40.8}]
    assert run([card("Utilization is 40.8%; inquiries count for 12 months.", ev)])[
        "card0:summary_in_evidence"
    ].passed
    assert not run([card("Utilization is 40.8% across 2 cards.", ev)])[
        "card0:summary_in_evidence"
    ].passed
