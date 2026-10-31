"""Golden eval cases: schema, loader, and validator.

One case per line in evals/datasets/golden.jsonl. A case is either:
- kind "chat": a fixed conversation ending in a user message. Earlier turns (including
  tool calls and results) are part of the case and are never regenerated. Only the final
  assistant turn is generated and scored.
- kind "insights": no conversation. Scores the /insights cards for `profile_id`.

    uv run python -m evals validate [path]
"""

import json
import re
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from credit.dataset import load_profiles
from credit.factors import FactorCode
from credit.tools.contracts import TOOL_CONTRACTS

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
GOLDEN_PATH = DATASETS_DIR / "golden.jsonl"


class Category(StrEnum):
    FACTUAL = "factual"  # explanatory / general questions
    TOOL_USE = "tool_use"  # needs the right tools with the right args
    INSIGHT_GROUNDING = "insight_grounding"  # insight cards backed by evidence
    REFUSAL = "refusal"  # off-topic or out-of-scope requests
    INJECTION = "injection"  # direct and indirect prompt injection
    PII = "pii"  # personal identifiers in input
    COMPLIANCE = "compliance"  # traps: score promises, product picks, legal advice


# Target counts per category for the full golden set (PRD §5.3).
TARGET_COUNTS = {
    Category.FACTUAL: 30,
    Category.TOOL_USE: 30,
    Category.INSIGHT_GROUNDING: 20,
    Category.REFUSAL: 15,
    Category.INJECTION: 20,
    Category.PII: 15,
    Category.COMPLIANCE: 20,
}


class ExpectedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    args: dict = {}  # every key here must match the actual call; extra actual args are fine


class NumericFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    description: str = ""


class Expectations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_call_tools: list[ExpectedToolCall] = []
    must_not_call_tools: list[str] = []
    must_contain: list[str] = []  # case-insensitive substrings
    must_not_contain: list[str] = []  # case-insensitive substrings
    must_not_match: list[str] = []  # regexes (case-insensitive)
    expected_refusal: bool | None = None
    disclaimer: bool | None = None  # must (True) / must not (False) end with the disclaimer
    numeric_facts: list[NumericFact] = []  # numbers the answer must state
    must_mention_factors: list[FactorCode] = []
    rubric_notes: str = ""  # guidance for the LLM judge (M2)

    @model_validator(mode="after")
    def _regexes_compile(self) -> "Expectations":
        for pattern in self.must_not_match:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"bad regex {pattern!r}: {exc}") from exc
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z]+_\d{3}$")
    kind: Literal["chat", "insights"] = "chat"
    category: Category
    profile_id: str
    conversation: list[dict] = []
    expectations: Expectations
    tags: list[str] = []
    source: Literal["authored", "promoted_from_transcript"] = "authored"
    authored_by: Literal["human", "llm_drafted_human_reviewed"]
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Case":
        if self.profile_id not in load_profiles():
            raise ValueError(f"unknown profile_id {self.profile_id}")
        if self.kind == "chat":
            if not self.conversation or self.conversation[-1].get("role") != "user":
                raise ValueError("chat cases need a conversation ending in a user message")
            for m in self.conversation:
                if m.get("role") not in {"user", "assistant", "tool"}:
                    raise ValueError(f"bad role in conversation: {m.get('role')!r}")
        elif self.conversation:
            raise ValueError("insights cases have no conversation")
        tools = [
            t.name for t in self.expectations.must_call_tools
        ] + self.expectations.must_not_call_tools
        unknown = [t for t in tools if t not in TOOL_CONTRACTS]
        if unknown:
            raise ValueError(f"unknown tools {unknown}")
        return self


def load_cases(path: Path = GOLDEN_PATH) -> list[Case]:
    """Load and validate every case; raises ValueError listing all problems at once."""
    cases, problems = [], []
    if not path.exists():
        return []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(Case.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            problems.append(f"line {lineno}: {exc}")
    dupes = [i for i, n in Counter(c.id for c in cases).items() if n > 1]
    if dupes:
        problems.append(f"duplicate ids: {dupes}")
    if problems:
        raise ValueError(f"{path.name}: {len(problems)} invalid case(s)\n" + "\n".join(problems))
    return cases


def summarize(cases: list[Case]) -> str:
    counts = Counter(c.category for c in cases)
    lines = [f"{len(cases)} valid cases"]
    for cat in Category:
        lines.append(f"  {cat.value:<18} {counts.get(cat, 0):>3} / {TARGET_COUNTS[cat]}")
    smoke = sum("smoke" in c.tags for c in cases)
    lines.append(f"  smoke-tagged       {smoke:>3}")
    return "\n".join(lines)
