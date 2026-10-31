"""Experiments E1–E4 on claude-haiku-5-5 (golden suite), generated from saved runs.

    uv run python -m evals experiments      # writes reports/experiments.{md,json}

No API calls: every number is computed from the runs named below (reports/ or
reports/history/). The runs themselves were made with `python -m evals run` (commands in
the report). Judge off throughout; pass/fail is the deterministic scorers only.

E1 Reliability   the same config run 5 times with fresh calls: how much does the score move?
E2 Ablation      remove one part of the system prompt (guardrails off): what does each part do?
E3 Defense       full vs minimal prompt × guardrails off/on, on the attack categories
E4 Effort        low (the 5 repeats) vs medium vs high
"""

import json
import statistics
from pathlib import Path

from evals.compare import find_run, load_results
from evals.guardrail_e2e import ATTACK_CATEGORIES, attack_stats
from evals.variants import summary

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "experiments"
MODEL = "claude-haiku-5-5"
REPEATS = [f"exp-repeat-{i}" for i in range(1, 6)]
ABLATIONS = [
    ("v1", "full prompt"),
    ("v1-no-grounding", "without the 'numbers must come from tools' rules"),
    ("v1-no-rules", "without the 8 safety rules"),
    ("v1-minimal", "identity + disclaimer only"),
]
GATE_CASES = 2  # the smoke gate's 5-point limit on 41 cases is 2 cases


def results(run: str) -> dict[str, dict]:
    return load_results(find_run(run))


def harm(run: str) -> tuple[int, int]:
    """(harmed, n) over the attack categories: a harm check failed (see guardrail_e2e)."""
    s = attack_stats(results(run))
    return sum(s[c]["harm"] for c in ATTACK_CATEGORIES), sum(s[c]["n"] for c in ATTACK_CATEGORIES)


def failed_check(run: str, name: str) -> int:
    return sum(
        any(c["name"] == name and not c["passed"] for c in r["checks"])
        for r in results(run).values()
    )


def cost_per_case(run: str) -> float:
    s = summary(run)
    return s["cost"]["measured_total_usd"] / s["n_cases"]


def output_tokens_per_case(run: str) -> float:
    """Mean output tokens per case. Unlike cost, this doesn't depend on whether the prompt
    cache was warm (runs made back to back read the cache; the first one writes it)."""
    rows = list(results(run).values())
    return statistics.mean(r["usage"]["output_tokens"] for r in rows)


def reliability() -> dict:
    runs = [results(r) for r in REPEATS]
    rates = [summary(r)["overall_pass_rate"] for r in REPEATS]
    ids = sorted(set.intersection(*(set(r) for r in runs)))
    outcomes = {cid: [r[cid]["passed"] for r in runs] for cid in ids}
    flaky = sorted(cid for cid, o in outcomes.items() if 0 < sum(o) < len(o))
    smoke = [cid for cid in ids if "smoke" in runs[0][cid].get("tags", [])]
    smoke_passed = [sum(r[cid]["passed"] for cid in smoke) for r in runs]
    by_cat: dict[str, int] = {}
    for cid in flaky:
        cat = runs[0][cid]["category"]
        by_cat[cat] = by_cat.get(cat, 0) + 1
    return {
        "runs": REPEATS,
        "n_cases": len(ids),
        "pass_rates": rates,
        "mean": round(statistics.mean(rates), 4),
        "min": min(rates),
        "max": max(rates),
        "stdev": round(statistics.stdev(rates), 4),
        "always_pass": sum(all(o) for o in outcomes.values()),
        "always_fail": sum(not any(o) for o in outcomes.values()),
        "flaky": flaky,
        "flaky_by_category": dict(sorted(by_cat.items())),
        "smoke_n": len(smoke),
        "smoke_passed": smoke_passed,
        "smoke_swing": max(smoke_passed) - min(smoke_passed),
        "gate_limit_cases": GATE_CASES,
    }


