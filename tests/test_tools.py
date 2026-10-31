"""Tool behavior, with key numbers checked by hand against data/profiles/v1.json."""

import json
from pathlib import Path

import pytest

from credit.tools.contracts import PAYOFF_DISCLAIMER, TOOL_CONTRACTS
from credit.tools.impl import call_tool

FIXTURES = Path(__file__).resolve().parents[1] / "contracts" / "tools" / "fixtures" / "v1.json"


def test_utilization_story_001_by_hand():
    # Open cards at 2026-06: acc_01 $1,200 / $8,000 and acc_03 $3,700 / $4,000.
    # Overall = 4,900 / 12,000 = 40.8%.
    out = call_tool("get_utilization", {"profile_id": "story_001"})
    assert out["total_balance"] == 4900
    assert out["total_limit"] == 12000
    assert out["overall_utilization_pct"] == 40.8
    assert {c["account_id"]: c["utilization_pct"] for c in out["cards"]} == {
        "acc_01": 15.0,
        "acc_03": 92.5,
    }


def test_simulate_payoff_by_hand():
    # Pay $2,000 on acc_03: 1,700 / 4,000 = 42.5%; overall 2,900 / 12,000 = 24.2%.
    out = call_tool(
        "simulate_payoff", {"profile_id": "story_001", "account_id": "acc_03", "amount": 2000}
    )
    assert out["card_balance_after"] == 1700
    assert out["card_utilization_pct_after"] == 42.5
    assert out["overall_utilization_pct_after"] == 24.2
    assert out["note"] == PAYOFF_DISCLAIMER
    assert "score" not in {k for k in out if k != "note"}


def test_payoff_capped_at_balance():
    out = call_tool(
        "simulate_payoff", {"profile_id": "story_001", "account_id": "acc_03", "amount": 99999}
    )
    assert out["applied_amount"] == 3700
    assert out["card_balance_after"] == 0


@pytest.mark.parametrize(
    "tool,args,code",
    [
        ("get_credit_profile", {"profile_id": "p_999"}, "PROFILE_NOT_FOUND"),
        ("get_credit_profile", {"profile_id": "DROP TABLE"}, "INVALID_INPUT"),
        (
            "simulate_payoff",
            {"profile_id": "story_001", "account_id": "acc_02", "amount": 1},
            "NOT_A_CREDIT_CARD",
        ),
        (
            "simulate_payoff",
            {"profile_id": "story_001", "account_id": "acc_09", "amount": 1},
            "ACCOUNT_NOT_FOUND",
        ),
        ("explain_factor", {"factor_code": "SHOE_SIZE"}, "INVALID_INPUT"),
        ("no_such_tool", {}, "INVALID_INPUT"),
    ],
)
def test_errors_are_returned_not_raised(tool, args, code):
    assert call_tool(tool, args)["error"]["error_code"] == code


def test_profile_summary_story_002():
    out = call_tool("get_credit_profile", {"profile_id": "story_002"})
    assert out["score"] == 753
    assert out["top_factors"][0] == "PAYMENT_HISTORY"
    assert out["late_payments_last_24_months"] == [
        {"account_id": "acc_02", "month": "2026-03", "days_late": 60}
    ]
    assert all(a["masked_number"].startswith("****") for a in out["accounts"])


def test_score_history_months():
    out = call_tool("get_score_history", {"profile_id": "story_003", "months": 3})
    assert [p["month"] for p in out["points"]] == ["2026-04", "2026-05", "2026-06"]


def test_outputs_validate_against_contracts():
    for fx in json.loads(FIXTURES.read_text())["fixtures"]:
        if "error" not in fx["output"]:
            TOOL_CONTRACTS[fx["tool"]][1].model_validate(fx["output"])


def test_fixtures_reproduce():
    for fx in json.loads(FIXTURES.read_text())["fixtures"]:
        assert call_tool(fx["tool"], fx["input"]) == fx["output"], fx
