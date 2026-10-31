"""HTTP routes for the web UI's eval tools: eval run browser, blind labeling, promote-to-test.

They call the same functions as the CLI (`python -m evals label`, `python -m evals promote`),
so a label or a promoted case made in the browser is the same record the terminal makes.

Labeling stays blind: an item is sent without the judge's verdict, the model, the prompt
version, or the run it came from.

The eval browser only reads saved runs (reports/, reports/history/, reports/baseline/), so it
makes no API calls. Run ids are accepted only if they appear in the run list, so a request
can't point the server at an arbitrary path.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evals.cases import DATASETS_DIR, GOLDEN_PATH, Category, load_cases
from evals.compare import SEARCH_DIRS, compare_results, load_results
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


def list_runs(search_dirs: list[Path] = SEARCH_DIRS) -> dict[str, Path]:
    """run id → folder, for every saved run with a summary. Same lookup order as
    `evals.compare.find_run`, so a name found twice resolves the same way as the CLI."""
    runs: dict[str, Path] = {}
    for d in search_dirs:
        if not d.is_dir():
            continue
        for run_dir in sorted(d.iterdir()):
            if (run_dir / "results.jsonl").exists() and (run_dir / "summary.json").exists():
                runs.setdefault(run_dir.name, run_dir)
    return runs


def run_summary(name: str, run_dir: Path) -> dict:
    s = json.loads((run_dir / "summary.json").read_text())
    return {
        "run_id": name,
        "location": str(run_dir.parent.name),
        "suite": s["suite"],
        "model": s["model"],
        "prompt_version": s["prompt_version"],
        "created_at": s["created_at"],
        "n_cases": s["n_cases"],
        "n_passed": s["n_passed"],
        "pass_rate": s["overall_pass_rate"],
        "categories": s["categories"],
        "cost_usd": s["cost"]["measured_total_usd"],
        "judge_mode": (s.get("judge") or {}).get("mode", "off"),
        "tags": s.get("tags"),
    }


def case_row(row: dict, case) -> dict:
    """One case in a run: outcome, the checks that failed, and what was asked."""
    question = None
    if case is not None:
        question = next(
            (m["content"] for m in reversed(case.conversation) if m["role"] == "user"), None
        )
    judge = row.get("judge") or {}
    return {
        "case_id": row["case_id"],
        "category": row["category"],
        "passed": row["passed"],
        "status": row["status"],
        "failed_checks": [
            {"name": c["name"], "scorer": c["scorer"], "detail": c.get("detail", "")}
            for c in row["checks"]
            if not c["passed"]
        ],
        "n_checks": len(row["checks"]),
        "question": question,
        "kind": case.kind if case is not None else None,
        "expectations": case.expectations.model_dump(mode="json") if case is not None else None,
        "final_text": row.get("final_text"),
        "cards": row.get("cards"),
        "tools": [c["name"] for c in row.get("tool_calls") or []],
        "judge": {
            dim: {"verdict": v["verdict"], "rationale": v.get("rationale", "")}
            for dim, v in judge.items()
            if isinstance(v, dict) and "verdict" in v
        },
        "cost_usd": row.get("cost_usd"),
        "latency_ms": row.get("latency_ms"),
    }


def _cases_for(suite: str) -> dict:
    path = DATASETS_DIR / f"{suite}.jsonl"
    return {c.id: c for c in load_cases(path)} if path.exists() else {}


def make_router(
    pool_path: Path = POOL_PATH,
    labels_path: Path = LABELS_PATH,
    storage=None,
    golden_path: Path = GOLDEN_PATH,
    search_dirs: list[Path] = SEARCH_DIRS,
) -> APIRouter:
    router = APIRouter()

    def run_dir(run_id: str) -> Path:
        runs = list_runs(search_dirs)
        if run_id not in runs:
            raise HTTPException(status_code=404, detail="unknown run_id")
        return runs[run_id]

    @router.get("/evals/runs")
    def runs() -> list[dict]:
        rows = [run_summary(name, d) for name, d in list_runs(search_dirs).items()]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    @router.get("/evals/runs/{run_id}")
    def run(run_id: str) -> dict:
        d = run_dir(run_id)
        summary = run_summary(run_id, d)
        cases = _cases_for(summary["suite"])
        rows = [case_row(r, cases.get(cid)) for cid, r in load_results(d).items()]
        return {"summary": summary, "cases": rows}

    @router.get("/evals/compare")
    def compare(a: str, b: str) -> dict:
        return {
            "a": a,
            "b": b,
            **compare_results(load_results(run_dir(a)), load_results(run_dir(b))),
        }

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
