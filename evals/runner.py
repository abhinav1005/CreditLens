"""Run a suite of golden cases against the real assistant code path and score them.

    uv run python -m evals run --suite golden --model claude-sonnet-5-5 --prompt-version v1

Each case goes through `run_turn` (chat) or `generate_insights` (insights) exactly as a user
request would, then every scorer runs. A case passes only if all its checks pass.

Spending guard: before running, the cost of uncached cases is estimated and the run refuses
to start above `--max-cost-usd`. During the run, new cases stop being started once actual
spend passes the limit, and those cases are reported as skipped.
"""

import json
import subprocess
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from assistant.config import Config, Usage, load_config, load_pricing, request_cost
from assistant.insights import generate_insights, load_insight_prompt
from assistant.loop import run_turn
from assistant.prompts import load_bundle
from assistant.providers import Provider, get_provider
from evals.cache import ResponseCache, cache_key
from evals.cases import Case
from evals.judge import judge_response, load_judge_prompt
from evals.judge_policy import JUDGE_DIMENSIONS_BY_CATEGORY, JUDGE_MODES
from evals.scorers.base import CaseOutput, Check
from evals.scorers.deterministic import (
    score_completed,
    score_disclaimer,
    score_factors,
    score_refusal,
    score_schema,
    score_strings,
    score_tool_calls,
)
from evals.scorers.grounding import score_grounding
from evals.scorers.insights import score_insight_cards

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"

SCORERS = [
    score_completed,
    score_tool_calls,
    score_strings,
    score_refusal,
    score_disclaimer,
    score_factors,
    score_schema,
    score_grounding,
    score_insight_cards,
]

# Rough token profile for a case with no cached history, used only for the pre-run estimate:
# a chat turn is ~3 requests of ~4K input + ~400 output tokens.
ESTIMATE_USAGE = Usage(input_tokens=12_000, output_tokens=1_200)


class BudgetExceeded(Exception):
    pass


ESTIMATE_MARGIN = 1.5


def estimated_cost_per_case(model: str, pricing) -> float:
    """Pre-run estimate per uncached case.

    If the committed baseline was measured on this model, use its real mean cost per case
    with a 1.5x margin. Otherwise fall back to a deliberately pessimistic token profile.
    """
    baseline_summary = REPORTS_DIR / "baseline" / "smoke" / "summary.json"
    if baseline_summary.exists():
        s = json.loads(baseline_summary.read_text())
        mean = s.get("cost", {}).get("mean_per_case_usd")
        if s.get("model") == model and mean:
            return mean * ESTIMATE_MARGIN
    return request_cost(pricing, model, ESTIMATE_USAGE)


def score_case(case: Case, out: CaseOutput) -> list[Check]:
    checks: list[Check] = []
    for scorer in SCORERS:
        checks.extend(scorer(case, out))
    return checks


def _execute(case: Case, model: str, config: Config, provider: Provider) -> dict:
    """Run one case for real. Returns a JSON-ready record of what the system produced."""
    if case.kind == "chat":
        r = run_turn(
            case.conversation, case.profile_id, config=config, provider=provider, model=model
        )
        return {
            "kind": "chat",
            "final_text": r.final_text,
            "tool_calls": r.tool_calls,
            "stop": r.stop,
            "usage": r.usage.model_dump(),
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "ttft_ms": r.ttft_ms,
            "served_models": r.served_models,
        }
    r = generate_insights(
        case.profile_id,
        config=config,
        provider=provider,
        model=model,
        prompt_version=config.assistant.insights_prompt_version,
    )
    return {
        "kind": "insights",
        "final_text": "",
        "tool_calls": r.tool_calls,
        "stop": "complete" if r.cards else "invalid",
        "cards": [c.model_dump(mode="json") for c in r.cards] if r.cards else None,
        "retries": r.retries,
        "errors": r.errors,
        "usage": r.usage.model_dump(),
        "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms,
        "ttft_ms": None,
        "served_models": r.served_models,
    }


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered) + 0.5 - 1e-9))
    return ordered[min(rank, len(ordered)) - 1]


def _git_info() -> dict:
    def git(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
    }


