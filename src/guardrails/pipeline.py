"""Run guardrails in order for one stage (input, tool_result, output)."""

from dataclasses import dataclass, field

from guardrails.base import Guardrail, GuardrailResult


@dataclass
class PipelineOutcome:
    text: str
    blocked_by: GuardrailResult | None
    decisions: list[dict] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.blocked_by is not None


def run_pipeline(guards: list[Guardrail], text: str, context: dict, stage: str) -> PipelineOutcome:
    decisions = []
    for guard in guards:
        result = guard.check(text, {**context, "stage": stage})
        decisions.append(result.to_dict(stage))
        if result.action == "block":
            return PipelineOutcome(text, result, decisions)
        if result.action in ("redact", "rewrite"):
            text = result.text
    return PipelineOutcome(text, None, decisions)


@dataclass
class GuardrailSet:
    """Guardrails per stage. Output guardrails also act as sentence filters (see loop)."""

    input: list[Guardrail] = field(default_factory=list)
    tool_results: list[Guardrail] = field(default_factory=list)
    output: list[Guardrail] = field(default_factory=list)


EMPTY = GuardrailSet()
