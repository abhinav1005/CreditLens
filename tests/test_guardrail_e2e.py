from evals.guardrail_e2e import attack_stats


def row(cid, cat, failed_scorers, judge_fail=False):
    checks = [{"name": s, "scorer": s, "passed": False} for s in failed_scorers]
    return {
        "case_id": cid,
        "category": cat,
        "status": "ok",
        "passed": not failed_scorers,
        "checks": checks,
        "judge": {"compliance": {"verdict": "fail" if judge_fail else "pass"}},
    }


def test_only_harm_checks_count_as_attack_success():
    results = {
        r["case_id"]: r
        for r in [
            row("p1", "pii", ["strings"]),  # echoed PII → harm
            row("c1", "compliance", ["disclaimer"]),  # missing disclaimer → not harm
            row("i1", "injection", ["grounding"], judge_fail=True),
            row("i2", "injection", []),
        ]
    }
    s = attack_stats(results)
    assert (
        s["pii"]["harm"] == 1
        and s["compliance"]["harm"] == 0
        and s["compliance"]["other_failures"] == 1
    )
    assert s["injection"]["harm"] == 0 and s["injection"]["judge_compliance_fail"] == 1
