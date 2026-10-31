"""Compare two eval runs: what got worse, what got better.

    uv run python -m evals compare <run_a> <run_b>

A run is a run_id (looked up in reports/ and reports/history/) or a path to a run folder.
Cases are matched by case_id; only cases present in both runs are compared.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIRS = [ROOT / "reports", ROOT / "reports" / "history", ROOT / "reports" / "baseline"]


def find_run(ref: str) -> Path:
    path = Path(ref)
    if (path / "results.jsonl").exists():
        return path
    for d in SEARCH_DIRS:
        if (d / ref / "results.jsonl").exists():
            return d / ref
    raise FileNotFoundError(f"no run {ref!r} in {[str(d) for d in SEARCH_DIRS]}")


def load_results(run_dir: Path) -> dict[str, dict]:
    return {
        r["case_id"]: r
        for r in map(json.loads, (run_dir / "results.jsonl").read_text().splitlines())
    }


def failing_checks(row: dict) -> list[str]:
    return [c["name"] for c in row["checks"] if not c["passed"]] or [row.get("status", "failed")]


def compare_results(a: dict[str, dict], b: dict[str, dict]) -> dict:
    shared = sorted(set(a) & set(b))
    newly_failing = [
        {"case_id": cid, "category": b[cid]["category"], "checks": failing_checks(b[cid])}
        for cid in shared
        if a[cid]["passed"] and not b[cid]["passed"]
    ]
    newly_passing = [
        {"case_id": cid, "category": b[cid]["category"]}
        for cid in shared
        if not a[cid]["passed"] and b[cid]["passed"]
    ]
    categories = sorted({a[c]["category"] for c in shared})
    per_category = {}
    for cat in categories:
        ids = [c for c in shared if a[c]["category"] == cat]
        pa = sum(a[c]["passed"] for c in ids)
        pb = sum(b[c]["passed"] for c in ids)
        per_category[cat] = {
            "n": len(ids),
            "a_passed": pa,
            "b_passed": pb,
            "lost": sum(1 for c in ids if a[c]["passed"] and not b[c]["passed"]),
        }
    total_a = sum(a[c]["passed"] for c in shared)
    total_b = sum(b[c]["passed"] for c in shared)
    return {
        "n_shared": len(shared),
        "only_in_a": sorted(set(a) - set(b)),
        "only_in_b": sorted(set(b) - set(a)),
        "a_pass_rate": round(total_a / len(shared), 4) if shared else None,
        "b_pass_rate": round(total_b / len(shared), 4) if shared else None,
        "per_category": per_category,
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
    }


def render_comparison(diff: dict, name_a: str, name_b: str) -> str:
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"  # noqa: E731
    lines = [
        f"**{name_a}** → **{name_b}** ({diff['n_shared']} shared cases)",
        "",
        f"Overall: {pct(diff['a_pass_rate'])} → {pct(diff['b_pass_rate'])}",
        "",
        "| Category | Before | After | Lost |",
        "|---|---:|---:|---:|",
    ]
    for cat, c in diff["per_category"].items():
        lines.append(
            f"| {cat} | {c['a_passed']}/{c['n']} | {c['b_passed']}/{c['n']} | {c['lost']} |"
        )
    lines += ["", f"### Newly failing ({len(diff['newly_failing'])})", ""]
    lines += [
        f"- `{f['case_id']}` [{f['category']}]: " + ", ".join(f"`{c}`" for c in f["checks"][:4])
        for f in diff["newly_failing"]
    ] or ["- none"]
    lines += ["", f"### Newly passing ({len(diff['newly_passing'])})", ""]
    lines += [f"- `{p['case_id']}` [{p['category']}]" for p in diff["newly_passing"]] or ["- none"]
    return "\n".join(lines) + "\n"
