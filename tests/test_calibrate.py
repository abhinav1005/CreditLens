import pytest

from assistant.config import Usage
from evals.calibrate import agreement, bootstrap_ci, calibrate, kappa
from evals.judge import DIMENSIONS, JudgeResult
from evals.labeling import load_pool


def test_kappa_by_hand():
    # 10 items: agree on 8 (4 fail, 4 pass), disagree on 2.
    # p_o = 0.8; human fail rate 0.5, judge fail rate 0.5 → p_e = 0.5; kappa = 0.6.
    human = ["fail"] * 5 + ["pass"] * 5
    judge = ["fail"] * 4 + ["pass"] + ["fail"] + ["pass"] * 4
    assert kappa(human, judge) == pytest.approx(0.6)
    m = agreement(human, judge)
    assert m["precision_fail"] == 0.8 and m["recall_fail"] == 0.8 and m["accuracy"] == 0.8
    assert m["confusion"] == {"human_fail": [4, 1], "human_pass": [1, 4]}


def test_kappa_undefined_for_single_class():
    assert kappa(["pass"] * 4, ["pass"] * 4) is None


def test_bootstrap_ci_brackets_point_estimate():
    human = (["fail"] * 5 + ["pass"] * 5) * 4
    judge = (["fail"] * 4 + ["pass"] + ["fail"] + ["pass"] * 4) * 4
    low, high = bootstrap_ci(human, judge)
    assert low < 0.6 < high


def test_calibrate_end_to_end_with_fake_judge(tmp_path):
    pool = load_pool()[:12]
    split = {item["item_id"]: ("test" if i < 4 else "dev") for i, item in enumerate(pool)}
    labels = [
        {
            "item_id": it["item_id"],
            "labeler": "h1",
            "verdicts": {d: ("fail" if i % 2 else "pass") for d in DIMENSIONS},
        }
        for i, it in enumerate(pool)
    ]
    calls = []

    def fake_judge(case, out, *, config, version):
        calls.append(case.id)
        i = len(calls) - 1
        v = "fail" if i % 2 else "pass"  # agrees with every label
        return JudgeResult(
            {d: {"verdict": v, "rationale": "r"} for d in DIMENSIONS},
            Usage(),
            0.001,
            "claude-sonnet-5-5",
            "judge:v1",
            "h",
            0,
            [],
        )

    report = calibrate(
        "v1",
        "h1",
        max_cost_usd=1,
        cache_dir=tmp_path,
        judge=fake_judge,
        labels=labels,
        pool=pool,
        split=split,
    )
    assert report["n_judged"] == 12
    assert report["results"]["all"]["compliance"]["kappa"] == 1.0
    assert report["results"]["test"]["compliance"]["n"] == 4
    assert "written_by_sonnet" in report["results"] or "written_by_haiku" in report["results"]
    # Second run is fully cached: the judge isn't called again.
    calibrate(
        "v1",
        "h1",
        max_cost_usd=1,
        cache_dir=tmp_path,
        judge=fake_judge,
        labels=labels,
        pool=pool,
        split=split,
    )
    assert len(calls) == 12


def test_hand_kappa_matches_sklearn():
    import random

    from sklearn.metrics import cohen_kappa_score

    rng = random.Random(1)
    for _ in range(50):
        n = rng.randint(5, 40)
        human = [rng.choice(["pass", "fail"]) for _ in range(n)]
        judge = [rng.choice(["pass", "fail"]) for _ in range(n)]
        mine = kappa(human, judge)
        if mine is not None:
            assert mine == pytest.approx(cohen_kappa_score(human, judge))
