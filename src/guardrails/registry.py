"""Build the guardrail set named in config.yaml (`guardrails:`)."""

from collections.abc import Callable

from guardrails.base import Guardrail
from guardrails.pipeline import EMPTY, GuardrailSet

# name → factory. Filled in as guardrails land (M3.2 pii, M3.4 injection, M3.6 compliance).
REGISTRY: dict[str, Callable[[], Guardrail]] = {}


def build_guardrails(config) -> GuardrailSet:
    g = getattr(config, "guardrails", None)
    if g is None or not g.enabled:
        return EMPTY

    def make(names: list[str]) -> list[Guardrail]:
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            raise KeyError(
                f"unknown guardrails in config.yaml: {unknown} (known: {sorted(REGISTRY)})"
            )
        return [REGISTRY[n]() for n in names]

    return GuardrailSet(
        input=make(g.input), tool_results=make(g.tool_results), output=make(g.output)
    )
