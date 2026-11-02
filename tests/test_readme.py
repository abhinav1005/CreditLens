from evals.dashboard import build
from evals.readme import (
    RESULTS_END,
    RESULTS_START,
    is_current,
    render_results_doc,
    updated_readme,
)


def test_only_the_marked_block_changes():
    text = f"intro\n{RESULTS_START}\nSTALE-BLOCK\n{RESULTS_END}\noutro\n"
    new = updated_readme(text)
    assert new.startswith(f"intro\n{RESULTS_START}\n\n") and new.endswith(f"{RESULTS_END}\noutro\n")
    assert "STALE-BLOCK" not in new and "Still to do" in new
    assert updated_readme(new) == new  # idempotent


def test_every_table_moved_to_the_results_doc():
    assert "| Model |" in render_results_doc(build())


def test_committed_readme_is_current():
    assert is_current(), "run `uv run python -m evals readme`"
