from evals.gate import evaluate_gate


def rows(spec):
    """spec: {case_id: (category, passed)}"""
    return {
        cid: {
            "case_id": cid,
            "category": cat,
            "passed": ok,
            "status": "ok",
            "checks": [] if ok else [{"name": "disclaimer", "passed": False}],
        }
        for cid, (cat, ok) in spec.items()
    }


BASE = rows(
    {f"t{i}": ("tool_use", True) for i in range(6)}
    | {f"c{i}": ("compliance", True) for i in range(6)}
)
KW = {"max_overall_drop_points": 5, "max_lost_per_category": 2}


def test_identical_run_passes():
    result = evaluate_gate(BASE, dict(BASE), **KW)
    assert result.passed and "✅" in result.markdown


def test_one_flaky_case_is_tolerated_by_category_rule():
    run = dict(BASE) | rows({"t0": ("tool_use", False)})
    result = evaluate_gate(BASE, run, **{**KW, "max_overall_drop_points": 10})
    assert result.passed  # 1 lost < 2, and 8.3-point drop < 10


def test_two_lost_in_a_category_fails_with_readable_diff():
    run = dict(BASE) | rows({"t0": ("tool_use", False), "t1": ("tool_use", False)})
    result = evaluate_gate(BASE, run, **{**KW, "max_overall_drop_points": 50})
    assert not result.passed
    assert any("`tool_use` lost 2" in r for r in result.reasons)
    assert "`t0` [tool_use]: `disclaimer`" in result.markdown and "❌" in result.markdown


def test_overall_drop_fails():
    run = dict(BASE) | rows({"t0": ("tool_use", False), "c0": ("compliance", False)})
    result = evaluate_gate(BASE, run, **KW)  # 2/12 = 16.7-point drop, 1 lost per category
    assert not result.passed and any("overall pass rate dropped" in r for r in result.reasons)


def test_missing_cases_fail():
    run = {k: v for k, v in BASE.items() if k != "t5"}
    assert not evaluate_gate(BASE, run, **KW).passed


def test_committed_baseline_blocks_the_degraded_prompt():
    """M2 done-when, as a test: the real v1-degraded smoke run fails the real gate."""
    from pathlib import Path

    from assistant.config import load_config
    from evals.baseline import BASELINE_DIR
    from evals.compare import load_results

    # A real smoke run of Sonnet 5.5 on prompts/system/v1-degraded.md, saved as a fixture.
    degraded = load_results(Path(__file__).parent / "fixtures" / "degraded_smoke")
    gate = load_config().gate
    result = evaluate_gate(
        load_results(BASELINE_DIR),
        degraded,
        max_overall_drop_points=gate.max_overall_drop_points,
        max_lost_per_category=gate.max_lost_per_category,
    )
    assert not result.passed
    assert any("tool_use" in r for r in result.reasons)
