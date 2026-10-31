"""Render a run's summary + results as report.md."""


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _ms(x) -> str:
    return "n/a" if x is None else f"{x:,.0f} ms"


def render_report(summary: dict, results: list[dict]) -> str:
    s = summary
    dirty = " (dirty)" if s["git"]["dirty"] else ""
    lines = [
        f"# Eval report: {s['run_id']}",
        "",
        f"- Suite: `{s['suite']}` · Model: `{s['model']}`",
        f"- Prompt: `{s['prompt_version']}` (hash `{s['prompt_hash']}`)",
        f"- Commit: `{s['git']['commit']}`{dirty} · Pricing as of {s['pricing_as_of']}",
        f"- Cases: {s['n_cases']} · Cache hits: {s['cache_hits']} · Status: {s['status_counts']}",
    ]
    if s["unreviewed_cases"]:
        lines.append(
            f"- ⚠️ {s['unreviewed_cases']} case(s) are LLM-drafted and not yet human-reviewed."
        )
    lines += [
        "",
        f"## Overall pass rate: {_pct(s['overall_pass_rate'])} ({s['n_passed']}/{s['n_cases']})",
        "",
        "| Category | Passed | Pass rate |",
        "|---|---:|---:|",
    ]
    for cat, c in s["categories"].items():
        lines.append(f"| {cat} | {c['passed']}/{c['n']} | {_pct(c['pass_rate'])} |")
    cost, lat = s["cost"], s["latency_ms"]
    lines += [
        "",
        "## Cost and latency",
        "",
        f"- Measured cost: ${cost['measured_total_usd']:.4f} total, "
        + (
            f"${cost['mean_per_case_usd']:.5f} per case"
            if cost["mean_per_case_usd"] is not None
            else "n/a per case"
        ),
        f"- API spend this run: ${cost['api_spend_this_run_usd']:.4f}"
        f" (estimate before run: ${cost['pre_run_estimate_usd']:.4f})",
        f"- Latency p50 {_ms(lat['p50'])}, p95 {_ms(lat['p95'])} ({lat['note']})",
        "",
        "## Failed checks by scorer",
        "",
    ]
    if s["failed_checks_by_scorer"]:
        lines += [f"- {k}: {v}" for k, v in sorted(s["failed_checks_by_scorer"].items())]
    else:
        lines.append("- none")
    failures = [r for r in results if not r["passed"]]
    lines += ["", f"## Failing cases ({len(failures)})", ""]
    for r in failures:
        bad = [c for c in r["checks"] if not c["passed"]] or [{"name": r["status"], "detail": ""}]
        reasons = "; ".join(
            f"`{c['name']}`" + (f" ({c['detail']})" if c.get("detail") else "") for c in bad
        )
        lines.append(f"- **{r['case_id']}** [{r['category']}]: {reasons}")
    return "\n".join(lines) + "\n"
