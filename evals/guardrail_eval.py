"""Measure a guardrail on its own labeled test set.

    uv run python -m evals guardrail pii [--split test]

PII metrics:
- recall: share of expected PII values that no longer appear in the redacted text
  (per entity type and overall). This is the PRD's ≥95% target.
- precision: share of redacted spans that overlap an expected PII value.
- negative false-positive rate: share of no-PII items where anything was redacted.

Tune on `dev`; the reported number is `test`.
"""

import json
from collections import defaultdict
from pathlib import Path

from evals.cases import DATASETS_DIR

ROOT = Path(__file__).resolve().parents[1]
GUARDRAIL_REPORTS = ROOT / "reports" / "guardrails"


def load_set(name: str) -> list[dict]:
    path = DATASETS_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate_pii(items: list[dict]) -> dict:
    from guardrails.pii import INPUT_ENTITIES, PIIRedactor, detect

    guard = PIIRedactor()
    found_by_type, total_by_type = defaultdict(int), defaultdict(int)
    span_hits = span_total = 0
    negatives = negative_fp = 0
    misses, false_positives = [], []
    for item in items:
        redacted = guard.check(item["text"], {"stage": "input"}).text
        spans = detect(item["text"], INPUT_ENTITIES)
        expected = [(item["text"].find(p["value"]), p) for p in item["pii"]]
        for start, end, entity in spans:
            span_total += 1
            hit = any(
                s >= 0 and not (end <= s or start >= s + len(p["value"])) for s, p in expected
            )
            span_hits += hit
            if not hit:
                false_positives.append(
                    {"id": item["id"], "span": item["text"][start:end], "entity": entity}
                )
        for p in item["pii"]:
            total_by_type[p["type"]] += 1
            if p["value"] not in redacted:
                found_by_type[p["type"]] += 1
            else:
                misses.append({"id": item["id"], "type": p["type"], "value": p["value"]})
        if not item["pii"]:
            negatives += 1
            negative_fp += redacted != item["text"]
    total = sum(total_by_type.values())
    return {
        "n_items": len(items),
        "n_pii_values": total,
        "recall": round(sum(found_by_type.values()) / total, 4) if total else None,
        "recall_by_type": {
            t: round(found_by_type[t] / n, 4) for t, n in sorted(total_by_type.items())
        },
        "precision": round(span_hits / span_total, 4) if span_total else None,
        "n_negatives": negatives,
        "negative_false_positive_rate": round(negative_fp / negatives, 4) if negatives else None,
        "misses": misses,
        "false_positives": false_positives,
    }


def render_pii(report: dict, split: str) -> str:
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"  # noqa: E731
    lines = [
        f"# PII guardrail ({split} split)",
        "",
        f"- Items: {report['n_items']} · PII values: {report['n_pii_values']}"
        f" · negatives: {report['n_negatives']}",
        f"- **Recall: {pct(report['recall'])}** (target ≥ 95%)",
        f"- Precision: {pct(report['precision'])}",
        f"- False-positive rate on negatives: {pct(report['negative_false_positive_rate'])}",
        "",
        "| Type | Recall |",
        "|---|---:|",
    ]
    lines += [f"| {t} | {pct(r)} |" for t, r in report["recall_by_type"].items()]
    lines += ["", f"## Misses ({len(report['misses'])})", ""]
    lines += [f"- `{m['id']}` {m['type']}: `{m['value']}`" for m in report["misses"]] or ["- none"]
    lines += ["", f"## False-positive spans ({len(report['false_positives'])})", ""]
    lines += [f"- `{f['id']}` {f['entity']}: `{f['span']}`" for f in report["false_positives"]] or [
        "- none"
    ]
    return "\n".join(lines) + "\n"


def run_guardrail_eval(name: str, split: str) -> tuple[dict, Path]:
    items = [i for i in load_set(name) if split == "all" or i["split"] == split]
    if name != "pii":
        raise ValueError(f"no evaluator for guardrail {name!r} yet")
    report = {"guardrail": name, "split": split, **evaluate_pii(items)}
    GUARDRAIL_REPORTS.mkdir(parents=True, exist_ok=True)
    (GUARDRAIL_REPORTS / f"{name}-{split}.json").write_text(json.dumps(report, indent=2) + "\n")
    md = GUARDRAIL_REPORTS / f"{name}-{split}.md"
    md.write_text(render_pii(report, split))
    return report, md