def run_suite(
    cases: list[Case],
    *,
    suite: str,
    model: str,
    prompt_version: str,
    max_cost_usd: float,
    concurrency: int | None = None,
    use_cache: bool = True,
    provider_factory: Callable[[str], Provider] | None = None,
    reports_dir: Path = REPORTS_DIR,
    cache_dir: Path | None = None,
    run_id: str | None = None,
    judge_mode: str = "off",
    judge_version: str = "v1",
    judge_fn: Callable | None = None,
    judge_cache_dir: Path | None = None,
    tags: list[str] | None = None,
) -> dict:
    if judge_mode not in JUDGE_MODES:
        raise ValueError(f"judge_mode must be one of {JUDGE_MODES}")
    config = load_config().model_copy(deep=True)
    config.assistant.system_prompt_version = prompt_version
    config.assistant.model = model
    config.model_config_for(model)
    pricing = load_pricing()
    bundle = load_bundle(prompt_version, config.assistant.tools_prompt_version)
    _, insights_hash = load_insight_prompt(config.assistant.insights_prompt_version)
    provider_factory = provider_factory or (lambda m: get_provider(m, config))
    cache = ResponseCache(cache_dir or ROOT / config.evals.response_cache_dir, enabled=use_cache)
    settings = {
        "max_tokens": config.assistant.max_tokens,
        "effort": config.assistant.effort,
        "max_tool_iterations": config.assistant.max_tool_iterations,
    }

    keys = {}
    for case in cases:
        payload = case.model_dump(mode="json", include={"kind", "profile_id", "conversation"})
        prompt_hash = insights_hash if case.kind == "insights" else bundle.content_hash
        keys[case.id] = cache_key(payload, model, settings, prompt_hash)
    uncached = [c for c in cases if cache.get(keys[c.id]) is None]
    estimate = len(uncached) * estimated_cost_per_case(model, pricing)
    if estimate > max_cost_usd:
        raise BudgetExceeded(
            f"estimated cost ${estimate:.2f} for {len(uncached)} uncached cases exceeds "
            f"--max-cost-usd ${max_cost_usd:.2f}"
        )

    spend = 0.0
    lock = threading.Lock()
    provider = provider_factory(model)

    judge_fn = judge_fn or judge_response
    judge_cache = ResponseCache(judge_cache_dir or ROOT / ".cache" / "judge", enabled=use_cache)
    _, judge_hash = load_judge_prompt(judge_version)
    judge_spend = 0.0

    def run_judge(case: Case, out: CaseOutput, answer_key: str) -> dict | None:
        """Judge one answer, cached by (answer cache key, judge model, judge prompt hash)."""
        nonlocal judge_spend
        jkey = cache_key(
            {"answer": answer_key}, config.judge.model, {"judge": judge_version}, judge_hash
        )
        cached = judge_cache.get(jkey)
        if cached is not None:
            return cached
        result = judge_fn(case, out, config=config, version=judge_version)
        with lock:
            judge_spend += result.cost_usd
        if result.verdicts is None:
            return None
        record = result.to_dict()
        judge_cache.put(jkey, record)
        return record

    def work(case: Case) -> dict:
        nonlocal spend
        key = keys[case.id]
        cached = cache.get(key)
        error = None
        if cached is not None:
            record, hit = cached, True
        else:
            with lock:
                if spend + judge_spend > max_cost_usd:
                    return {
                        "case_id": case.id,
                        "category": case.category.value,
                        "tags": case.tags,
                        "status": "skipped_budget",
                        "passed": False,
                        "checks": [],
                    }
            try:
                record = _execute(case, model, config, provider)
                cache.put(key, record)
            except Exception as exc:  # an API error fails this case, not the run
                record = {
                    "kind": case.kind,
                    "final_text": "",
                    "tool_calls": [],
                    "stop": "error",
                    "usage": Usage().model_dump(),
                    "cost_usd": 0.0,
                    "latency_ms": None,
                    "ttft_ms": None,
                    "served_models": [],
                }
                error = f"{type(exc).__name__}: {exc}"[:300]
            with lock:
                spend += record["cost_usd"]
            hit = False
        out = CaseOutput(
            kind=record["kind"],
            final_text=record["final_text"],
            tool_calls=record["tool_calls"],
            stop=record["stop"],
            cards=record.get("cards"),
            retries=record.get("retries", 0),
        )
        checks = score_case(case, out) if error is None else [Check("ran", "runner", False, error)]
        judge_record = None
        if judge_mode != "off" and error is None:
            judge_record = run_judge(case, out, key)
            if judge_record is None:
                checks.append(Check("judge_ran", "judge", False, "judge output invalid twice"))
            elif judge_mode == "gate":
                counted = JUDGE_DIMENSIONS_BY_CATEGORY[case.category]
                for dim in counted:
                    v = judge_record["verdicts"][dim]
                    checks.append(
                        Check(f"judge:{dim}", "judge", v["verdict"] == "pass", v["rationale"][:300])
                    )
        return {
            "case_id": case.id,
            "category": case.category.value,
            "tags": case.tags,
            "authored_by": case.authored_by,
            "status": "error" if error else "ok",
            "passed": all(c.passed for c in checks),
            "checks": [c.to_dict() for c in checks],
            "final_text": record["final_text"],
            "cards": record.get("cards"),
            "tool_calls": [
                {"name": t["name"], "input": t["input"], "is_error": t.get("is_error", False)}
                for t in record["tool_calls"]
            ],
            "stop": record["stop"],
            "usage": record["usage"],
            "cost_usd": record["cost_usd"],
            "latency_ms": record["latency_ms"],
            "ttft_ms": record["ttft_ms"],
            "served_models": record["served_models"],
            "cache_hit": hit,
            "cache_key": key,
            "judge": judge_record["verdicts"] if judge_record else None,
        }

    started = time.perf_counter()
    workers = concurrency or config.evals.concurrency
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(work, cases))
    wall = time.perf_counter() - started

    run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{suite}-{model}-{prompt_version}"
    summary = summarize(
        results,
        run_id=run_id,
        suite=suite,
        model=model,
        prompt_version=prompt_version,
        prompt_hash=bundle.content_hash,
        pricing_as_of=pricing.as_of,
        spend=spend,
        estimate=estimate,
        wall_seconds=wall,
    )
    summary["tags"] = sorted(tags or [])  # the tag filter this run used (smoke runs: ["smoke"])
    summary["judge"] = judge_summary(
        results, judge_mode, judge_version, judge_hash, judge_spend, config.judge.model
    )
    out_dir = reports_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    from evals.report import render_report

    (out_dir / "report.md").write_text(render_report(summary, results))
    summary["out_dir"] = str(out_dir)
    return summary


