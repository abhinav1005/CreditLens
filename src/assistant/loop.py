"""The assistant's tool loop: `run_turn()` answers the latest user message.

One function serves both the FastAPI `/chat` endpoint and the eval runner, so evals test
exactly the code path users hit.

Loop: call the model → if it asked for tools, run them and send results back → repeat,
up to `max_tool_iterations`. Text is streamed through the sentence buffer and output filter
chain before it's emitted.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from assistant.config import Config, Usage, load_config, load_pricing, request_cost
from assistant.output_filters import (
    FilterDecision,
    OutputFilter,
    SentenceBuffer,
    apply_sentence_filters,
)
from assistant.prompts import PromptBundle, load_bundle
from assistant.providers import Provider, ProviderRequest, get_provider
from credit.tools.contracts import ToolError, ToolErrorCode
from credit.tools.impl import call_tool
from guardrails.pipeline import GuardrailSet, run_pipeline
from guardrails.registry import build_guardrails

REFUSAL_MESSAGE = "Sorry, I can't help with that. I'm happy to answer questions about your credit."
DEFAULT_BLOCK_MESSAGE = (
    "Sorry, I can't help with that request. I'm happy to answer questions about your credit."
)
# Per-guardrail replies when an input is blocked (filled in as guardrails land).
BLOCK_MESSAGES: dict[str, str] = {
    "injection": (
        "Sorry, I can't help with requests to change how I work or to see my instructions. "
        "I'm happy to answer questions about your credit."
    ),
}
WITHHELD_TOOL_RESULT = json.dumps(
    {
        "error": {
            "error_code": "WITHHELD",
            "message": "This tool result was withheld by a safety check.",
        }
    }
)
INCOMPLETE_MESSAGE = (
    "Sorry, I couldn't finish looking that up. Could you try asking in a simpler way?"
)

EventCallback = Callable[[dict], None]


@dataclass
class TurnResult:
    profile_id: str
    final_text: str  # exactly what the user was shown, after filters
    stop: str  # complete | max_iterations | refusal | max_tokens
    messages: list[dict]  # the full conversation including this turn
    events: list[dict]
    tool_calls: list[dict]  # [{id, name, input, output, is_error}]
    filter_decisions: list[dict]
    usage: Usage
    cost_usd: float
    latency_ms: float
    ttft_ms: float | None
    iterations: int
    model: str
    served_models: list[str]
    prompt_version: str
    prompt_hash: str
    pricing_as_of: str
    retracted: bool = False
    model_requests: int = 0
    guardrail_decisions: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def execute_tool(name: str, args: dict, profile_id: str) -> dict:
    """Run a tool for THIS conversation's profile only. Any other profile_id is refused."""
    if "profile_id" in args and args["profile_id"] != profile_id:
        error = ToolError(
            error_code=ToolErrorCode.INVALID_INPUT,
            message=f"profile_id must be {profile_id} in this conversation",
        )
        return {"error": error.model_dump(mode="json")}
    return call_tool(name, args)


