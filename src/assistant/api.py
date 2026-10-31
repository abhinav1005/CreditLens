"""FastAPI app: `/chat` streams a turn over Server-Sent Events.

    uv run uvicorn assistant.api:app --reload

`run_turn` is synchronous, so it runs in a worker thread and pushes events onto a queue;
the response generator yields them as SSE frames as they arrive.

SSE frames:  event: <type>\\ndata: <json>\\n\\n
Event types: tool_call, tool_result, text, retract, done, transcript, error
"""

import json
import queue
import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from assistant.config import load_config
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


def create_app(
    provider_factory: Callable[[str], Provider] | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    config = load_config()
    provider_factory = provider_factory or (lambda model: get_provider(model, config))
    store = storage or SQLiteStorage(config.storage.sqlite_path)
    app = FastAPI(title="CreditLens", description=DISCLAIMER)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

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
                result = run_turn(
                    conversation,
                    request.profile_id,
                    config=config,
                    provider=provider_factory(config.assistant.model),
                    on_event=events.put,
                )
                transcript = transcript_from_turn(result, conversation_id, source="chat")
                store.put(transcript)
                events.put(
                    {
                        "type": "transcript",
                        "transcript_id": transcript.transcript_id,
                        "conversation_id": conversation_id,
                        "cost_usd": round(result.cost_usd, 6),
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

    return app


app = create_app()
