from evals.cases import load_cases
from evals.labeler import label_items, render_item
from evals.labeling import load_pool

POOL = load_pool()
CASES = {c.id: c for c in load_cases()}


def run(keys, already=frozenset(), batch=25):
    answers, saved, shown = iter(keys), [], []
    n = label_items(
        POOL,
        CASES,
        set(already),
        "tester",
        batch=batch,
        read=lambda prompt: next(answers),
        write=shown.append,
        save=saved.append,
    )
    return n, saved, shown


def test_labels_one_item_then_quits():
    n, saved, shown = run(
        ["p", "f", "p", "x", "f", "too vague", "q"]
    )  # "x" is ignored and re-asked
    assert n == 1
    assert saved[0]["item_id"] == POOL[0]["item_id"]
    assert saved[0]["verdicts"] == {
        "helpfulness": "pass",
        "clarity": "fail",
        "compliance": "pass",
        "groundedness": "fail",
    }
    assert saved[0]["note"] == "too vague"


def test_skip_and_resume():
    n, saved, _ = run(["s", "p", "p", "p", "p", "", "q"], already={POOL[0]["item_id"]})
    assert n == 1 and saved[0]["item_id"] == POOL[2]["item_id"]  # POOL[0] done, POOL[1] skipped


def test_batch_limit():
    n, saved, _ = run(["p", "p", "p", "p", ""] * 3, batch=2)
    assert n == 2


def test_display_is_blind_to_model_and_prompt():
    item = POOL[0]
    text = render_item(item, CASES[item["case_id"]])
    assert item["model"] not in text and "v1-degraded" not in text and "judge" not in text.lower()
