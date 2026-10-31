"""The committed baseline the CI gate compares against.

    uv run python -m evals baseline <run_id>

Copies a smoke run into reports/baseline/smoke/ and records where it came from. This is
the only way the baseline changes, and it should happen in a reviewed PR that shows the
gate result against the OLD baseline, so nobody can quietly lower the bar.
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from evals.compare import find_run

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "reports" / "baseline" / "smoke"


def set_baseline(run_ref: str, baseline_dir: Path = BASELINE_DIR) -> dict:
    run_dir = find_run(run_ref)
    summary = json.loads((run_dir / "summary.json").read_text())
    if summary.get("tags") != ["smoke"]:
        raise ValueError(
            f"{run_dir.name} isn't a smoke run (tags={summary.get('tags')}); run with --tags smoke"
        )
    if summary.get("status_counts", {}).get("error"):
        raise ValueError(f"{run_dir.name} has errored cases; rerun before using it as a baseline")
    if baseline_dir.exists():
        shutil.rmtree(baseline_dir)
    baseline_dir.mkdir(parents=True)
    for name in ["results.jsonl", "summary.json", "report.md"]:
        shutil.copy(run_dir / name, baseline_dir / name)
    meta = {
        "run_id": summary["run_id"],
        "model": summary["model"],
        "prompt_version": summary["prompt_version"],
        "prompt_hash": summary["prompt_hash"],
        "n_cases": summary["n_cases"],
        "overall_pass_rate": summary["overall_pass_rate"],
        "set_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_commit": summary["git"]["commit"],
    }
    (baseline_dir / "baseline.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta
