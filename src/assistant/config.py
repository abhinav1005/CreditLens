"""Load config.yaml and config/pricing.yaml into typed objects, and compute request cost.

Env overrides (handy for evals and CI):
    CREDITLENS_CONFIG           path to an alternative config.yaml
    CREDITLENS_ASSISTANT_MODEL  replaces assistant.model
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]


class AssistantConfig(BaseModel):
    model: str
    system_prompt_version: str
    tools_prompt_version: str
    max_tokens: int
    max_tool_iterations: int
    effort: str


class RoutingConfig(BaseModel):
    cheap_model: str


class JudgeConfig(BaseModel):
    model: str
    effort: str


class ModelConfig(BaseModel):
    provider: str
    supports_effort: bool


class StorageConfig(BaseModel):
    sqlite_path: str


class EvalsConfig(BaseModel):
    response_cache_dir: str
    concurrency: int
    max_cost_usd_local: float
    max_cost_usd_ci: float


class Config(BaseModel):
    assistant: AssistantConfig
    routing: RoutingConfig
    judge: JudgeConfig
    models: dict[str, ModelConfig]
    storage: StorageConfig
    evals: EvalsConfig

    def model_config_for(self, model: str) -> ModelConfig:
        if model not in self.models:
            raise KeyError(f"model {model!r} is not listed under `models:` in config.yaml")
        return self.models[model]


class Rates(BaseModel):
    input: float
    output: float
    cache_write: float
    cache_read: float


class ModelPricing(Rates):
    long_context_threshold: int | None = None
    long_context: Rates | None = None


class Pricing(BaseModel):
    as_of: str
    models: dict[str, ModelPricing]


class Usage(BaseModel):
    """Token counts as reported by the provider for one or more requests."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(**{f: getattr(self, f) + getattr(other, f) for f in Usage.model_fields})


def request_cost(pricing: Pricing, model: str, usage: Usage) -> float:
    """USD cost of ONE request. (Long-context tiers depend on a single request's size.)"""
    p = pricing.models[model]
    rates: Rates = p
    total_input = usage.input_tokens + usage.cache_write_tokens + usage.cache_read_tokens
    if p.long_context and p.long_context_threshold and total_input > p.long_context_threshold:
        rates = p.long_context
    return (
        usage.input_tokens * rates.input
        + usage.output_tokens * rates.output
        + usage.cache_write_tokens * rates.cache_write
        + usage.cache_read_tokens * rates.cache_read
    ) / 1_000_000


@lru_cache(maxsize=4)
def _load_config(path: str, model_override: str | None) -> Config:
    config = Config.model_validate(yaml.safe_load(Path(path).read_text()))
    if model_override:
        config.assistant.model = model_override
    for model in [config.assistant.model, config.routing.cheap_model, config.judge.model]:
        config.model_config_for(model)  # fail fast on unknown models
    return config


def load_config() -> Config:
    path = os.environ.get("CREDITLENS_CONFIG", str(ROOT / "config.yaml"))
    return _load_config(path, os.environ.get("CREDITLENS_ASSISTANT_MODEL"))


@lru_cache(maxsize=1)
def load_pricing() -> Pricing:
    return Pricing.model_validate(yaml.safe_load((ROOT / "config" / "pricing.yaml").read_text()))
