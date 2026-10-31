from evals.readme import RESULTS_END, RESULTS_START, is_current, updated_readme


def test_only_the_marked_block_changes():
    text = f"intro\n{RESULTS_START}\nSTALE-BLOCK\n{RESULTS_END}\noutro\n"
    new = updated_readme(text)
    assert new.startswith(f"intro\n{RESULTS_START}\n\n") and new.endswith(f"{RESULTS_END}\noutro\n")
    assert "STALE-BLOCK" not in new and "| Model |" in new
    assert updated_readme(new) == new  # idempotent


def test_committed_readme_is_current():
    assert is_current(), "run `uv run python -m evals readme`"
