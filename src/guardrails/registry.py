"""Build the guardrail set named in config.yaml (`guardrails:`)."""

from collections.abc import Callable

from guardrails.base import Guardrail
from guardrails.pipeline import EMPTY, GuardrailSet


def _pii() -> Guardrail:
    from guardrails.pii import PIIRedactor  # imported lazily: loading spaCy takes ~1s

    return PIIRedactor()


def _injection() -> Guardrail:
    from guardrails.injection import InjectionGuard

    return InjectionGuard()


# name → factory. Filled in as guardrails land (M3.6 compliance).
REGISTRY: dict[str, Callable[[], Guardrail]] = {"pii": _pii, "injection": _injection}


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
