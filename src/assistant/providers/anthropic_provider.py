"""Anthropic implementation of `Provider`, using the official SDK's streaming helper.

Request shape notes (current API, see PRD §14 "API constraints"):
- No temperature: sampling params are rejected, so none are sent.
- Thinking is adaptive by default on Sonnet/Haiku 5.5; depth is set with output_config.effort.
  Haiku 4.5 has no effort parameter (config: supports_effort: false).
- Thinking blocks come back in `content` and are replayed unchanged via provider_blocks.
- Optional server-side refusal fallback (config: refusal_fallback) re-runs a refused
  request on a fallback model inside the same call; the served model is recorded.
"""

import json
import time

import anthropic

from assistant.config import ModelConfig, Usage
from assistant.providers.base import ProviderRequest, ProviderResponse, TextCallback, ToolCall

FALLBACK_BETA = "server-side-fallback-2026-07-01"

_STOP_REASONS = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}


def to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """Convert our neutral conversation format to Anthropic Messages API format."""
    out = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            if m.get("provider_blocks") is not None:
                content = m["provider_blocks"]
            else:
                content = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for call in m.get("tool_calls", []):
                    content.append(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["name"],
                            "input": call["input"],
                        }
                    )
            out.append({"role": "assistant", "content": content})
        elif m["role"] == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r["tool_call_id"],
                            "content": r["content"],
                            "is_error": r.get("is_error", False),
                        }
                        for r in m["results"]
                    ],
                }
            )
        else:
            raise ValueError(f"unknown role {m['role']!r}")
    return out


def _usage(raw) -> Usage:
    return Usage(
        input_tokens=raw.input_tokens or 0,
        output_tokens=raw.output_tokens or 0,
        cache_write_tokens=getattr(raw, "cache_creation_input_tokens", None) or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", None) or 0,
    )


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model_config: ModelConfig, client: anthropic.Anthropic | None = None):
        self.model_config = model_config
        self.client = client or anthropic.Anthropic()

    def build_params(self, request: ProviderRequest) -> dict:
        params: dict = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": to_anthropic_messages(request.messages),
        }
        if request.tools:
            params["tools"] = request.tools
        output_config: dict = {}
        if request.effort and self.model_config.supports_effort:
            output_config["effort"] = request.effort
        if request.output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.output_schema}
        if output_config:
            params["output_config"] = output_config
        if request.cache_prompt:
            # Automatic caching: the API caches the longest stable prefix it can (tools, then
            # system, then earlier messages). Verified by usage.cache_read_input_tokens (M4.4).
            params["cache_control"] = {"type": "ephemeral"}
        return params

    def complete(
        self, request: ProviderRequest, on_text: TextCallback | None = None
    ) -> ProviderResponse:
        params = self.build_params(request)
        if self.model_config.refusal_fallback:
            stream_ctx = self.client.beta.messages.stream(
                betas=[FALLBACK_BETA], fallbacks="default", **params
            )
        else:
            stream_ctx = self.client.messages.stream(**params)

        start = time.perf_counter()
        ttft = None
        with stream_ctx as stream:
            for text in stream.text_stream:
                if ttft is None:
                    ttft = (time.perf_counter() - start) * 1000
                if on_text:
                    on_text(text)
            message = stream.get_final_message()
        latency = (time.perf_counter() - start) * 1000

        text = "".join(b.text for b in message.content if b.type == "text")
        tool_calls = [
            ToolCall(
                id=b.id,
                name=b.name,
                input=b.input if isinstance(b.input, dict) else json.loads(b.input),
            )
            for b in message.content
            if b.type == "tool_use"
        ]
        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=_STOP_REASONS.get(message.stop_reason, "other"),
            usage=_usage(message.usage),
            requested_model=request.model,
            served_model=message.model,
            latency_ms=latency,
            ttft_ms=ttft,
            provider_blocks=[b.model_dump(mode="json", exclude_none=True) for b in message.content],
        )
