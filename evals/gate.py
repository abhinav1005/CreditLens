"""CI regression gate: is this smoke run worse than the committed baseline?

    uv run python -m evals gate <run_id> [--comment-file gate.md]

Fails (exit 1) if either:
- the overall pass rate dropped by more than `gate.max_overall_drop_points`, or
- any category lost `gate.max_lost_per_category` or more cases that passed in the baseline.

A regression is defined case by case ("this case used to pass and now fails"), not as a
percentage per category: with ~6 smoke cases per category, one flaky case would otherwise
swing a category by 17 points. The markdown it writes is posted as the PR comment.
"""

from dataclasses import dataclass
from pathlib import Path

from evals.baseline import BASELINE_DIR
from evals.compare import compare_results, load_results, render_comparison


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]
    comparison: dict
    markdown: str


def evaluate_gate(
    baseline: dict[str, dict],
    run: dict[str, dict],
    *,
    max_overall_drop_points: float,
    max_lost_per_category: int,
    names: tuple[str, str] = ("baseline", "this PR"),
) -> GateResult:
    diff = compare_results(baseline, run)
    reasons = []
    missing = sorted(set(baseline) - set(run))
    if missing:
        reasons.append(
            f"{len(missing)} baseline case(s) missing from this run: {', '.join(missing[:5])}"
        )
    if diff["n_shared"]:
        drop = 100 * (diff["a_pass_rate"] - diff["b_pass_rate"])
        if drop > max_overall_drop_points:
            reasons.append(
                f"overall pass rate dropped {drop:.1f} points (limit {max_overall_drop_points:g})"
            )
    for cat, c in diff["per_category"].items():
        if c["lost"] >= max_lost_per_category:
            reasons.append(
                f"`{cat}` lost {c['lost']} baseline-passing case(s)"
                f" (limit: fewer than {max_lost_per_category})"
            )
    passed = not reasons
    header = "## ✅ Eval gate passed" if passed else "## ❌ Eval gate failed"
    body = [header, ""]
    body += [f"- {r}" for r in reasons] or ["- No regressions against the committed baseline."]
    body += [
        "",
        render_comparison(diff, *names),
        "_Smoke suite vs `reports/baseline/smoke/`. Change the baseline only with "
        "`python -m evals baseline <run_id>` in a reviewed PR._",
    ]
    return GateResult(passed, reasons, diff, "\n".join(body) + "\n")


def gate_run(run_dir: Path, baseline_dir: Path = BASELINE_DIR) -> GateResult:
    from assistant.config import load_config

    config = load_config()
    return evaluate_gate(
        load_results(baseline_dir),
        load_results(run_dir),
        max_overall_drop_points=config.gate.max_overall_drop_points,
        max_lost_per_category=config.gate.max_lost_per_category,
        names=(f"baseline ({baseline_dir.name})", run_dir.name),
    )
