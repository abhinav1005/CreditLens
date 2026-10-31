from evals.experiments import build, gate_tolerance, is_current


def test_gate_tolerance_matches_the_gate_rule():
    # 5-point limit: losing 2 of 41 is a 4.9-point drop (allowed), 3 is 7.3 (fails).
    assert gate_tolerance(41) == 2
    assert gate_tolerance(100) == 5


def test_experiment_numbers_are_consistent():
    data = build()
    rel = data["reliability"]
    assert rel["always_pass"] + rel["always_fail"] + len(rel["flaky"]) == rel["n_cases"]
    assert rel["min"] <= rel["mean"] <= rel["max"]
    assert len(rel["smoke_passed"]) == len(rel["runs"])
    for row in data["defense"]:
        assert 0 <= row["harm"] <= row["n"]


def test_committed_experiments_report_is_current():
    assert is_current(), "run `uv run python -m evals experiments`"
