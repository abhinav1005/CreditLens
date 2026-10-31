"""LLM judge: pass/fail per rubric dimension, with the rationale written before the verdict.

The judge is pinned (config.judge.model) because it is the thing being calibrated against
human labels: swapping it would invalidate the calibration. Used only where rules can't
decide (PRD: deterministic scorers first).
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from assistant.config import Config, Usage, load_config, load_pricing, request_cost
from assistant.prompts import PROMPTS_DIR
from assistant.providers import Provider, ProviderRequest, get_provider
from assistant.schema import inline_refs
from evals.cases import Case
from evals.scorers.base import CaseOutput

DIMENSIONS = ["helpfulness", "clarity", "compliance", "groundedness"]
MAX_RETRIES = 1


class DimensionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: Literal["helpfulness", "clarity", "compliance", "groundedness"]
    rationale: str  # first, so the model reasons before deciding
    verdict: Literal["pass", "fail"]


class JudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grades: list[DimensionVerdict]


@dataclass
class JudgeResult:
    verdicts: dict[str, dict] | None  # dimension → {verdict, rationale}; None if unusable output
    usage: Usage
    cost_usd: float
    model: str
    prompt_version: str
    prompt_hash: str
    retries: int
    errors: list[str]

    def to_dict(self) -> dict:
        return {
            "verdicts": self.verdicts,
            "usage": self.usage.model_dump(),
            "cost_usd": self.cost_usd,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "retries": self.retries,
            "errors": self.errors,
        }


def load_judge_prompt(version: str = "v1") -> tuple[str, str]:
    text = (PROMPTS_DIR / "judge" / f"{version}.md").read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


def render_conversation(conversation: list[dict]) -> str:
    lines = []
    for m in conversation:
        if m["role"] == "user":
            lines.append(f"USER: {m['content']}")
        elif m["role"] == "assistant":
            if m.get("content"):
                lines.append(f"ASSISTANT: {m['content']}")
            for call in m.get("tool_calls", []):
                lines.append(f"ASSISTANT called {call['name']}({json.dumps(call['input'])})")
        elif m["role"] == "tool":
            for r in m["results"]:
                lines.append(f"TOOL RESULT: {r['content']}")
    return "\n".join(lines)


def build_judge_input(case: Case, out: CaseOutput) -> str:
    """Everything the judge sees for one case, as one user message."""
    if case.kind == "insights":
        conversation = "USER: (requested insight cards for their profile)"
        reply = json.dumps(out.cards, indent=1) if out.cards else "(no valid cards)"
    else:
        conversation = render_conversation(case.conversation)
        reply = out.final_text
    tools = (
        "\n".join(
            f"{c['name']}({json.dumps(c['input'])}) -> {json.dumps(c.get('output'))}"
            for c in out.tool_calls
        )
        or "(no tools called in this turn)"
    )
    notes = case.expectations.rubric_notes or "(none)"
    return (
        f"<conversation>\n{conversation}\n</conversation>\n\n"
        f"<tool_results_this_turn>\n{tools}\n</tool_results_this_turn>\n\n"
        f"<final_reply>\n{reply}\n</final_reply>\n\n"
        f'<case_notes category="{case.category.value}">\n{notes}\n</case_notes>'
    )


def parse_grades(text: str) -> dict[str, dict]:
    grades = JudgeOutput.model_validate_json(text).grades
    found = {g.dimension: {"verdict": g.verdict, "rationale": g.rationale} for g in grades}
    if set(found) != set(DIMENSIONS) or len(grades) != len(DIMENSIONS):
        raise ValueError(
            f"expected one grade per dimension {DIMENSIONS}, got {[g.dimension for g in grades]}"
        )
    return found


def judge_response(
    case: Case,
    out: CaseOutput,
    *,
    config: Config | None = None,
    provider: Provider | None = None,
    version: str = "v1",
) -> JudgeResult:
    config = config or load_config()
    model = config.judge.model
    provider = provider or get_provider(model, config)
    pricing = load_pricing()
    system, prompt_hash = load_judge_prompt(version)
    messages = [{"role": "user", "content": build_judge_input(case, out)}]
    schema = inline_refs(JudgeOutput.model_json_schema())

    usage, cost, errors, verdicts = Usage(), 0.0, [], None
    attempts = 0
    while attempts <= MAX_RETRIES:
        attempts += 1
        response = provider.complete(
            ProviderRequest(
                model=model,
                system=system,
                messages=list(messages),
                max_tokens=4000,
                effort=config.judge.effort,
                output_schema=schema,
            )
        )
        usage = usage + response.usage
        cost += request_cost(pricing, model, response.usage)
        try:
            verdicts = parse_grades(response.text)
            break
        except (ValidationError, ValueError) as exc:
            errors.append(str(exc)[:300])
            messages.append(response.assistant_message())
            messages.append(
                {
                    "role": "user",
                    "content": f"Invalid output: {errors[-1]}\nReturn all four grades.",
                }
            )
    return JudgeResult(
        verdicts, usage, cost, model, f"judge:{version}", prompt_hash, attempts - 1, errors
    )
