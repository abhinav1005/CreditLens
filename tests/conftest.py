"""Shared test setup.

Unit tests never call a real model API. Guardrails from config.yaml include an LLM
classifier, so by default every test runs with NO guardrails; tests that exercise
guardrails pass their own `GuardrailSet` with fake providers. Live tests (`-m live`)
use the real configuration.
"""

import pytest

import assistant.loop
from guardrails.pipeline import EMPTY


@pytest.fixture(autouse=True)
def no_config_guardrails(request, monkeypatch):
    if "live" not in request.keywords:
        monkeypatch.setattr(assistant.loop, "build_guardrails", lambda config: EMPTY)
