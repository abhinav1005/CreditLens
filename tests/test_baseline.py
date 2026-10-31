import json

import pytest

from evals.baseline import set_baseline


def make_run(tmp_path, name, tags, errors=0):
    d = tmp_path / name
    d.mkdir()
    summary = {
        "run_id": name,
        "model": "m",
        "prompt_version": "v1",
        "prompt_hash": "h",
        "n_cases": 2,
        "overall_pass_rate": 0.5,
        "tags": tags,
        "status_counts": {"ok": 2 - errors, "error": errors},
        "git": {"commit": "abc"},
    }
    (d / "summary.json").write_text(json.dumps(summary))
    (d / "results.jsonl").write_text("")
    (d / "report.md").write_text("# r")
    return d


def test_sets_baseline_from_smoke_run(tmp_path):
    run = make_run(tmp_path, "r1", ["smoke"])
    meta = set_baseline(str(run), baseline_dir=tmp_path / "baseline")
    assert meta["run_id"] == "r1"
    assert (tmp_path / "baseline" / "baseline.json").exists() and (
        tmp_path / "baseline" / "results.jsonl"
    ).exists()


def test_refuses_non_smoke_or_errored_runs(tmp_path):
    with pytest.raises(ValueError):
        set_baseline(str(make_run(tmp_path, "full", [])), baseline_dir=tmp_path / "b")
    with pytest.raises(ValueError):
        set_baseline(
            str(make_run(tmp_path, "err", ["smoke"], errors=1)), baseline_dir=tmp_path / "b"
        )
