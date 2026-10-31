"""Rescore saved runs offline after a fix to the string checks (no API calls).

    uv run python -m evals rescore <run_id> [<run_id> ...]
    uv run python -m evals rescore --all          # every run in reports/ and reports/history/

Why only string checks: a saved results row keeps the answer text but not the full tool
outputs, so checks that need tool data (numeric grounding, tool calls) can't be recomputed
from it. String checks (must/must-not contain, match, assert) need only the answer text, so
when a case's string expectations or the negation list change, they can be recomputed
exactly. Every other check is kept as saved. Cached runs can instead be rescored fully by
rerunning them (`python -m evals run ...` with the same settings costs nothing).

The run's summary is updated in place (pass counts, categories, failed checks) and gets a
`rescored` note saying what was recomputed.
"""

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from evals.cases import DATASETS_DIR, load_cases
from evals.compare import SEARCH_DIRS
from evals.scorers.base import CaseOutput
from evals.scorers.deterministic import score_strings


def rescore_rows(rows: list[dict], cases: dict) -> tuple[int, int]:
    """Recompute string checks in place. Returns (rows whose checks changed, rows whose
    pass/fail flipped). A row can change without flipping, e.g. when another check still
    fails; it must still be saved, because reports such as attack harm read single checks."""
    changed = flipped = 0
    for row in rows:
        case = cases.get(row["case_id"])
        if case is None or row["status"] != "ok" or case.kind != "chat":
            continue
        out = CaseOutput(
            kind="chat",
            final_text=row["final_text"],
            tool_calls=row.get("tool_calls") or [],
            stop=row.get("stop", "complete"),
        )
        kept = [c for c in row["checks"] if c["scorer"] != "strings"]
        new_checks = kept + [c.to_dict() for c in score_strings(case, out)]
        changed += sorted(map(json.dumps, new_checks)) != sorted(map(json.dumps, row["checks"]))
        row["checks"] = new_checks
        passed = all(c["passed"] for c in row["checks"])
        flipped += passed != row["passed"]
        row["passed"] = passed
    return changed, flipped


def update_summary(summary: dict, rows: list[dict]) -> dict:
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    n = len(rows)
    summary.update(
        {
            "n_passed": sum(r["passed"] for r in rows),
            "overall_pass_rate": round(sum(r["passed"] for r in rows) / n, 4) if n else None,
            "categories": {
                cat: {
                    "n": len(rs),
                    "passed": sum(r["passed"] for r in rs),
                    "pass_rate": round(sum(r["passed"] for r in rs) / len(rs), 4),
                }
                for cat, rs in sorted(by_cat.items())
            },
            "failed_checks_by_scorer": dict(
                Counter(c["scorer"] for r in rows for c in r["checks"] if not c["passed"])
            ),
            "rescored": {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "what": "string checks recomputed from saved answers (evals/rescore.py)",
            },
        }
    )
    return summary


def rescore_run(run_dir: Path) -> tuple[int, int, int]:
    """Rescore one run folder. Returns (rows, changed, flipped)."""
    summary_path, results_path = run_dir / "summary.json", run_dir / "results.jsonl"
    summary = json.loads(summary_path.read_text())
    suite_path = DATASETS_DIR / f"{summary['suite']}.jsonl"
    if not suite_path.exists():  # e.g. the "latency" suite is a subset of golden
        suite_path = DATASETS_DIR / "golden.jsonl"
    cases = {c.id: c for c in load_cases(suite_path)}
    rows = [json.loads(line) for line in results_path.read_text().splitlines()]
    changed, flipped = rescore_rows(rows, cases)
    if changed:
        results_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        summary_path.write_text(json.dumps(update_summary(summary, rows), indent=2) + "\n")
    return len(rows), changed, flipped


def all_runs() -> list[Path]:
    dirs = [
        d for d in SEARCH_DIRS if d.name != "baseline"
    ]  # the baseline changes only via `evals baseline`
    return [
        run
        for d in dirs
        if d.is_dir()
        for run in sorted(d.iterdir())
        if (run / "results.jsonl").exists() and (run / "summary.json").exists()
    ]
