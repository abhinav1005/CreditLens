"""The common guardrail interface.

Every guardrail implements `check(text, context) -> GuardrailResult`. A pipeline runs them in
order: a `redact` or `rewrite` passes the modified text to the next guardrail, and a `block`
stops the pipeline. Every result is logged, including passes, so evals can measure each
guardrail's precision and recall.
"""

from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

Action = Literal["pass", "redact", "block", "rewrite"]


@dataclass
class GuardrailResult:
    name: str
    allowed: bool
    action: Action
    text: str  # the text after this guardrail (unchanged on pass/block)
    reasons: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self, stage: str) -> dict:
        d = asdict(self)
        d.pop("text")  # never log the text itself: it may be what was redacted
        return {"stage": stage, **d}


class Guardrail(Protocol):
    name: str

    def check(self, text: str, context: dict) -> GuardrailResult: ...


def passed(name: str, text: str, **scores: float) -> GuardrailResult:
    return GuardrailResult(name, True, "pass", text, [], dict(scores))
