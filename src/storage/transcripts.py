"""Transcript records and the storage interface.

The interface is deliberately tiny (put / get / list by date) so any backend can satisfy it.
Callers filter in Python. That's fine at demo scale and keeps SQLite from growing queries
another store couldn't run.

Text reaching storage must already be PII-redacted. Input redaction lands in M3 and runs
before `run_turn`, so storage never sees raw input.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from assistant.config import Usage


class Transcript(BaseModel):
    transcript_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    source: Literal["chat", "eval"]
    conversation_id: str
    profile_id: str
    model: str
    served_models: list[str]
    prompt_version: str
    prompt_hash: str
    variant: str | None = None  # A/B arm (M4.7)
    messages: list[dict]
    events: list[dict]
    tool_calls: list[dict]
    filter_decisions: list[dict]
    guardrail_decisions: list[dict] = []  # M3
    final_text: str
    stop: str
    usage: Usage
    cost_usd: float
    pricing_as_of: str
    latency_ms: float
    ttft_ms: float | None
    extra: dict = {}


def transcript_from_turn(
    result, conversation_id: str, source: str, variant: str | None = None
) -> Transcript:
    """Build a Transcript from an `assistant.loop.TurnResult`."""
    return Transcript(
        source=source,
        conversation_id=conversation_id,
        profile_id=result.profile_id,
        model=result.model,
        served_models=result.served_models,
        prompt_version=result.prompt_version,
        prompt_hash=result.prompt_hash,
        variant=variant,
        messages=result.messages,
        events=result.events,
        tool_calls=result.tool_calls,
        filter_decisions=result.filter_decisions,
        guardrail_decisions=result.guardrail_decisions,
        final_text=result.final_text,
        stop=result.stop,
        usage=result.usage,
        cost_usd=result.cost_usd,
        pricing_as_of=result.pricing_as_of,
        latency_ms=result.latency_ms,
        ttft_ms=result.ttft_ms,
        extra=result.extra,
    )


class Storage(Protocol):
    def put(self, transcript: Transcript) -> None: ...

    def get(self, transcript_id: str) -> Transcript | None: ...

    def list(
        self, start: str | None = None, end: str | None = None, limit: int = 100
    ) -> list[Transcript]:
        """Newest first. `start`/`end` are ISO timestamps (inclusive / exclusive)."""
        ...
