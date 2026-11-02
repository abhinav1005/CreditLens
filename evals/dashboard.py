"""Dashboard data: one JSON file built from the committed reports, for the web dashboard.

    uv run python -m evals dashboard            # writes web/public/dashboard.json
    uv run python -m evals dashboard --check    # CI: fail if it's out of date

No API calls. Every number is read or computed from files under reports/ (and the golden
set), and each section names the command that produced its source. Nothing is typed in by
hand, and the output has no timestamp, so the same reports always give the same file.
"""

import json
from collections import Counter
from pathlib import Path

from evals.calibrate import CALIBRATION_DIR, MAIN_DIMENSION
from evals.cases import Category, load_cases
from evals.compare import find_run, load_results
from evals.guardrail_e2e import ATTACK_CATEGORIES, attack_stats
from evals.story import build_story
from evals.variants import latency, summary, usage

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUT = ROOT / "web" / "public" / "dashboard.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def models_section() -> dict:
    report = _read(REPORTS / "model-comparison.json")
    rows = []
    for r in report["rows"]:
        lat = r["latency"]
        rows.append(
            {
                "model": r["model"],
                "pass_rate": r["overall_pass_rate"],
                "categories": r["categories"],
                "judge": r["judge"],
                "cost_per_case_usd": r["mean_cost_per_case_usd"],
                "latency_p50_ms": lat["total_ms"]["p50"] if lat else None,
                "latency_p95_ms": lat["total_ms"]["p95"] if lat else None,
                "ttft_p50_ms": lat["ttft_ms"]["p50"] if lat else None,
            }
        )
    return {
        "source": "uv run python -m evals matrix --models <ids>",
        "n_cases": report["n_cases"],
        "pricing_as_of": report["pricing_as_of"],
        "rows": rows,
    }


def guardrails_section() -> dict:
    pii = _read(REPORTS / "guardrails" / "pii-test.json")
    rows = [
        {
            "guardrail": "pii",
            "n_positive": pii["n_pii_values"],
            "n_negative": pii["n_negatives"],
            "recall": pii["recall"],
            "false_positive_rate": pii["negative_false_positive_rate"],
            "rules_only_recall": None,
            "by_type": pii["recall_by_type"],
        }
    ]
    for name, pos, neg, by in [
        ("injection", "n_attacks", "n_benign", "flag_rate_by_kind"),
        ("compliance", "n_violations", "n_compliant", "recall_by_rule"),
    ]:
        r = _read(REPORTS / "guardrails" / f"{name}-test.json")
        rows.append(
            {
                "guardrail": name,
                "n_positive": r[pos],
                "n_negative": r[neg],
                "recall": r["recall"],
                "false_positive_rate": r["false_positive_rate"],
                "rules_only_recall": r["rules_only"]["recall"],
                "by_type": r[by],
            }
        )
    return {"source": "uv run python -m evals guardrail <name> --split test", "rows": rows}


def end_to_end_section() -> dict:
    scenarios = []
    for label, on, off in [
        ("v1", "e2e-guardrails-on", "e2e-guardrails-off"),
        ("v1-degraded", "e2e-degraded-guardrails-on", "e2e-degraded-guardrails-off"),
    ]:
        s_on = attack_stats(load_results(find_run(on)))
        s_off = attack_stats(load_results(find_run(off)))
        scenarios.append(
            {
                "prompt": label,
                "n": sum(s_on[c]["n"] for c in ATTACK_CATEGORIES),
                "harm_off": sum(s_off[c]["harm"] for c in ATTACK_CATEGORIES),
                "harm_on": sum(s_on[c]["harm"] for c in ATTACK_CATEGORIES),
                "by_category": {
                    c: {"n": s_on[c]["n"], "off": s_off[c]["harm"], "on": s_on[c]["harm"]}
                    for c in ATTACK_CATEGORIES
                },
            }
        )
    return {
        "source": "uv run python -m evals guardrail-e2e <run_on> <run_off> --label <prompt>",
        "scenarios": scenarios,
    }


