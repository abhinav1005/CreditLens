"""Sentence buffering and the output filter chain.

Streamed text is held until a sentence is complete, then passed through every
`OutputFilter` before it reaches the user. Once text is sent it can't be unsent, so
checks that need the whole answer run in `check_final` and can only `retract`.

M1 ships with an empty chain; M3 adds PII and compliance filters here.
"""

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

# A sentence ends at . ! ? followed by whitespace, or at a newline. "40.8%" and "$1,200.50"
# don't end a sentence because the period is followed by a digit.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n")


@dataclass
class FilterDecision:
    action: Literal["pass", "rewrite", "block", "retract"]
    text: str = ""
    filter_name: str = ""
    reasons: list[str] = field(default_factory=list)


class OutputFilter(Protocol):
    name: str

    def check_sentence(self, sentence: str, context: dict) -> FilterDecision: ...

    def check_final(self, full_text: str, context: dict) -> FilterDecision: ...


class SentenceBuffer:
    """Accumulates streamed chunks and returns complete sentences (with trailing whitespace)."""

    def __init__(self):
        self._pending = ""

    def feed(self, chunk: str) -> list[str]:
        self._pending += chunk
        sentences = []
        while True:
            match = _BOUNDARY.search(self._pending)
            if not match:
                break
            sentences.append(self._pending[: match.end()])
            self._pending = self._pending[match.end() :]
        return sentences

    def flush(self) -> list[str]:
        rest, self._pending = self._pending, ""
        return [rest] if rest else []


def apply_sentence_filters(
    sentence: str, filters: list[OutputFilter], context: dict
) -> tuple[str | None, list[FilterDecision]]:
    """Run a sentence through the chain. Returns (text to send or None if blocked, decisions)."""
    decisions = []
    text = sentence
    for f in filters:
        decision = f.check_sentence(text, context)
        decisions.append(decision)
        if decision.action == "block":
            return None, decisions
        if decision.action == "rewrite":
            text = decision.text
    return text, decisions
