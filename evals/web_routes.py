"""HTTP routes for the web UI's eval tools: blind labeling and promote-to-test.

They call the same functions as the CLI (`python -m evals label`, `python -m evals promote`),
so a label or a promoted case made in the browser is the same record the terminal makes.

Labeling stays blind: an item is sent without the judge's verdict, the model, the prompt
version, or the run it came from.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evals.cases import GOLDEN_PATH, Category, load_cases
from evals.judge import DIMENSIONS
from evals.labeler import (
    DIMENSION_HINTS,
    LABELS_PATH,
    TARGET,
    append_label,
    load_labels,
    make_label,
    next_unlabeled,
)
from evals.labeling import POOL_PATH, load_pool
from evals.promote import promote


class LabelIn(BaseModel):
    item_id: str
    labeler: str = Field(min_length=1, max_length=40)
    verdicts: dict[str, str]
    note: str = Field(default="", max_length=2000)


class PromoteIn(BaseModel):
    category: Category
    note: str = Field(min_length=1, max_length=2000)  # what was wrong → rubric_notes
    must_not_contain: list[str] = []
    must_contain: list[str] = []


def item_view(item: dict, case) -> dict:
    """What the labeler sees: the conversation, this turn's tool results, the reply."""
    record = item["record"]
    return {
        "item_id": item["item_id"],
        "case_id": case.id,
        "category": case.category.value,
        "kind": record["kind"],
        "conversation": case.conversation,
        "tool_calls": [
            {"name": c["name"], "input": c["input"], "output": c.get("output")}
            for c in record["tool_calls"]
        ],
        "reply": record["final_text"] if record["kind"] == "chat" else None,
        "cards": record.get("cards") if record["kind"] == "insights" else None,
        "rubric_notes": case.expectations.rubric_notes,
    }


def make_router(
    pool_path: Path = POOL_PATH,
    labels_path: Path = LABELS_PATH,
    storage=None,
    golden_path: Path = GOLDEN_PATH,
) -> APIRouter:
    router = APIRouter()

    @router.get("/labeling/dimensions")
    def dimensions() -> list[dict]:
        return [{"name": d, "hint": DIMENSION_HINTS[d]} for d in DIMENSIONS]

    @router.get("/labeling/next")
    def next_item(labeler: str, skip: str = "") -> dict:
        pool = load_pool(pool_path)
        mine = {lab["item_id"] for lab in load_labels(labels_path) if lab["labeler"] == labeler}
        item = next_unlabeled(pool, mine, set(filter(None, skip.split(","))))
        progress = {"done": len(mine), "target": TARGET, "pool_size": len(pool)}
        if item is None:
            return {"item": None, "progress": progress}
        cases = {c.id: c for c in load_cases()}
        return {"item": item_view(item, cases[item["case_id"]]), "progress": progress}

    @router.post("/labeling/labels")
    def save_label(label: LabelIn) -> dict:
        if label.item_id not in {i["item_id"] for i in load_pool(pool_path)}:
            raise HTTPException(status_code=404, detail="unknown item_id")
        if any(
            lab["item_id"] == label.item_id and lab["labeler"] == label.labeler
            for lab in load_labels(labels_path)
        ):
            raise HTTPException(status_code=409, detail="already labeled by this labeler")
        try:
            record = make_label(label.item_id, label.labeler, label.verdicts, label.note)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        append_label(record, labels_path)
        return record

    @router.post("/transcripts/{transcript_id}/promote")
    def promote_transcript(transcript_id: str, body: PromoteIn) -> dict:
        try:
            case = promote(
                transcript_id,
                body.category.value,
                body.note,
                [s for s in body.must_not_contain if s.strip()],
                [s for s in body.must_contain if s.strip()],
                storage=storage,
                golden_path=golden_path,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown transcript_id") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return case

    return router
