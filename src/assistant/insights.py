"""Insight cards: 1-3 structured, evidence-backed summaries of a profile.

Flow (see PRD §14):
1. Code calls get_credit_profile, get_utilization and get_score_history directly. These
   are the only tool calls, so the evidence check (evals) knows exactly what was seen.
2. One model request with structured output (`output_config.format`) writes the cards.
3. Pydantic validates. On failure, retry once with the validation error. Retries are counted.
"""

import hashlib
import json
import time
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from assistant.config import Config, Usage, load_config, load_pricing, request_cost
from assistant.prompts import PROMPTS_DIR
from assistant.providers import Provider, ProviderRequest, get_provider
from credit.factors import FactorCode
from credit.tools.impl import call_tool

DATA_TOOLS = ["get_credit_profile", "get_utilization", "get_score_history"]
MAX_RETRIES = 1


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    field: str
    value: float | str


class InsightCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    summary: str
    factor_code: FactorCode
    evidence: list[EvidenceItem]
    suggested_next_step: str
    disclaimer_required: bool


class InsightCardsWire(BaseModel):
    """Shape sent to the model as the output schema (no length constraints on the wire)."""

    model_config = ConfigDict(extra="forbid")
    cards: list[InsightCard]


class InsightCards(InsightCardsWire):
    """What we accept: 1-3 cards, each with at least one evidence item."""

    cards: list[InsightCard] = Field(min_length=1, max_length=3)

    def model_post_init(self, __context) -> None:
        for card in self.cards:
            if not card.evidence:
                raise ValueError(f"card {card.title!r} has no evidence")


@dataclass
class InsightResult:
    profile_id: str
    cards: list[InsightCard] | None  # None if both attempts failed validation
    retries: int
    errors: list[str]
    tool_calls: list[dict]  # [{name, input, output}]
    usage: Usage
    cost_usd: float
    latency_ms: float
    model: str
    served_models: list[str]
    prompt_version: str
    prompt_hash: str


def load_insight_prompt(version: str = "v1") -> tuple[str, str]:
    text = (PROMPTS_DIR / "insights" / f"{version}.md").read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


def gather_tool_data(profile_id: str) -> list[dict]:
    calls = []
    for name in DATA_TOOLS:
        args = {"profile_id": profile_id}
        calls.append({"name": name, "input": args, "output": call_tool(name, args)})
    return calls


def generate_insights(
    profile_id: str,
    *,
    config: Config | None = None,
    provider: Provider | None = None,
    model: str | None = None,
    prompt_version: str = "v1",
) -> InsightResult:
    config = config or load_config()
    model = model or config.assistant.model
    provider = provider or get_provider(model, config)
    pricing = load_pricing()
    system, prompt_hash = load_insight_prompt(prompt_version)
    start = time.perf_counter()

    tool_calls = gather_tool_data(profile_id)
    data = {c["name"]: c["output"] for c in tool_calls}
    messages = [
        {
            "role": "user",
            "content": "Tool data (JSON):\n<tool_data>\n"
            + json.dumps(data, indent=1)
            + "\n</tool_data>",
        }
    ]
    schema = InsightCardsWire.model_json_schema()

    usage, cost, served, errors = Usage(), 0.0, [], []
    cards = None
    attempts = 0
    while attempts <= MAX_RETRIES:
        attempts += 1
        response = provider.complete(
            ProviderRequest(
                model=model,
                system=system,
                messages=list(messages),
                max_tokens=config.assistant.max_tokens,
                effort=config.assistant.effort,
                output_schema=schema,
            )
        )
        usage = usage + response.usage
        served.append(response.served_model)
        priced = response.served_model if response.served_model in pricing.models else model
        cost += request_cost(pricing, priced, response.usage)
        try:
            cards = InsightCards.model_validate_json(response.text).cards
            break
        except (ValidationError, ValueError) as exc:
            errors.append(str(exc)[:500])
            messages.append(response.assistant_message())
            messages.append(
                {
                    "role": "user",
                    "content": "That output failed validation:\n"
                    + errors[-1]
                    + "\nReturn corrected cards.",
                }
            )

    return InsightResult(
        profile_id=profile_id,
        cards=cards,
        retries=attempts - 1,
        errors=errors,
        tool_calls=tool_calls,
        usage=usage,
        cost_usd=cost,
        latency_ms=(time.perf_counter() - start) * 1000,
        model=model,
        served_models=served,
        prompt_version=f"insights:{prompt_version}",
        prompt_hash=prompt_hash,
    )
