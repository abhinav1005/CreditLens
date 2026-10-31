"""Labeling pool: assistant responses for humans to label and the judge to grade.

The pool mixes models and prompt versions (including the deliberately degraded prompt) so
that a good share of responses fail. A pool where ~90% pass makes kappa unstable.

    uv run python -m evals build-pool --models claude-sonnet-5-5,claude-haiku-5-5 \
        --prompts v1,v1-degraded

Items are deduplicated and shuffled with a fixed seed, so labeling order is random but
reproducible. Each item records exactly where it came from (model, prompt, run, cache key).
"""

import hashlib
import json
import random
from pathlib import Path

from evals.cache import ResponseCache
from evals.cases import DATASETS_DIR, load_cases

POOL_PATH = DATASETS_DIR / "labeling_pool.jsonl"
POOL_SEED = 20261031


def item_id(cache_key: str) -> str:
    return "lp_" + hashlib.sha256(cache_key.encode()).hexdigest()[:10]


def build_pool(
    models: list[str],
    prompts: list[str],
    *,
    max_cost_usd: float,
    run_suite=None,
    cache: ResponseCache | None = None,
    reports_dir: Path | None = None,
) -> list[dict]:
    from assistant.config import load_config
    from evals.runner import ROOT
    from evals.runner import run_suite as real_run_suite

    run_suite = run_suite or real_run_suite
    config = load_config()
    cache = cache or ResponseCache(ROOT / config.evals.response_cache_dir)
    cases = load_cases()
    items, seen, spent = [], set(), 0.0
    for model in models:
        for prompt in prompts:
            kwargs = {"reports_dir": reports_dir} if reports_dir else {}
            summary = run_suite(
                cases,
                suite="golden",
                model=model,
                prompt_version=prompt,
                max_cost_usd=max_cost_usd - spent,
                cache_dir=cache.dir,
                **kwargs,
            )
            spent += summary["cost"]["api_spend_this_run_usd"]
            results = Path(summary["out_dir"]) / "results.jsonl"
            for row in map(json.loads, results.read_text().splitlines()):
                if row["status"] != "ok":
                    continue
                record = cache.get(row["cache_key"])
                answer = (
                    record.get("cards") if record["kind"] == "insights" else record["final_text"]
                )
                dedupe = (row["case_id"], json.dumps(answer, sort_keys=True))
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                items.append(
                    {
                        "item_id": item_id(row["cache_key"]),
                        "case_id": row["case_id"],
                        "category": row["category"],
                        "model": model,
                        "prompt_version": prompt,
                        "run_id": summary["run_id"],
                        "cache_key": row["cache_key"],
                        "record": record,
                    }
                )
    random.Random(POOL_SEED).shuffle(items)
    return items


def write_pool(items: list[dict], path: Path = POOL_PATH) -> None:
    path.write_text("".join(json.dumps(i, sort_keys=True) + "\n" for i in items))


def load_pool(path: Path = POOL_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
