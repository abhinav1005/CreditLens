import json

import pytest
from pydantic import ValidationError

from evals.__main__ import main
from evals.cases import Case, load_cases

BASE = {
    "id": "tool_001",
    "category": "tool_use",
    "profile_id": "story_001",
    "conversation": [{"role": "user", "content": "What's my utilization?"}],
    "expectations": {
        "must_call_tools": [{"name": "get_utilization"}],
        "numeric_facts": [{"value": 40.8}],
    },
    "authored_by": "human",
}


def case(**overrides):
    return Case.model_validate({**BASE, **overrides})


def test_valid_case():
    assert case().expectations.numeric_facts[0].value == 40.8


@pytest.mark.parametrize(
    "overrides",
    [
        {"profile_id": "p_999"},
        {"conversation": []},
        {"conversation": [{"role": "assistant", "content": "hi"}]},
        {"expectations": {"must_call_tools": [{"name": "delete_account"}]}},
        {"expectations": {"must_not_match": ["("]}},
        {"kind": "insights"},  # insights cases have no conversation
        {"authored_by": "someone"},
        {"id": "Tool-1"},
        {"surprise": 1},
    ],
)
def test_invalid_cases_rejected(overrides):
    with pytest.raises((ValidationError, ValueError)):
        case(**overrides)


def test_insights_case():
    c = case(id="ins_001", kind="insights", category="insight_grounding", conversation=[])
    assert c.kind == "insights"


def test_load_reports_all_problems_and_duplicates(tmp_path):
    path = tmp_path / "g.jsonl"
    bad = {**BASE, "profile_id": "p_999"}
    path.write_text("\n".join(json.dumps(x) for x in [BASE, BASE, bad]) + "\n")
    with pytest.raises(ValueError) as err:
        load_cases(path)
    assert "line 3" in str(err.value) and "duplicate ids" in str(err.value)


def test_cli_validate(tmp_path, capsys):
    path = tmp_path / "g.jsonl"
    path.write_text(json.dumps({**BASE, "tags": ["smoke"]}) + "\n")
    assert main(["validate", str(path)]) == 0
    out = capsys.readouterr().out
    assert "1 valid cases" in out and "tool_use             1 / 30" in out