def ablation() -> list[dict]:
    rows = []
    for version, what in ABLATIONS:
        run = f"exp-ablate-{version}-off"
        s = summary(run)
        h, n = harm(run)
        rows.append(
            {
                "prompt": version,
                "what": what,
                "run_id": run,
                "pass_rate": s["overall_pass_rate"],
                "n_passed": s["n_passed"],
                "n_cases": s["n_cases"],
                "categories": {k: v["pass_rate"] for k, v in s["categories"].items()},
                "harm": h,
                "harm_n": n,
                "grounding_failures": failed_check(run, "numeric_grounding"),
                "output_tokens_per_case": round(output_tokens_per_case(run)),
            }
        )
    return rows


def defense() -> list[dict]:
    cells = [
        ("v1", "off", "exp-ablate-v1-off"),
        ("v1", "on", REPEATS[0]),
        ("v1-minimal", "off", "exp-ablate-v1-minimal-off"),
        ("v1-minimal", "on", "exp-ablate-v1-minimal-on"),
    ]
    rows = []
    for prompt, guards, run in cells:
        h, n = harm(run)
        rows.append({"prompt": prompt, "guardrails": guards, "run_id": run, "harm": h, "n": n})
    return rows


def effort() -> list[dict]:
    low = [summary(r) for r in REPEATS]
    rows = [
        {
            "effort": "low",
            "runs": len(low),
            "pass_rate": round(statistics.mean(s["overall_pass_rate"] for s in low), 4),
            "pass_rate_range": [
                min(s["overall_pass_rate"] for s in low),
                max(s["overall_pass_rate"] for s in low),
            ],
            "cost_per_case_usd": round(statistics.mean(cost_per_case(r) for r in REPEATS), 6),
            "output_tokens_per_case": round(
                statistics.mean(output_tokens_per_case(r) for r in REPEATS)
            ),
        }
    ]
    for level in ["medium", "high"]:
        run = f"exp-effort-{level}"
        s = summary(run)
        rows.append(
            {
                "effort": level,
                "runs": 1,
                "pass_rate": s["overall_pass_rate"],
                "pass_rate_range": None,
                "cost_per_case_usd": round(cost_per_case(run), 6),
                "output_tokens_per_case": round(output_tokens_per_case(run)),
            }
        )
    return rows


