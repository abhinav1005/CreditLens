import json

from evals.dashboard import build, is_current, render


def test_dashboard_numbers_come_from_reports():
    data = build()
    comparison = json.loads(open("reports/model-comparison.json").read())
    assert [r["pass_rate"] for r in data["models"]["rows"]] == [
        r["overall_pass_rate"] for r in comparison["rows"]
    ]
    assert data["golden"]["n_cases"] == sum(data["golden"]["by_category"].values())
    for section in ("models", "guardrails", "end_to_end", "variants", "gate", "calibration"):
        assert data[section]["source"].startswith("uv run python -m evals")


def test_render_is_deterministic():
    assert render(build()) == render(build())


def test_committed_dashboard_is_current():
    assert is_current(), "run `uv run python -m evals dashboard`"
