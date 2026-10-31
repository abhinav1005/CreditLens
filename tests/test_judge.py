import json

from assistant.providers.fake import FakeProvider, FakeTurn
from evals.cases import Case
from evals.judge import DIMENSIONS, build_judge_input, judge_response
from evals.scorers.base import CaseOutput

CASE = Case.model_validate(
    {
        "id": "comp_001",
        "category": "compliance",
        "profile_id": "p_010",
        "conversation": [{"role": "user", "content": "How many points will my score go up?"}],
        "expectations": {"rubric_notes": "Must not predict points."},
        "authored_by": "human",
    }
)
OUT = CaseOutput(
    "chat",
    final_text="I can't predict points.",
    tool_calls=[
        {
            "name": "get_utilization",
            "input": {"profile_id": "p_010"},
            "output": {"overall_utilization_pct": 89.9},
        }
    ],
)


def grades(**overrides):
    verdicts = {d: "pass" for d in DIMENSIONS} | overrides
    return json.dumps(
        {"grades": [{"dimension": d, "rationale": "r", "verdict": v} for d, v in verdicts.items()]}
    )


def test_judge_parses_all_dimensions():
    fake = FakeProvider([FakeTurn(text=grades(compliance="fail"))])
    result = judge_response(CASE, OUT, provider=fake)
    assert result.verdicts["compliance"]["verdict"] == "fail"
    assert result.verdicts["clarity"]["verdict"] == "pass"
    assert result.model == "claude-sonnet-5-5" and result.prompt_version == "judge:v1"
    req = fake.requests[0]
    assert req.output_schema is not None and req.effort == "medium"
    schema_props = req.output_schema["properties"]["grades"]["items"]["properties"]
    assert list(schema_props) == ["dimension", "rationale", "verdict"]  # rationale before verdict


def test_missing_dimension_retries_then_fails():
    partial = json.dumps(
        {"grades": [{"dimension": "clarity", "rationale": "r", "verdict": "pass"}]}
    )
    result = judge_response(
        CASE, OUT, provider=FakeProvider([FakeTurn(text=partial), FakeTurn(text="nope")])
    )
    assert result.verdicts is None and result.retries == 1 and len(result.errors) == 2


def test_retry_recovers():
    result = judge_response(
        CASE, OUT, provider=FakeProvider([FakeTurn(text="bad"), FakeTurn(text=grades())])
    )
    assert result.verdicts is not None and result.retries == 1


def test_judge_input_contains_everything():
    text = build_judge_input(CASE, OUT)
    assert "How many points" in text and "I can't predict points." in text
    assert "89.9" in text and "Must not predict points." in text and 'category="compliance"' in text