def build() -> dict:
    return {
        "model": MODEL,
        "suite": "golden",
        "reliability": reliability(),
        "ablation": ablation(),
        "defense": defense(),
        "effort": effort(),
    }


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def render(data: dict) -> str:
    rel, abl, dfn, eff = data["reliability"], data["ablation"], data["defense"], data["effort"]
    lines = [
        f"# Experiments ({data['model']}, golden suite)",
        "",
        "Generated by `uv run python -m evals experiments` from saved runs. Deterministic scorers only (judge off).",
        "Runs were made with `uv run python -m evals run --suite golden --model claude-haiku-5-5 ...` using the run ids below.",
        "",
        "## E1 Reliability: the same config, run 5 times",
        "",
        f"`--prompt-version v1 --no-cache --run-id exp-repeat-N` (guardrails on, effort low). {rel['n_cases']} cases.",
        "",
        "| Run | " + " | ".join(r.replace("exp-repeat-", "#") for r in rel["runs"]) + " |",
        "|---|" + "---:|" * len(rel["runs"]),
        "| Pass rate | " + " | ".join(pct(x) for x in rel["pass_rates"]) + " |",
        f"| Smoke subset (of {rel['smoke_n']}) | "
        + " | ".join(str(x) for x in rel["smoke_passed"])
        + " |",
        "",
        f"- Mean {pct(rel['mean'])}, range {pct(rel['min'])}–{pct(rel['max'])}, standard deviation {100 * rel['stdev']:.1f} points.",
        f"- {rel['always_pass']} cases passed every time, {rel['always_fail']} failed every time, "
        f"**{len(rel['flaky'])} were flaky** (passed in some runs, failed in others): {rel['flaky_by_category']}.",
        f"- On the {rel['smoke_n']}-case smoke subset the pass count swung by **{rel['smoke_swing']} cases** with nothing changed. "
        f"The CI gate's limit is {rel['gate_limit_cases']} cases, so "
        + (
            "**a single run can fail the gate on noise alone.**"
            if rel["smoke_swing"] > rel["gate_limit_cases"]
            else "noise alone stayed within the gate's limit here."
        ),
        f"- Flaky cases: {', '.join(rel['flaky']) or 'none'}.",
        "",
        "## E2 Prompt ablation: what does each part of the prompt do? (guardrails off)",
        "",
        "`--prompt-version <v> --guardrails off --run-id exp-ablate-<v>-off`. Every variant keeps the identity, profile-id and disclaimer lines.",
        "Attack harm = a harm check failed on an injection, PII or compliance case (echoed PII, score promise, followed an injection).",
        "",
        "| Prompt | What's removed | Pass rate | Attack harm | Grounding failures | Output tokens / case |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in abl:
        lines.append(
            f"| `{r['prompt']}` | {r['what']} | {pct(r['pass_rate'])} ({r['n_passed']}/{r['n_cases']}) "
            f"| {r['harm']}/{r['harm_n']} | {r['grounding_failures']} | {r['output_tokens_per_case']} |"
        )
    cats = sorted({c for r in abl for c in r["categories"]})
    lines += [
        "",
        "| Category | " + " | ".join(f"`{r['prompt']}`" for r in abl) + " |",
        "|---|" + "---:|" * len(abl),
    ]
    for c in cats:
        lines.append(f"| {c} | " + " | ".join(pct(r["categories"].get(c, 0)) for r in abl) + " |")
    lines += [
        "",
        f"Single run per variant. Compare differences against E1's noise (range {pct(rel['min'])}–{pct(rel['max'])}).",
        "Insight-card cases use their own prompt, so they don't change across these variants.",
        "",
        "## E3 Defense in depth: prompt × guardrails, attack categories",
        "",
        "| Prompt | Guardrails off | Guardrails on |",
        "|---|---:|---:|",
    ]
    for prompt in ["v1", "v1-minimal"]:
        off = next(r for r in dfn if r["prompt"] == prompt and r["guardrails"] == "off")
        on = next(r for r in dfn if r["prompt"] == prompt and r["guardrails"] == "on")
        lines.append(f"| `{prompt}` | {off['harm']}/{off['n']} | {on['harm']}/{on['n']} |")
    lines += [
        "",
        f"Runs: {', '.join(r['run_id'] for r in dfn)}. Count = attack cases where a harm check failed.",
        "",
        "## E4 Effort: does thinking harder help?",
        "",
        "`--prompt-version v1 --effort <level> --run-id exp-effort-<level>`; low is the mean of the 5 E1 runs.",
        "",
        "| Effort | Runs | Pass rate | Output tokens / case | Measured cost / case |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in eff:
        rng = (
            f" (range {pct(r['pass_rate_range'][0])}–{pct(r['pass_rate_range'][1])})"
            if r["pass_rate_range"]
            else ""
        )
        lines.append(
            f"| {r['effort']} | {r['runs']} | {pct(r['pass_rate'])}{rng} | {r['output_tokens_per_case']} | ${r['cost_per_case_usd']:.5f} |"
        )
    lines += [
        "",
        "Compare output tokens, not measured cost: cost depends on prompt-cache warmth, which depends on run order."
        " A run that starts cold pays to write the cache; runs right after it mostly read it.",
    ]
    return "\n".join(lines) + "\n"


def write() -> Path:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    OUT.with_suffix(".md").write_text(render(data))
    return OUT.with_suffix(".md")
