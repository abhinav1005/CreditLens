"""Judge calibration: how well does the LLM judge agree with human labels?

    uv run python -m evals calibrate-judge --judge-version v1 --labeler abhinav

For every hand-labeled pool item, the pinned judge grades the same reply (cached by item,
judge model and judge prompt hash, so reruns are free). Then, per rubric dimension and per
split (dev / test / all):

- precision, recall, F1 for detecting FAILURES (fail is the positive class: the judge's
  job is to catch bad replies)
- accuracy
- Cohen's kappa (agreement beyond chance) with a bootstrap 95% confidence interval
- the confusion matrix

Also: kappa on Sonnet-written vs Haiku-written replies (does the Sonnet judge go easier on
Sonnet?), and human-vs-human kappa when a second labeler labeled the same items.

The headline is `test` (frozen before any judge iteration); `dev` is for tuning.
"""

import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from evals.cache import ResponseCache
from evals.cases import Case, load_cases
from evals.judge import DIMENSIONS, judge_response, load_judge_prompt
from evals.labeler import load_labels
from evals.labeling import load_pool
from evals.scorers.base import CaseOutput
from evals.split import load_split

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_DIR = ROOT / "reports" / "calibration"
MAIN_DIMENSION = "compliance"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 7


def kappa(human: list[str], judge: list[str]) -> float | None:
    """Cohen's kappa = (p_o - p_e) / (1 - p_e).

    p_o: share of items where the two raters agree.
    p_e: agreement expected by chance, from each rater's own fail/pass rates.
    None when undefined (p_e = 1, e.g. both raters gave every item the same class).
    Written out by hand (tests check it equals sklearn's) because the bootstrap calls it
    thousands of times.
    """
    n = len(human)
    if n == 0:
        return None
    p_o = sum(h == j for h, j in zip(human, judge, strict=True)) / n
    h_fail, j_fail = human.count("fail") / n, judge.count("fail") / n
    p_e = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if math.isclose(p_e, 1.0):
        return None
    return (p_o - p_e) / (1 - p_e)


def bootstrap_ci(
    human: list[str], judge: list[str], samples: int = BOOTSTRAP_SAMPLES
) -> list[float] | None:
    """95% percentile interval of kappa over resampled (human, judge) pairs."""
    if len(human) < 5:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    n, values = len(human), []
    for _ in range(samples):
        idx = [rng.randrange(n) for _ in range(n)]
        k = kappa([human[i] for i in idx], [judge[i] for i in idx])
        if k is not None:
            values.append(k)
    if len(values) < samples * 0.5:
        return None
    values.sort()
    return [
        round(values[int(0.025 * len(values))], 3),
        round(values[int(0.975 * len(values)) - 1], 3),
    ]


def agreement(human: list[str], judge: list[str]) -> dict:
    n = len(human)
    if n == 0:
        return {"n": 0}
    p, r, f, _ = precision_recall_fscore_support(
        human, judge, labels=["fail"], average=None, zero_division=0
    )
    cm = confusion_matrix(human, judge, labels=["fail", "pass"])
    k = kappa(human, judge)
    return {
        "n": n,
        "human_fail_rate": round(human.count("fail") / n, 3),
        "judge_fail_rate": round(judge.count("fail") / n, 3),
        "precision_fail": round(float(p[0]), 3),
        "recall_fail": round(float(r[0]), 3),
        "f1_fail": round(float(f[0]), 3),
        "accuracy": round(sum(h == j for h, j in zip(human, judge, strict=True)) / n, 3),
        "kappa": None if k is None else round(k, 3),
        "kappa_ci95": bootstrap_ci(human, judge),
        # rows = human (fail, pass), cols = judge (fail, pass)
        "confusion": {"human_fail": cm[0].tolist(), "human_pass": cm[1].tolist()},
    }