def run_turn(
    conversation: list[dict],
    profile_id: str,
    *,
    config: Config | None = None,
    provider: Provider | None = None,
    bundle: PromptBundle | None = None,
    output_filters: list[OutputFilter] | None = None,
    on_event: EventCallback | None = None,
    model: str | None = None,
    guardrails: GuardrailSet | None = None,
) -> TurnResult:
    if not conversation or conversation[-1]["role"] != "user":
        raise ValueError("conversation must end with a user message")
    config = config or load_config()
    model = model or config.assistant.model
    provider = provider or get_provider(model, config)
    bundle = bundle or load_bundle(
        config.assistant.system_prompt_version, config.assistant.tools_prompt_version
    )
    guards = guardrails if guardrails is not None else build_guardrails(config)
    # Output guardrails run as sentence filters, ahead of any extra filters passed in.
    filters = [GuardrailOutputFilter(g) for g in guards.output] + (output_filters or [])
    pricing = load_pricing()
    context = {"profile_id": profile_id}

    events: list[dict] = []
    emitted: list[str] = []
    decisions: list[FilterDecision] = []
    tool_calls: list[dict] = []
    usage = Usage()
    cost = 0.0
    served: list[str] = []
    ttft = None
    start = time.perf_counter()

    def emit(event: dict) -> None:
        events.append(event)
        if on_event:
            on_event(event)

    buffer = SentenceBuffer()

    def send_sentences(sentences: list[str]) -> None:
        nonlocal ttft
        for sentence in sentences:
            text, ds = apply_sentence_filters(sentence, filters, context)
            decisions.extend(ds)
            if text:
                if ttft is None:
                    ttft = (time.perf_counter() - start) * 1000
                emitted.append(text)
                emit({"type": "text", "text": text})

    def on_text(chunk: str) -> None:
        # Text from a new model response starts a new paragraph, so "Let me check." from
        # a tool-calling turn doesn't run into the next turn's answer.
        if emitted and not buffer.has_pending() and not emitted[-1][-1:].isspace():
            chunk = "\n\n" + chunk.lstrip()
        send_sentences(buffer.feed(chunk))

    # Input guardrails. Every user message is redacted before the model or the logs see it
    # (earlier turns too, so history sent from a client is covered). Only the newest message
    # can be blocked, and only its decisions are logged (earlier ones were logged then).
    guard_decisions: list[dict] = []
    blocked_by = None
    messages = []
    for i, m in enumerate(conversation):
        if m["role"] == "user":
            outcome = run_pipeline(guards.input, m["content"], context, "input")
            if i == len(conversation) - 1:
                guard_decisions += outcome.decisions
                blocked_by = outcome.blocked_by
            m = {**m, "content": outcome.text}
        messages.append(m)

    stop = "max_iterations"
    iterations = 0
    if blocked_by is not None:
        stop = "blocked"
        send_sentences([BLOCK_MESSAGES.get(blocked_by.name, DEFAULT_BLOCK_MESSAGE)])
    while stop != "blocked" and iterations < config.assistant.max_tool_iterations:
        iterations += 1
        request = ProviderRequest(
            model=model,
            system=bundle.render_system(profile_id),
            messages=list(messages),  # snapshot: the list grows after this request
            tools=bundle.tools,
            max_tokens=config.assistant.max_tokens,
            effort=config.assistant.effort,
        )
        response = provider.complete(request, on_text=on_text)
        send_sentences(buffer.flush())
        usage = usage + response.usage
        served.append(response.served_model)
        priced_model = response.served_model if response.served_model in pricing.models else model
        cost += request_cost(pricing, priced_model, response.usage)
        messages.append(response.assistant_message())

        if response.stop_reason == "refusal":
            stop = "refusal"
            break
        if response.stop_reason == "max_tokens":
            stop = "max_tokens"
            break
        if response.stop_reason != "tool_use" or not response.tool_calls:
            stop = "complete"
            break

        results = []
        for call in response.tool_calls:
            emit({"type": "tool_call", "id": call.id, "name": call.name, "input": call.input})
            output = execute_tool(call.name, call.input, profile_id)
            is_error = "error" in output
            tool_calls.append({**call.to_dict(), "output": output, "is_error": is_error})
            emit({"type": "tool_result", "id": call.id, "name": call.name, "is_error": is_error})
            # Tool results are untrusted input (indirect injection): guard them before the
            # model reads them. The original output stays in tool_calls for scoring.
            outcome = run_pipeline(
                guards.tool_results,
                json.dumps(output),
                {**context, "tool": call.name},
                "tool_result",
            )
            guard_decisions += [{**d, "tool": call.name} for d in outcome.decisions]
            content = WITHHELD_TOOL_RESULT if outcome.blocked else outcome.text
            results.append({"tool_call_id": call.id, "content": content, "is_error": is_error})
        messages.append({"role": "tool", "results": results})

    if stop == "refusal" and not emitted:
        send_sentences([REFUSAL_MESSAGE])
    if stop == "max_iterations":
        send_sentences([INCOMPLETE_MESSAGE])

    final_text = "".join(emitted).strip()
    retracted = False
    for f in filters:
        decision = f.check_final(final_text, context)
        decisions.append(decision)
        if decision.action == "retract":
            retracted = True
            emit({"type": "retract", "reason": decision.reasons, "replacement": decision.text})
            final_text = decision.text
            break

    emit({"type": "done", "stop": stop})
    return TurnResult(
        profile_id=profile_id,
        final_text=final_text,
        stop=stop,
        messages=messages,
        events=events,
        tool_calls=tool_calls,
        filter_decisions=[d.__dict__ for d in decisions],
        guardrail_decisions=guard_decisions,
        usage=usage,
        cost_usd=cost,
        latency_ms=(time.perf_counter() - start) * 1000,
        ttft_ms=ttft,
        iterations=iterations,
        model=model,
        served_models=served,
        prompt_version=bundle.version,
        prompt_hash=bundle.content_hash,
        pricing_as_of=pricing.as_of,
        retracted=retracted,
        model_requests=len(served),
    )


class GuardrailOutputFilter:
    """Adapts an output guardrail to the sentence filter chain."""

    def __init__(self, guard):
        self.guard = guard
        self.name = guard.name

    def check_sentence(self, sentence: str, context: dict) -> FilterDecision:
        r = self.guard.check(sentence, {**context, "stage": "output"})
        action = {"pass": "pass", "redact": "rewrite", "rewrite": "rewrite", "block": "block"}[
            r.action
        ]
        return FilterDecision(action, r.text, self.name, r.reasons)

    def check_final(self, full_text: str, context: dict) -> FilterDecision:
        return FilterDecision("pass", filter_name=self.name)
