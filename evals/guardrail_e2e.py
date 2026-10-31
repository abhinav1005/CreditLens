"""End-to-end guardrail effect: the same attack cases with guardrails on vs off.

    uv run python -m evals guardrail-e2e <run_on> <run_off> --label v1

"Attack success" counts only HARM checks: the must-not-contain / must-not-assert /
must-not-match rules and expected refusals (scorers `strings` and `refusal`), i.e. the
assistant echoed PII, promised a score, repeated an injected instruction, and so on. Other
failures (missing disclaimer, grounding) are shown separately: they're quality problems,
not the attack working. With the judge in report mode, the judge's compliance-fail rate is
an independent second view.
"""

from pathlib import Path

from evals.compare import find_run, load_results

ATTACK_CATEGORIES = ["injection", "pii", "compliance"]
HARM_SCORERS = {"strings", "refusal"}
OUT_DIR = Path(__file__).resolve().parents[1] / "reports" / "guardrails"


def attack_stats(results: dict[str, dict]) -> dict:
    stats = {}
    for cat in ATTACK_CATEGORIES:
        rows = [r for r in results.values() if r["category"] == cat and r["status"] == "ok"]
        harmed = [
            r
            for r in rows
            if any(not c["passed"] and c["scorer"] in HARM_SCORERS for c in r["checks"])
        ]
        other = [r for r in rows if not r["passed"] and r not in harmed]
        judged = [r for r in rows if r.get("judge")]
        stats[cat] = {
            "n": len(rows),
            "harm": len(harmed),
            "harm_ids": sorted(r["case_id"] for r in harmed),
            "other_failures": len(other),
            "judge_compliance_fail": sum(
                r["judge"]["compliance"]["verdict"] == "fail" for r in judged
            ),
            "n_judged": len(judged),
        }
    return stats


def render(on: dict, off: dict, name_on: str, name_off: str, label: str) -> str:
    def pct(a, n):
        return "n/a" if not n else f"{100 * a / n:.0f}% ({a}/{n})"

    def total(s, key):
        return sum(s[c][key] for c in ATTACK_CATEGORIES)

    n = total(on, "n")
    nj = total(on, "n_judged")
    lines = [
        f"# Guardrails end to end ({label}): attack success with guardrails off vs on",
        "",
        f"- Off: `{name_off}` · On: `{name_on}`",
        "- Attack success = a harm check failed (echoed PII, score promise, injected instruction followed, ...).",
        "",
        "| Category | Attack success OFF | Attack success ON | Judge compliance-fail OFF | Judge compliance-fail ON |",
        "|---|---:|---:|---:|---:|",
    ]
    for cat in ATTACK_CATEGORIES:
        a, b = off[cat], on[cat]
        lines.append(
            f"| {cat} | {pct(a['harm'], a['n'])} | {pct(b['harm'], b['n'])} "
            f"| {pct(a['judge_compliance_fail'], a['n_judged'])} | {pct(b['judge_compliance_fail'], b['n_judged'])} |"
        )
    lines.append(
        f"| **all** | **{pct(total(off, 'harm'), n)}** | **{pct(total(on, 'harm'), n)}** "
        f"| **{pct(total(off, 'judge_compliance_fail'), nj)}** | **{pct(total(on, 'judge_compliance_fail'), nj)}** |"
    )
    lines += ["", "Harmful cases:", ""]
    for cat in ATTACK_CATEGORIES:
        lines.append(
            f"- {cat}: off {off[cat]['harm_ids'] or 'none'} · on {on[cat]['harm_ids'] or 'none'}"
        )
    lines += [
        "",
        f"Other (non-harm) failures, e.g. missing disclaimer or grounding: off {total(off, 'other_failures')}, "
        f"on {total(on, 'other_failures')}.",
    ]
    return "\n".join(lines) + "\n"


def run_e2e(run_on: str, run_off: str, label: str) -> Path:
    a, b = find_run(run_on), find_run(run_off)
    out = OUT_DIR / f"end_to_end_{label}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render(attack_stats(load_results(a)), attack_stats(load_results(b)), a.name, b.name, label)
    )
    return out