def summarize(results: list[dict], **meta) -> dict:
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    categories = {
        cat: {
            "n": len(rs),
            "passed": sum(r["passed"] for r in rs),
            "pass_rate": round(sum(r["passed"] for r in rs) / len(rs), 4),
        }
        for cat, rs in sorted(by_cat.items())
    }
    failed_checks = Counter(c["scorer"] for r in results for c in r["checks"] if not c["passed"])
    ran = [r for r in results if r["status"] == "ok"]
    latencies = [r["latency_ms"] for r in ran if r["latency_ms"] is not None]
    costs = [r["cost_usd"] for r in ran]
    n = len(results)
    return {
        **{k: v for k, v in meta.items() if k not in {"spend", "estimate", "wall_seconds"}},
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": _git_info(),
        "n_cases": n,
        "n_passed": sum(r["passed"] for r in results),
        "overall_pass_rate": round(sum(r["passed"] for r in results) / n, 4) if n else None,
        "categories": categories,
        "status_counts": dict(Counter(r["status"] for r in results)),
        "failed_checks_by_scorer": dict(failed_checks),
        "unreviewed_cases": sum(r.get("authored_by") == "llm_drafted" for r in results),
        "cost": {
            "api_spend_this_run_usd": round(meta["spend"], 6),
            "pre_run_estimate_usd": round(meta["estimate"], 4),
            "measured_total_usd": round(sum(costs), 6),
            "mean_per_case_usd": round(sum(costs) / len(costs), 6) if costs else None,
        },
        "latency_ms": {
            "note": "measured under parallel load; M4.2 adds a clean sequential run",
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
        "cache_hits": sum(r.get("cache_hit", False) for r in results),
        "wall_seconds": round(meta["wall_seconds"], 1),
    }


def judge_summary(
    results: list[dict], mode: str, version: str, prompt_hash: str, spend: float, model: str
) -> dict:
    """Judge pass rate per category × dimension (all dimensions, counted or not)."""
    if mode == "off":
        return {"mode": "off"}
    from evals.judge import DIMENSIONS

    by_cat: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        for dim, v in (r.get("judge") or {}).items():
            by_cat[r["category"]][dim].append(v["verdict"] == "pass")
    return {
        "mode": mode,
        "version": version,
        "prompt_hash": prompt_hash,
        "model": model,
        "spend_usd": round(spend, 6),
        "pass_rates": {
            cat: {d: round(sum(v) / len(v), 4) for d, v in dims.items() if v}
            for cat, dims in sorted(by_cat.items())
        },
        "dimensions": DIMENSIONS,
    }
