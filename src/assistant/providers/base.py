"""Provider-neutral types for talking to an LLM.

The tool loop only ever sees these types, so swapping Anthropic for another provider
means writing one new `Provider` class, not touching the loop.

Conversation messages are plain dicts in OUR format (not any provider's):
    {"role": "user", "content": "text"}
    {"role": "assistant", "content": "text", "tool_calls": [ToolCall-as-dict, ...],
     "provider_blocks": <opaque native content, optional>}
    {"role": "tool", "results": [{"tool_call_id": ..., "content": "json text", "is_error": bool}]}

`provider_blocks` lets a provider replay its own native content (for Anthropic: thinking
blocks, which must be passed back unchanged) instead of a lossy rebuild from text.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from assistant.config import Usage

StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal", "other"]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "input": self.input}


@dataclass
class ProviderRequest:
    model: str
    system: str
    messages: list[dict]
    tools: list[dict] = field(default_factory=list)  # [{name, description, input_schema}]
    max_tokens: int = 16000
    effort: str | None = None
    output_schema: dict | None = None  # JSON Schema for structured output, if any


@dataclass
class ProviderResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: StopReason
    usage: Usage
    requested_model: str
    served_model: str  # can differ from requested if a refusal fallback ran
    latency_ms: float
    ttft_ms: float | None  # time to first text token; None if no text was streamed
    provider_blocks: list[dict] | None = None

    def assistant_message(self) -> dict:
        """This response as a conversation message to append to the history."""
        message = {
            "role": "assistant",
            "content": self.text,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
        }
        if self.provider_blocks is not None:
            message["provider_blocks"] = self.provider_blocks
        return message


TextCallback = Callable[[str], None]


class Provider(Protocol):
    name: str

    def complete(
        self, request: ProviderRequest, on_text: TextCallback | None = None
    ) -> ProviderResponse:
        """Run one model request, calling `on_text` with each text chunk as it streams."""
        ...