def judge_cache_key(item: dict, judge_model: str, prompt_hash: str) -> str:
    raw = json.dumps(
        {"item": item["item_id"], "model": judge_model, "prompt": prompt_hash}, sort_keys=True
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def case_output(item: dict) -> CaseOutput:
    r = item["record"]
    return CaseOutput(
        kind=r["kind"],
        final_text=r.get("final_text", ""),
        tool_calls=r["tool_calls"],
        stop=r.get("stop", "complete"),
        cards=r.get("cards"),
        retries=r.get("retries", 0),
    )


def judge_items(
    items: list[dict],
    cases: dict[str, Case],
    version: str,
    *,
    cache: ResponseCache,
    max_cost_usd: float,
    judge=judge_response,
) -> tuple[dict[str, dict], float]:
    from assistant.config import load_config

    config = load_config()
    _, prompt_hash = load_judge_prompt(version)
    verdicts, spent = {}, 0.0
    for item in items:
        key = judge_cache_key(item, config.judge.model, prompt_hash)
        cached = cache.get(key)
        if cached is None:
            if spent > max_cost_usd:
                raise RuntimeError(
                    f"judge spend ${spent:.2f} passed --max-cost-usd ${max_cost_usd:.2f}"
                )
            result = judge(
                cases[item["case_id"]], case_output(item), config=config, version=version
            )
            cached = result.to_dict()
            spent += result.cost_usd
            if result.verdicts is not None:
                cache.put(key, cached)
        if cached["verdicts"] is not None:
            verdicts[item["item_id"]] = cached["verdicts"]
    return verdicts, spent


def calibrate(
    version: str,
    labeler: str | None,
    *,
    max_cost_usd: float,
    cache_dir: Path | None = None,
    judge=judge_response,
    labels: list[dict] | None = None,
    pool: list[dict] | None = None,
    split: dict[str, str] | None = None,
) -> dict:
    from assistant.config import load_config

    config = load_config()
    pool = pool if pool is not None else load_pool()
    split = split if split is not None else load_split()
    all_labels = labels if labels is not None else load_labels()
    by_item = {i["item_id"]: i for i in pool}
    mine = [lab for lab in all_labels if labeler is None or lab["labeler"] == labeler]
    first_label = {}
    for lab in mine:  # one label per item: the first one recorded
        first_label.setdefault(lab["item_id"], lab)
    items = [by_item[i] for i in first_label if i in by_item]
    cache = ResponseCache(cache_dir or ROOT / ".cache" / "judge")
    cases = {c.id: c for c in load_cases()}
    verdicts, spent = judge_items(
        items, cases, version, cache=cache, max_cost_usd=max_cost_usd, judge=judge
    )

    groups: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if item["item_id"] not in verdicts:
            continue
        groups["all"].append(item["item_id"])
        groups[split.get(item["item_id"], "dev")].append(item["item_id"])
        family = (
            "sonnet"
            if "sonnet" in item["model"]
            else "haiku" if "haiku" in item["model"] else "other"
        )
        groups[f"written_by_{family}"].append(item["item_id"])

    results = {}
    for group, ids in sorted(groups.items()):
        results[group] = {
            dim: agreement(
                [first_label[i]["verdicts"][dim] for i in ids],
                [verdicts[i][dim]["verdict"] for i in ids],
            )
            for dim in DIMENSIONS
        }

    human_human = {}
    labelers = sorted({lab["labeler"] for lab in all_labels})
    if len(labelers) >= 2:
        a, b = labelers[0], labelers[1]
        la = {lab["item_id"]: lab for lab in all_labels if lab["labeler"] == a}
        lb = {lab["item_id"]: lab for lab in all_labels if lab["labeler"] == b}
        shared = sorted(set(la) & set(lb))
        human_human = (
            {
                "labelers": [a, b],
                "n_shared": len(shared),
                **{
                    dim: agreement(
                        [la[i]["verdicts"][dim] for i in shared],
                        [lb[i]["verdicts"][dim] for i in shared],
                    )
                    for dim in DIMENSIONS
                },
            }
            if shared
            else {}
        )

    _, prompt_hash = load_judge_prompt(version)
    return {
        "judge_version": version,
        "judge_prompt_hash": prompt_hash,
        "judge_model": config.judge.model,
        "labeler": labeler,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "main_dimension": MAIN_DIMENSION,
        "n_labeled_items": len(items),
        "n_judged": len(verdicts),
        "judge_spend_usd": round(spent, 4),
        "results": results,
        "human_human": human_human,
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_ci(ci: list[float] | None) -> str:
    return "n/a" if ci is None else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def render_markdown(report: dict) -> str:
    lines = [
        f"# Judge calibration: `{report['judge_version']}` (hash `{report['judge_prompt_hash']}`)",
        "",
        f"- Judge model: `{report['judge_model']}` · Labeler: `{report['labeler']}`",
        f"- Created: {report['created_at']}",
        f"- Labeled items: {report['n_labeled_items']} · judged: {report['n_judged']}",
        "- Positive class = **fail**. Headline = `test` split (frozen before judge iteration).",
        "",
    ]
    for group in ["test", "dev", "all", "written_by_sonnet", "written_by_haiku"]:
        if group not in report["results"]:
            continue
        header = (
            "| Dimension | n | Human fail % | Judge fail % | Precision | Recall | F1 "
            "| Accuracy | Kappa | 95% CI |"
        )
        lines += [f"## {group}", "", header, "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for dim, m in report["results"][group].items():
            if m["n"] == 0:
                continue
            star = " **(main)**" if dim == report["main_dimension"] else ""
            cells = [
                f"{dim}{star}",
                str(m["n"]),
                f"{100 * m['human_fail_rate']:.0f}%",
                f"{100 * m['judge_fail_rate']:.0f}%",
                f"{m['precision_fail']:.2f}",
                f"{m['recall_fail']:.2f}",
                f"{m['f1_fail']:.2f}",
                f"{m['accuracy']:.2f}",
                _fmt(m["kappa"]),
                _fmt_ci(m["kappa_ci95"]),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    if report["human_human"]:
        hh = report["human_human"]
        lines += [
            f"## Human vs human ({' vs '.join(hh['labelers'])}, {hh['n_shared']} shared items)",
            "",
        ]
        for dim in DIMENSIONS:
            lines.append(f"- {dim}: kappa {_fmt(hh[dim]['kappa'])}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_report(report: dict) -> Path:
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    base = CALIBRATION_DIR / f"judge-{report['judge_version']}"
    base.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    base.with_suffix(".md").write_text(render_markdown(report))
    return base.with_suffix(".md")
