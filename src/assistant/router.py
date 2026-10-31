"""Model router: send simple, general questions to the cheap model.

A deterministic rule (PRD §14: rule first, LLM classifier only if the rule misroutes too
often). A turn goes to the SMALL model only if all of these hold:
- the latest user message doesn't refer to the person's own situation ("my", "I", "me"...),
- there are no earlier turns (follow-ups usually depend on fetched data),
- it doesn't ask for a simulation ("what if I pay...").
Everything else goes to the BIG model. Misrouting is measured against the golden set's
labeled tool needs (`python -m evals route-check`).
"""

import re
from typing import Literal

PERSONAL = re.compile(r"\b(my|mine|me|i|i'm|i've|i'd|im|our|us)\b", re.IGNORECASE)
SIMULATION = re.compile(r"\bwhat if\b|\bif i (pay|paid|close|open)\b", re.IGNORECASE)

Tier = Literal["big", "small"]


def route(conversation: list[dict]) -> tuple[Tier, str]:
    latest = conversation[-1]["content"]
    if len(conversation) > 1:
        return "big", "follow-up turn"
    if SIMULATION.search(latest):
        return "big", "simulation request"
    if PERSONAL.search(latest.replace("’", "'")):
        return "big", "refers to the person's own credit"
    return "small", "general question"
