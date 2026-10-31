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
    lines += (
        [
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
        ]
        + _judge_section(s.get("judge", {"mode": "off"}))
        + _guardrail_section(s.get("guardrails"))
        + [
            "## Failed checks by scorer",
            "",
        ]
    )
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


def _judge_section(judge: dict) -> list[str]:
    if judge.get("mode", "off") == "off":
        return []
    counted = "counted toward pass/fail" if judge["mode"] == "gate" else "shown only, not counted"
    dims = judge["dimensions"]
    lines = [
        f"## LLM judge (`{judge['version']}`, `{judge['model']}`)",
        "",
        f"Mode `{judge['mode']}`: {counted}.",
        "",
        f"Judge spend this run: ${judge['spend_usd']:.4f}",
        "",
        "| Category | " + " | ".join(dims) + " |",
        "|---|" + "---:|" * len(dims),
    ]
    for cat, rates in judge["pass_rates"].items():
        lines.append(f"| {cat} | " + " | ".join(_pct(rates.get(d)) for d in dims) + " |")
    return lines + [""]


def _guardrail_section(g: dict | None) -> list[str]:
    """Per-guardrail test-set precision/recall (from reports/guardrails/) + what fired here."""
    import json
    from pathlib import Path

    if not g:
        return []
    enabled = g["config"].get("enabled")
    lines = [f"## Guardrails ({'on' if enabled else 'OFF'})", ""]
    reports = Path(__file__).resolve().parents[1] / "reports" / "guardrails"
    rows = []
    for name in ["pii", "injection", "compliance"]:
        path = reports / f"{name}-test.json"
        if path.exists():
            r = json.loads(path.read_text())
            fp = r.get("false_positive_rate", r.get("negative_false_positive_rate"))
            rows.append(
                f"| {name} | {_pct(r['recall'])} | {_pct(r.get('precision'))} | {_pct(fp)} |"
            )
    if rows:
        lines += [
            "Measured on each guardrail's held-out test set (`python -m evals guardrail <name>`):",
            "",
            "| Guardrail | Recall | Precision | False-positive rate |",
            "|---|---:|---:|---:|",
            *rows,
            "",
        ]
    lines.append(
        f"In this run: {g['blocked_turns']} blocked turn(s); compliance checked "
        f"{g['compliance_checked']}, regenerated {g['compliance_regenerated']}, "
        f"fell back {g['compliance_fallbacks']}."
    )
    if g["decision_counts"]:
        lines += [""] + [f"- `{k}`: {v}" for k, v in g["decision_counts"].items()]
    return lines + [""]
