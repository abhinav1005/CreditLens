import json

import pytest

from assistant.providers import ToolCall
from assistant.providers.fake import FakeProvider, FakeTurn
from evals.cache import cache_key
from evals.cases import Case
from evals.runner import BudgetExceeded, percentile, run_suite

DISCLAIMER = "_Educational information only, not financial advice._"

CHAT = Case.model_validate(
    {
        "id": "tool_001",
        "category": "tool_use",
        "profile_id": "story_001",
        "conversation": [{"role": "user", "content": "What's my utilization?"}],
        "expectations": {
            "must_call_tools": [{"name": "get_utilization"}],
            "numeric_facts": [{"value": 40.8}],
            "disclaimer": True,
        },
        "authored_by": "human",
    }
)
OFFTOPIC = Case.model_validate(
    {
        "id": "ref_001",
        "category": "refusal",
        "profile_id": "p_001",
        "conversation": [{"role": "user", "content": "Write me a poem about pizza."}],
        "expectations": {"expected_refusal": True, "must_not_call_tools": ["get_credit_profile"]},
        "authored_by": "human",
    }
)
INSIGHTS = Case.model_validate(
    {
        "id": "ins_001",
        "kind": "insights",
        "category": "insight_grounding",
        "profile_id": "story_001",
        "expectations": {},
        "authored_by": "human",
    }
)
CARDS = {
    "cards": [
        {
            "title": "Utilization",
            "summary": "Overall utilization is 40.8%.",
            "factor_code": "UTILIZATION",
            "evidence": [
                {"tool": "get_utilization", "field": "overall_utilization_pct", "value": 40.8}
            ],
            "suggested_next_step": "Pay down balances.",
            "disclaimer_required": True,
        }
    ]
}


def responder(request):
    if request.output_schema is not None:
        return FakeTurn(text=json.dumps(CARDS))
    last = request.messages[-1]
    if last["role"] == "tool":
        return FakeTurn(text=f"Your overall utilization is 40.8%.\n\n{DISCLAIMER}")
    if "poem" in last["content"]:
        return FakeTurn(text="Sorry, I can only help with credit questions.")
    return FakeTurn(tool_calls=[ToolCall("t1", "get_utilization", {"profile_id": "story_001"})])


def run(tmp_path, cases, provider, **kw):
    return run_suite(
        cases,
        suite="test",
        model="claude-sonnet-5-5",
        prompt_version="v1",
        max_cost_usd=kw.pop("max_cost_usd", 5.0),
        provider_factory=lambda m: provider,
        reports_dir=tmp_path / "reports",
        cache_dir=tmp_path / "cache",
        run_id=kw.pop("run_id", "r1"),
        **kw,
    )


def test_run_scores_and_writes_reports(tmp_path):
    summary = run(tmp_path, [CHAT, OFFTOPIC, INSIGHTS], FakeProvider(responder=responder))
    assert summary["n_passed"] == 3, summary
    assert set(summary["categories"]) == {"tool_use", "refusal", "insight_grounding"}
    out = tmp_path / "reports" / "r1"
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert {r["case_id"] for r in rows} == {"tool_001", "ref_001", "ins_001"}
    assert "Overall pass rate: 100.0% (3/3)" in (out / "report.md").read_text()
    assert summary["cost"]["measured_total_usd"] > 0


def test_second_run_hits_cache_and_spends_nothing(tmp_path):
    run(tmp_path, [CHAT, INSIGHTS], FakeProvider(responder=responder))
    second = FakeProvider(responder=responder)
    summary = run(tmp_path, [CHAT, INSIGHTS], second, run_id="r2")
    assert summary["cache_hits"] == 2 and second.requests == []
    assert summary["cost"]["api_spend_this_run_usd"] == 0
    assert summary["cost"]["measured_total_usd"] > 0  # the recorded cost of producing the answers


def test_failing_case_reported(tmp_path):
    def wrong(request):
        return FakeTurn(
            text="Your utilization is 12%."
        )  # no tool call, made-up number, no disclaimer

    summary = run(tmp_path, [CHAT], FakeProvider(responder=wrong))
    assert summary["n_passed"] == 0
    assert {"tool_calls", "grounding", "numeric_facts", "disclaimer"} <= set(
        summary["failed_checks_by_scorer"]
    )


def test_provider_error_fails_case_not_run(tmp_path):
    def boom(request):
        raise RuntimeError("API down")

    summary = run(tmp_path, [CHAT], FakeProvider(responder=boom))
    assert summary["status_counts"] == {"error": 1}


def test_budget_refuses_to_start(tmp_path):
    with pytest.raises(BudgetExceeded):
        run(tmp_path, [CHAT] * 1, FakeProvider(responder=responder), max_cost_usd=0.0001)


def test_cache_key_sensitive_to_prompt_and_model():
    base = cache_key({"c": 1}, "m1", {"effort": "low"}, "hashA")
    assert base == cache_key({"c": 1}, "m1", {"effort": "low"}, "hashA")
    assert base != cache_key({"c": 1}, "m1", {"effort": "low"}, "hashB")
    assert base != cache_key({"c": 1}, "m2", {"effort": "low"}, "hashA")
    assert base != cache_key({"c": 1}, "m1", {"effort": "high"}, "hashA")


def test_percentile_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([1, 2, 3, 4], 50) == 2
    assert percentile(list(range(1, 101)), 95) == 95
