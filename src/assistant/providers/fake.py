"""A scripted provider for tests.

Either replays `turns` in order, or (thread-safe, for parallel eval runs) asks
`responder(request)` for each turn. Every request is recorded.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from assistant.config import Usage
from assistant.providers.base import ProviderRequest, ProviderResponse, TextCallback, ToolCall


@dataclass
class FakeTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None  # default: tool_use if tool_calls else end_turn
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=100, output_tokens=20))


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        turns: list[FakeTurn] | None = None,
        responder: Callable[[ProviderRequest], FakeTurn] | None = None,
    ):
        self.turns = list(turns or [])
        self.responder = responder
        self.requests: list[ProviderRequest] = []
        self._lock = threading.Lock()

    def _next_turn(self, request: ProviderRequest) -> FakeTurn:
        with self._lock:
            self.requests.append(request)
            if self.responder is not None:
                return self.responder(request)
            if not self.turns:
                raise AssertionError("FakeProvider ran out of scripted turns")
            return self.turns.pop(0)

    def complete(
        self, request: ProviderRequest, on_text: TextCallback | None = None
    ) -> ProviderResponse:
        turn = self._next_turn(request)
        start = time.perf_counter()
        ttft = None
        if on_text and turn.text:
            # Stream word by word so tests exercise sentence buffering.
            for i, word in enumerate(turn.text.split(" ")):
                if ttft is None:
                    ttft = (time.perf_counter() - start) * 1000
                on_text(word if i == 0 else " " + word)
        stop = turn.stop_reason or ("tool_use" if turn.tool_calls else "end_turn")
        return ProviderResponse(
            text=turn.text,
            tool_calls=turn.tool_calls,
            stop_reason=stop,
            usage=turn.usage,
            requested_model=request.model,
            served_model=request.model,
            latency_ms=(time.perf_counter() - start) * 1000,
            ttft_ms=ttft,
        )
