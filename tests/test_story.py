import copy

from evals.dashboard import build
from evals.story import build_story, check_claims, gaps


def test_the_data_still_supports_the_wording():
    # If this fails, the reports changed and a sentence in evals/story.py is no longer true.
    assert check_claims(build()) == []


def test_a_stale_claim_is_caught():
    data = copy.deepcopy(build())
    for row in data["experiments"]["ablation"]:
        row["categories"]["refusal"] = 1.0
    assert "safety rules matter" in check_claims(data)


def test_story_numbers_are_read_from_the_data():
    data = copy.deepcopy(build())
    data["golden"]["n_cases"] = 999
    assert "999 test questions" in build_story(data)["steps"][0]["text"]


def test_story_builds_without_experiments():
    data = copy.deepcopy(build())
    data["experiments"] = None
    assert [f["id"] for f in build_story(data)["findings"]] == ["grader"]


def test_gaps_disappear_once_fixed():
    data = copy.deepcopy(build())
    data["golden"]["human_reviewed"] = data["golden"]["n_cases"]
    data["calibration"]["rows"] = [{"judge_version": "v1"}]
    for row in data["guardrails"]["rows"]:
        row["recall"] = 1.0
    data["experiments"]["reliability"]["smoke_swing"] = 0
    assert gaps(data) == []
