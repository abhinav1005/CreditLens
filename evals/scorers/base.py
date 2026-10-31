"""Shared types for scorers.

A scorer looks at one case and the system's output for it and returns zero or more
`Check`s. No checks means "doesn't apply". A case passes only if every check passes.
"""

from dataclasses import dataclass, field


@dataclass
class CaseOutput:
    """What the system produced for one case: the final chat turn or the insight cards."""

    kind: str  # chat | insights
    final_text: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # [{name, input, output, is_error}]
    stop: str = "complete"
    cards: list[dict] | None = None  # insights only; None = failed validation
    retries: int = 0


@dataclass
class Check:
    name: str  # e.g. "tool_called:get_utilization"
    scorer: str  # e.g. "tool_calls"
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scorer": self.scorer,
            "passed": self.passed,
            "detail": self.detail,
        }
