"""Prompt-injection guardrail: heuristic rules, then an LLM classifier.

Layer 1 (rules): weighted patterns. A strong match (score ≥ BLOCK_SCORE) is treated as an
injection without any API call.
Layer 2 (LLM): everything else goes to a small classifier model (Haiku 5.5) with a
versioned prompt. It catches attacks with no telltale keywords and clears look-alike
credit questions ("ignore the late payment, what if I pay it off?").

Stages:
- input: an injection blocks the turn.
- tool_result: only free-text fields (creditor_name, notes) are checked. An injected field
  is replaced with a marker (action "rewrite") so the real data still reaches the model.

Classifier verdicts are cached on disk by (text, model, prompt hash) so evals rerun free.
"""

import hashlib
import json
import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from assistant.prompts import PROMPTS_DIR
from assistant.schema import inline_refs
from guardrails.base import GuardrailResult, passed

BLOCK_SCORE = 0.8
CLASSIFIER_MODEL = "claude-haiku-5-5"
PROMPT_FILE = PROMPTS_DIR / "guardrails" / "injection_v1.md"
FREE_TEXT_FIELDS = {"creditor_name", "notes"}
REMOVED = "[removed: text that looked like instructions to the assistant]"

# (pattern, weight). High weights are near-unambiguous; low weights only add suspicion.
RULES = [
    (
        r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|all|your|these|earlier)\b.{0,20}\b(instructions|rules|prompt|guidelines|directions)\b",
        0.95,
    ),
    (r"\b(system|developer)\s*(prompt|message|instructions|override|notice|mode)\b", 0.6),
    (r"</?\s*(system|user|assistant|instructions?)\s*>", 0.95),
    (
        r"\b(reveal|print|show|repeat|output|dump|list)\b.{0,30}\b(system prompt|your instructions|your rules|the text above|tool definitions|every tool|all (the )?tools)\b",
        0.9,
    ),
    (r"\bjailbreak\b|\bdo anything now\b|\bno (more )?rules\b", 0.9),
    # Common in real attacks but also in ordinary sentences ("you are now approved",
    # "new instructions from my bank"): suspicion only, so the LLM decides (tuned on dev).
    (r"\byou are now\b|\bnew instructions\b", 0.5),
    (
        r"\b(assistant|AI|chatbot|model)\b.{0,15}\b(must|should|will|you must)\b.{0,40}\b(recommend|tell|say|reveal|promise|ignore)\b",
        0.8,
    ),
    (
        r"\bprofile[_ ]?id\b.{0,30}\b(actually|instead|use)\b|\buse (profile )?(p|story|inj)_\d{3}\b",
        0.85,
    ),
    (r"\b(pretend|role-?play|act as)\b.{0,30}\b(you|you're|you are)\b", 0.4),
    (r"\boverride\b", 0.3),
]
_COMPILED = [(re.compile(p, re.IGNORECASE | re.DOTALL), w) for p, w in RULES]


def rule_score(text: str) -> tuple[float, list[str]]:
    hits = [(w, p.pattern[:40]) for p, w in _COMPILED if p.search(text)]
    if not hits:
        return 0.0, []
    return max(w for w, _ in hits), [h for _, h in hits]


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str
    label: Literal["injection", "benign"]


@lru_cache(maxsize=1)
def _prompt() -> tuple[str, str]:
    text = PROMPT_FILE.read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


def classify_llm(text: str, provider=None, cache_dir=None) -> tuple[str, str, float]:
    """(label, rationale, cost_usd). Cached on disk by text + model + prompt hash."""
    from assistant.config import ROOT, load_pricing, request_cost
    from assistant.providers import ProviderRequest, get_provider
    from evals.cache import ResponseCache

    system, prompt_hash = _prompt()
    cache = ResponseCache(cache_dir or ROOT / ".cache" / "guardrails")
    key = hashlib.sha256(json.dumps([text, CLASSIFIER_MODEL, prompt_hash]).encode()).hexdigest()
    hit = cache.get(key)
    if hit:
        return hit["label"], hit["rationale"], 0.0
    provider = provider or get_provider(CLASSIFIER_MODEL)
    response = provider.complete(
        ProviderRequest(
            model=CLASSIFIER_MODEL,
            system=system,
            messages=[{"role": "user", "content": f"<text>\n{text}\n</text>"}],
            max_tokens=1000,
            effort="low",
            output_schema=inline_refs(Verdict.model_json_schema()),
        )
    )
    try:
        verdict = Verdict.model_validate_json(response.text)
    except ValueError:
        verdict = Verdict(rationale="classifier output invalid; failing closed", label="injection")
    cost = request_cost(load_pricing(), CLASSIFIER_MODEL, response.usage)
    cache.put(key, {"label": verdict.label, "rationale": verdict.rationale})
    return verdict.label, verdict.rationale, cost


def is_injection(
    text: str, *, use_llm: bool = True, provider=None, cache_dir=None
) -> tuple[bool, dict]:
    score, hits = rule_score(text)
    if score >= BLOCK_SCORE:
        return True, {"layer": "rules", "rule_score": score, "rules": hits}
    if not use_llm:
        return False, {"layer": "rules", "rule_score": score, "rules": hits}
    label, rationale, cost = classify_llm(text, provider, cache_dir)
    return label == "injection", {
        "layer": "llm",
        "rule_score": score,
        "rules": hits,
        "rationale": rationale,
        "cost": cost,
    }


class InjectionGuard:
    name = "injection"

    def __init__(self, use_llm: bool = True, provider=None, cache_dir=None):
        self.use_llm = use_llm
        self.provider = provider
        self.cache_dir = (
            cache_dir  # tests pass a temp dir so fake verdicts never reach the real cache
        )

    def check(self, text: str, context: dict) -> GuardrailResult:
        if context.get("stage") == "tool_result":
            return self._check_tool_result(text)
        flagged, info = is_injection(
            text, use_llm=self.use_llm, provider=self.provider, cache_dir=self.cache_dir
        )
        scores = {"rule_score": info["rule_score"], "llm": 1.0 if info["layer"] == "llm" else 0.0}
        if flagged:
            return GuardrailResult(
                self.name, False, "block", text, [f"injection ({info['layer']})"], scores
            )
        return passed(self.name, text, **scores)

    def _check_tool_result(self, text: str) -> GuardrailResult:
        try:
            data = json.loads(text)
        except ValueError:
            return passed(self.name, text)
        flagged_fields = []

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in FREE_TEXT_FIELDS and isinstance(v, str) and v.strip():
                        bad, _ = is_injection(
                            v,
                            use_llm=self.use_llm,
                            provider=self.provider,
                            cache_dir=self.cache_dir,
                        )
                        if bad:
                            node[k] = REMOVED
                            flagged_fields.append(k)
                    else:
                        walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        if not flagged_fields:
            return passed(self.name, text)
        return GuardrailResult(
            self.name,
            True,
            "rewrite",
            json.dumps(data),
            [f"injected text in {sorted(set(flagged_fields))}"],
            {"fields": float(len(flagged_fields))},
        )
