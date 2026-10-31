import json

from fastapi.testclient import TestClient

from assistant.api import create_app
from assistant.insights import InsightCardsWire, generate_insights
from assistant.providers.fake import FakeProvider, FakeTurn
from storage.sqlite import SQLiteStorage

GOOD = {
    "cards": [
        {
            "title": "High utilization",
            "summary": "Your overall utilization is 40.8%.",
            "factor_code": "UTILIZATION",
            "evidence": [
                {"tool": "get_utilization", "field": "overall_utilization_pct", "value": 40.8}
            ],
            "suggested_next_step": "Paying balances down before statement dates helps.",
            "disclaimer_required": True,
        }
    ]
}


def test_valid_cards_first_try():
    fake = FakeProvider([FakeTurn(text=json.dumps(GOOD))])
    result = generate_insights("story_001", provider=fake)
    assert result.retries == 0 and result.cards[0].factor_code == "UTILIZATION"
    assert [c["name"] for c in result.tool_calls] == [
        "get_credit_profile",
        "get_utilization",
        "get_score_history",
    ]
    assert fake.requests[0].output_schema == InsightCardsWire.model_json_schema()
    assert "40.8" in fake.requests[0].messages[0]["content"]


def test_invalid_then_valid_counts_one_retry():
    fake = FakeProvider([FakeTurn(text='{"cards": []}'), FakeTurn(text=json.dumps(GOOD))])
    result = generate_insights("story_001", provider=fake)
    assert result.retries == 1 and result.cards is not None
    assert "failed validation" in fake.requests[1].messages[-1]["content"]


def test_two_failures_give_no_cards():
    fake = FakeProvider([FakeTurn(text="not json"), FakeTurn(text='{"cards": [{"title": 1}]}')])
    result = generate_insights("story_001", provider=fake)
    assert result.cards is None and len(result.errors) == 2


def test_schema_forbids_extra_fields():
    schema = InsightCardsWire.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["InsightCard"]["additionalProperties"] is False


def test_insights_endpoint():
    app = create_app(
        provider_factory=lambda m: FakeProvider([FakeTurn(text=json.dumps(GOOD))]),
        storage=SQLiteStorage(":memory:"),
    )
    resp = TestClient(app).get("/insights/story_001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cards"][0]["title"] == "High utilization"
    assert body["meta"]["prompt_version"] == "insights:v1"


import os  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_insights_validate():
    result = generate_insights("story_001", model="claude-haiku-5-5")
    assert result.cards, result.errors
