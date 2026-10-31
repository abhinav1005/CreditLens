"""Model comparison: quality × cost × latency.

    uv run python -m evals latency --models claude-sonnet-5-5,claude-haiku-5-5 --tags smoke
    uv run python -m evals matrix --models claude-sonnet-5-5,claude-haiku-5-5,claude-haiku-4-5-20251001

`latency` runs a fixed subset ONE CASE AT A TIME with fresh model calls (cached answers are
ignored), so the numbers aren't distorted by parallel load or cache hits. It writes
reports/latency/<model>.json.

`matrix` runs the golden suite per model (cached answers are reused) and writes
reports/model-comparison.{md,json}: pass rate per category, judge pass rates, cost per case,
and latency from the sequential run when there is one.
"""

import json
from pathlib import Path

from evals.runner import percentile, run_suite

ROOT = Path(__file__).resolve().parents[1]
LATENCY_DIR = ROOT / "reports" / "latency"
COMPARISON = ROOT / "reports" / "model-comparison"
JUDGE_DIMS = ["helpfulness", "compliance", "groundedness"]


def latency_run(cases, model: str, *, max_cost_usd: float, label: str = "", **kwargs) -> dict:
    summary = run_suite(
        cases,
        suite="latency",
        model=model,
        prompt_version=kwargs.pop("prompt_version", "v1"),
        max_cost_usd=max_cost_usd,
        concurrency=1,
        read_cache=False,
        run_id=f"latency-{model}{label}",
        **kwargs,
    )
    rows = [
        json.loads(line)
        for line in (Path(summary["out_dir"]) / "results.jsonl").read_text().splitlines()
    ]
    ok = [r for r in rows if r["status"] == "ok" and r["latency_ms"] is not None]
    total = [r["latency_ms"] for r in ok]
    ttft = [r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]
    result = {
        "model": model,
        "label": label,
        "n": len(ok),
        "total_ms": {"p50": percentile(total, 50), "p95": percentile(total, 95)},
        "ttft_ms": {"p50": percentile(ttft, 50), "p95": percentile(ttft, 95)},
        "cost_usd": summary["cost"]["api_spend_this_run_usd"],
        "run_id": summary["run_id"],
        "settings": {
            "prompt_caching": kwargs.get("prompt_caching"),
            "guardrails": kwargs.get("guardrails_enabled"),
        },
    }
    LATENCY_DIR.mkdir(parents=True, exist_ok=True)
    (LATENCY_DIR / f"{model}{label}.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def matrix(cases, models: list[str], *, max_cost_usd: float, judge_mode: str = "report") -> dict:
    rows = []
    for model in models:
        s = run_suite(
            cases,
            suite="golden",
            model=model,
            prompt_version="v1",
            max_cost_usd=max_cost_usd,
            judge_mode=judge_mode,
            run_id=f"matrix-{model}",
        )
        lat_path = LATENCY_DIR / f"{model}.json"
        latency = json.loads(lat_path.read_text()) if lat_path.exists() else None
        judge = s.get("judge", {})
        judge_overall = {}
        if judge.get("pass_rates"):
            results = [
                json.loads(line)
                for line in (Path(s["out_dir"]) / "results.jsonl").read_text().splitlines()
            ]
            for dim in JUDGE_DIMS:
                verdicts = [r["judge"][dim]["verdict"] == "pass" for r in results if r.get("judge")]
                judge_overall[dim] = round(sum(verdicts) / len(verdicts), 4) if verdicts else None
        rows.append(
            {
                "model": model,
                "run_id": s["run_id"],
                "overall_pass_rate": s["overall_pass_rate"],
                "categories": {k: v["pass_rate"] for k, v in s["categories"].items()},
                "judge": judge_overall,
                "mean_cost_per_case_usd": s["cost"]["mean_per_case_usd"],
                "latency": latency,
                "spend_usd": round(
                    s["cost"]["api_spend_this_run_usd"] + judge.get("spend_usd", 0), 4
                ),
            }
        )
    report = {
        "suite": "golden",
        "n_cases": len(cases),
        "pricing_as_of": s["pricing_as_of"],
        "rows": rows,
    }
    COMPARISON.parent.mkdir(parents=True, exist_ok=True)
    COMPARISON.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    COMPARISON.with_suffix(".md").write_text(render(report))
    return report


def render(report: dict) -> str:
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"  # noqa: E731
    ms = lambda x: "n/a" if x is None else f"{x / 1000:.1f}s"  # noqa: E731
    rows = report["rows"]
    cats = sorted({c for r in rows for c in r["categories"]})
    lines = [
        "# Model comparison",
        "",
        f"Golden suite ({report['n_cases']} cases), prompt v1, guardrails on. Pricing as of {report['pricing_as_of']}.",
        "Reproduce: `uv run python -m evals latency --models <ids> --tags smoke` then `uv run python -m evals matrix --models <ids>`.",
        "",
        "| Model | Pass rate | Judge: helpful | Judge: compliant | Judge: grounded | Cost / case | Latency p50 / p95 (total) | TTFT p50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lat = r["latency"]
        lat_txt = f"{ms(lat['total_ms']['p50'])} / {ms(lat['total_ms']['p95'])}" if lat else "n/a"
        ttft = ms(lat["ttft_ms"]["p50"]) if lat else "n/a"
        cost = r["mean_cost_per_case_usd"]
        lines.append(
            f"| `{r['model']}` | {pct(r['overall_pass_rate'])} | {pct(r['judge'].get('helpfulness'))} | "
            f"{pct(r['judge'].get('compliance'))} | {pct(r['judge'].get('groundedness'))} | "
            f"{'n/a' if cost is None else f'${cost:.4f}'} | {lat_txt} | {ttft} |"
        )
    lines += [
        "",
        "## Pass rate by category",
        "",
        "| Category | " + " | ".join(f"`{r['model']}`" for r in rows) + " |",
        "|---|" + "---:|" * len(rows),
    ]
    for c in cats:
        lines.append(f"| {c} | " + " | ".join(pct(r["categories"].get(c)) for r in rows) + " |")
    lines += [
        "",
        "Latency comes from a sequential run of the smoke subset with fresh calls (`reports/latency/`);"
        " costs include the assistant's guardrail classifier calls but not the judge.",
    ]
    return "\n".join(lines) + "\n"