def _run_row(name: str, run: str) -> dict:
    s = summary(run)
    return {
        "name": name,
        "pass_rate": s["overall_pass_rate"],
        "n_passed": s["n_passed"],
        "n_cases": s["n_cases"],
        "cost_usd": s["cost"]["measured_total_usd"],
    }


def variants_section() -> dict:
    off, on = latency("claude-sonnet-5-5"), latency("claude-sonnet-5-5-cache-on")
    caching = []
    for name, lat in [("off", off), ("on", on)]:
        caching.append(
            {
                **_run_row(name, lat["run_id"]),
                "cost_usd": lat["cost_usd"],
                "latency_p50_ms": lat["total_ms"]["p50"],
                "ttft_p50_ms": lat["ttft_ms"]["p50"],
            }
        )
    trimming = [
        {**_run_row(name, run), "input_tokens": usage(run)["input_tokens"]}
        for name, run in [
            ("2,000-token budget", "long-budget-2000"),
            ("no trimming", "long-budget-0"),
        ]
    ]
    return {
        "source": "uv run python -m evals variants",
        "routing": [
            _run_row("always Sonnet 5.5", "matrix-claude-sonnet-5-5"),
            _run_row("rule router", "routed-golden"),
            _run_row("always Haiku 5.5", "matrix-claude-haiku-5-5"),
        ],
        "caching": caching,
        "trimming": trimming,
    }


def experiments_section() -> dict | None:
    path = REPORTS / "experiments.json"
    if not path.exists():
        return None
    data = _read(path)
    return {"source": "uv run python -m evals experiments", **data}


def gate_section() -> dict:
    base = _read(REPORTS / "baseline" / "smoke" / "baseline.json")
    return {
        "source": "uv run python -m evals baseline <run_id>",
        "baseline_run": base["run_id"],
        "model": base["model"],
        "prompt_version": base["prompt_version"],
        "n_cases": base["n_cases"],
        "pass_rate": base["overall_pass_rate"],
    }


def calibration_section() -> dict:
    reports = sorted(CALIBRATION_DIR.glob("judge-*.json")) if CALIBRATION_DIR.exists() else []
    rows = []
    for path in reports:
        r = _read(path)
        test = r["results"].get("test", {}).get(MAIN_DIMENSION)
        rows.append(
            {
                "judge_version": r["judge_version"],
                "n_labeled": r["n_labeled_items"],
                "main_dimension": MAIN_DIMENSION,
                "test_kappa": test["kappa"] if test else None,
                "test_kappa_ci95": test["kappa_ci95"] if test else None,
                "test_n": test["n"] if test else 0,
            }
        )
    return {
        "source": "uv run python -m evals calibrate-judge --judge-version <v>",
        "rows": rows,
        "status": "measured" if rows else "waiting for human labels",
    }


def golden_section() -> dict:
    cases = load_cases()
    counts = Counter(c.category.value for c in cases)
    return {
        "source": "uv run python -m evals validate",
        "n_cases": len(cases),
        "by_category": {c.value: counts.get(c.value, 0) for c in Category},
        "human_reviewed": sum(c.authored_by != "llm_drafted" for c in cases),
        "smoke": sum("smoke" in c.tags for c in cases),
    }


def build() -> dict:
    data = {
        "note": "Generated by `uv run python -m evals dashboard` from committed reports.",
        "golden": golden_section(),
        "models": models_section(),
        "guardrails": guardrails_section(),
        "end_to_end": end_to_end_section(),
        "variants": variants_section(),
        "gate": gate_section(),
        "experiments": experiments_section(),
        "calibration": calibration_section(),
    }
    return {**data, "story": build_story(data)}


def render(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def write(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(build()))
    return path


def is_current(path: Path = OUT) -> bool:
    return path.exists() and path.read_text() == render(build())
