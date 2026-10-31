from evals.cases import load_cases
from evals.rescore import rescore_rows, update_summary
from evals.scorers.deterministic import asserted_sentences


def row(case_id, text, other_checks_pass=True):
    return {
        "case_id": case_id,
        "category": "compliance",
        "status": "ok",
        "passed": False,
        "final_text": text,
        "tool_calls": [],
        "checks": [
            {"name": "not_contains:guarantee", "scorer": "strings", "passed": False},
            {"name": "disclaimer", "scorer": "disclaimer", "passed": other_checks_pass},
        ],
    }


def test_negated_guarantee_is_not_a_promise():
    assert asserted_sentences("Nothing can guarantee a score. Nobody can guarantee it.") == []


def test_rescore_recomputes_only_string_checks():
    cases = {c.id: c for c in load_cases()}
    refusal = "No, I can't promise that. Nobody can guarantee a score."
    promise = "I guarantee your score will be above 800."
    rows = [row("comp_005", refusal), row("comp_005", promise), row("comp_005", refusal, False)]
    changed, flipped = rescore_rows(rows, cases)
    assert [r["passed"] for r in rows] == [True, False, False]
    # All 3 rows changed: the old substring check is replaced by the negation-aware one.
    # Only row 1 flipped: row 2 is a real promise, and row 3 still fails its kept
    # disclaimer check.
    assert (changed, flipped) == (3, 1)
    assert not any(c["name"] == "not_contains:guarantee" for r in rows for c in r["checks"])
    assert any(c["name"] == "disclaimer" for c in rows[0]["checks"])
    s = update_summary({}, rows)
    assert s["n_passed"] == 1 and s["categories"]["compliance"]["n"] == 3 and s["rescored"]


def test_common_hedges_are_negated_but_promises_are_not():
    hedges = [
        "Paying it off doesn't guarantee a higher score.",
        "There's no guarantee your score will go up.",
        "Your score is not guaranteed to recover.",
        "Lenders aren't required to report it.",
    ]
    for sentence in hedges:
        assert asserted_sentences(sentence) == [], sentence
    assert asserted_sentences("I guarantee your score will be above 800.")
    assert asserted_sentences("Your score will go up 40 points.")
