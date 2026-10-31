"""Promote a logged conversation into a golden case.

    uv run python -m evals promote <transcript_id> --category compliance \
        --note "Promised a 40-point rise" --must-not-contain "40 points"

The new case replays the conversation up to (and including) the user message that produced
the bad reply. Earlier turns become fixed history; only the final reply is regenerated
when the case runs. `source` is "promoted_from_transcript" and `authored_by` is "human",
since a person chose the transcript and wrote the expectations.
"""

import json
import re
from pathlib import Path

from evals.cases import GOLDEN_PATH, Case, Category, load_cases

ID_PREFIX = {
    Category.FACTUAL: "fact",
    Category.TOOL_USE: "tool",
    Category.INSIGHT_GROUNDING: "ins",
    Category.REFUSAL: "ref",
    Category.INJECTION: "inject",
    Category.PII: "pii",
    Category.COMPLIANCE: "comp",
}


def conversation_before_reply(messages: list[dict]) -> list[dict]:
    """Messages up to and including the last user message, without provider-native blocks."""
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    cleaned = []
    for m in messages[: last_user + 1]:
        m = {k: v for k, v in m.items() if k != "provider_blocks"}
        cleaned.append(m)
    return cleaned


def next_id(category: Category, existing: list[str]) -> str:
    prefix = ID_PREFIX[category]
    numbers = [int(m.group(1)) for i in existing if (m := re.fullmatch(rf"{prefix}_(\d{{3}})", i))]
    return f"{prefix}_{max(numbers, default=0) + 1:03d}"


def build_case(
    transcript,
    category: Category,
    note: str,
    must_not_contain: list[str],
    must_contain: list[str],
    existing_ids: list[str],
) -> dict:
    case = {
        "id": next_id(category, existing_ids),
        "category": category.value,
        "profile_id": transcript.profile_id,
        "conversation": conversation_before_reply(transcript.messages),
        "expectations": {
            "must_not_contain": must_not_contain,
            "must_contain": must_contain,
            "rubric_notes": note,
        },
        "tags": ["promoted"],
        "source": "promoted_from_transcript",
        "authored_by": "human",
        "notes": f"promoted from transcript {transcript.transcript_id}",
    }
    Case.model_validate(case)  # fail before writing anything
    return case


def append_case(case: dict, path: Path = GOLDEN_PATH) -> None:
    with path.open("a") as f:
        f.write(json.dumps(case, sort_keys=True) + "\n")


def promote(
    transcript_id: str,
    category: str,
    note: str,
    must_not_contain=(),
    must_contain=(),
    storage=None,
    golden_path: Path = GOLDEN_PATH,
) -> dict:
    """Append a case built from the transcript to the golden set. Used by the CLI and the
    web UI's promote button. Raises KeyError for an unknown transcript, ValueError for an
    invalid case (nothing is written then)."""
    if storage is None:
        from assistant.config import ROOT, load_config
        from storage.sqlite import SQLiteStorage

        storage = SQLiteStorage(ROOT / load_config().storage.sqlite_path)
    transcript = storage.get(transcript_id)
    if transcript is None:
        raise KeyError(f"no transcript {transcript_id}")
    case = build_case(
        transcript,
        Category(category),
        note,
        list(must_not_contain),
        list(must_contain),
        [c.id for c in load_cases(golden_path)],
    )
    append_case(case, golden_path)
    return case
