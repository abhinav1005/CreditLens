"""FastAPI app: `/chat` streams a turn over Server-Sent Events.

    uv run uvicorn assistant.api:app --reload

`run_turn` is synchronous, so it runs in a worker thread and pushes events onto a queue;
the response generator yields them as SSE frames as they arrive.

SSE frames:  event: <type>\\ndata: <json>\\n\\n
Event types: tool_call, tool_result, text, retract, done, transcript, error
The `transcript` event carries the guardrail decisions that acted (redact/block/rewrite/
retract) so the UI can show badges. `/profiles` lists the synthetic profiles for the picker.
"""

import json
import queue
import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from assistant.ab import assign_variant
from assistant.config import ROOT, load_config
from assistant.insights import generate_insights
from assistant.loop import run_turn
from assistant.providers import Provider, get_provider
from credit.dataset import load_profiles
from storage.sqlite import SQLiteStorage
from storage.transcripts import Storage, transcript_from_turn

DISCLAIMER = "Educational demo on synthetic data. Not financial advice."


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    profile_id: str
    conversation_id: str | None = None
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)


def sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def guardrail_flags(decisions: list[dict]) -> list[dict]:
    """The guardrail decisions that did something (not a plain pass), for UI badges."""
    return [
        {k: d[k] for k in ("stage", "name", "action", "reasons")}
        for d in decisions
        if d["action"] != "pass"
    ]


def transcript_summary(t) -> dict:
    """One row of the transcript list: enough to filter and pick, not the whole record."""
    last_user = next((m["content"] for m in reversed(t.messages) if m["role"] == "user"), "")
    return {
        "transcript_id": t.transcript_id,
        "created_at": t.created_at,
        "conversation_id": t.conversation_id,
        "profile_id": t.profile_id,
        "model": t.model,
        "prompt_version": t.prompt_version,
        "variant": t.variant,
        "stop": t.stop,
        "cost_usd": round(t.cost_usd, 6),
        "latency_ms": round(t.latency_ms, 1),
        "question": last_user[:200],
        "tools": [c["name"] for c in t.tool_calls],
        "guardrails": guardrail_flags(t.guardrail_decisions),
    }


def profile_summary(profile) -> dict:
    """A short description of a synthetic profile for the profile picker."""
    return {
        "profile_id": profile.profile_id,
        "score": profile.score_history[-1].score,
        "as_of": profile.months[-1],
        "n_accounts": len(profile.accounts),
        "story": profile.story.description if profile.story else None,
    }


def create_app(
    provider_factory: Callable[[str], Provider] | None = None,
    storage: Storage | None = None,
    eval_router: APIRouter | None = None,
) -> FastAPI:
    config = load_config()
    provider_factory = provider_factory or (lambda model: get_provider(model, config))
    # Resolve against the repo root so the DB location doesn't depend on the cwd.
    store = storage or SQLiteStorage(ROOT / config.storage.sqlite_path)
    app = FastAPI(title="CreditLens", description=DISCLAIMER)
    if eval_router is None:
        from evals.web_routes import make_router  # labeling and promote for the web UI

        eval_router = make_router(storage=store)
    app.include_router(eval_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/profiles")
    def profiles() -> list[dict]:
        return [profile_summary(p) for p in load_profiles().values()]

    @app.get("/transcripts")
    def transcripts(limit: int = 200) -> list[dict]:
        # Newest first. Filtering happens in the UI (demo scale; see storage.transcripts).
        return [transcript_summary(t) for t in store.list(limit=min(limit, 1000))]

    @app.get("/transcripts/{transcript_id}")
    def transcript(transcript_id: str) -> dict:
        t = store.get(transcript_id)
        if t is None:
            raise HTTPException(status_code=404, detail="unknown transcript_id")
        return t.model_dump(mode="json")

    @app.post("/chat")
    def chat(request: ChatRequest) -> StreamingResponse:
        if request.profile_id not in load_profiles():
            raise HTTPException(status_code=404, detail="unknown profile_id")
        if request.messages[-1].role != "user":
            raise HTTPException(status_code=422, detail="last message must be from the user")
        conversation_id = request.conversation_id or uuid.uuid4().hex
        conversation = [m.model_dump() for m in request.messages]
        events: queue.Queue = queue.Queue()
        done = object()

        def worker() -> None:
            try:
                variant, model = None, config.assistant.model
                if config.ab_test.enabled:
                    variant = assign_variant(conversation_id, config.ab_test.percent)
                    if variant == "candidate":
                        model = config.ab_test.candidate_model
                result = run_turn(
                    conversation,
                    request.profile_id,
                    config=config,
                    provider=provider_factory(model),
                    model=model,
                    on_event=events.put,
                )
                transcript = transcript_from_turn(
                    result, conversation_id, source="chat", variant=variant
                )
                store.put(transcript)
                events.put(
                    {
                        "type": "transcript",
                        "transcript_id": transcript.transcript_id,
                        "conversation_id": conversation_id,
                        "cost_usd": round(result.cost_usd, 6),
                        "model": result.model,
                        "prompt_version": result.prompt_version,
                        "latency_ms": round(result.latency_ms, 1),
                        "guardrails": guardrail_flags(result.guardrail_decisions),
                    }
                )
            except Exception as exc:  # surface failures to the client instead of hanging
                events.put({"type": "error", "message": type(exc).__name__})
            finally:
                events.put(done)

        def stream() -> Iterator[str]:
            threading.Thread(target=worker, daemon=True).start()
            while (event := events.get()) is not done:
                yield sse(event["type"], {k: v for k, v in event.items() if k != "type"})

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/insights/{profile_id}")
    def insights(profile_id: str) -> dict:
        if profile_id not in load_profiles():
            raise HTTPException(status_code=404, detail="unknown profile_id")
        result = generate_insights(
            profile_id, config=config, provider=provider_factory(config.assistant.model)
        )
        meta = {
            "model": result.model,
            "served_models": result.served_models,
            "prompt_version": result.prompt_version,
            "prompt_hash": result.prompt_hash,
            "retries": result.retries,
            "cost_usd": round(result.cost_usd, 6),
            "latency_ms": round(result.latency_ms, 1),
        }
        if result.cards is None:
            raise HTTPException(status_code=502, detail={"error": "invalid model output", **meta})
        return {"cards": [c.model_dump(mode="json") for c in result.cards], "meta": meta}

    return app


app = create_app()
