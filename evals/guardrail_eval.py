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
    if name == "pii":
        report = {"guardrail": name, "split": split, **evaluate_pii(items)}
        markdown = render_pii(report, split)
    elif name == "injection":
        rules_only, combined = evaluate_injection(items, use_llm=False), evaluate_injection(items)
        report = {"guardrail": name, "split": split, "rules_only": rules_only, **combined}
        markdown = render_injection(rules_only, combined, split)
    elif name == "compliance":
        rules_only, combined = evaluate_compliance(items, use_llm=False), evaluate_compliance(items)
        report = {"guardrail": name, "split": split, "rules_only": rules_only, **combined}
        markdown = render_compliance(rules_only, combined, split)
    else:
        raise ValueError(f"no evaluator for guardrail {name!r}")
    GUARDRAIL_REPORTS.mkdir(parents=True, exist_ok=True)
    (GUARDRAIL_REPORTS / f"{name}-{split}.json").write_text(json.dumps(report, indent=2) + "\n")
    md = GUARDRAIL_REPORTS / f"{name}-{split}.md"
    md.write_text(markdown)
    return report, md


def evaluate_injection(items: list[dict], use_llm: bool = True) -> dict:
    """Recall on attacks and false-positive rate on benign texts, per kind and layer."""
    from guardrails.injection import is_injection

    by_kind: dict[str, list[bool]] = defaultdict(list)
    layer_counts: dict[str, int] = defaultdict(int)
    errors, cost = [], 0.0
    for item in items:
        flagged, info = is_injection(item["text"], use_llm=use_llm)
        cost += info.get("cost", 0.0)
        layer_counts[info["layer"]] += 1
        correct = flagged == (item["label"] == "injection")
        by_kind[item["kind"]].append(flagged)
        if not correct:
            errors.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "flagged": flagged,
                    "layer": info["layer"],
                    "text": item["text"][:120],
                }
            )
    attacks = [f for k in ("direct", "indirect") for f in by_kind.get(k, [])]
    benign = [f for k in ("benign_hard", "benign") for f in by_kind.get(k, [])]
    rate = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    return {
        "use_llm": use_llm,
        "n_attacks": len(attacks),
        "n_benign": len(benign),
        "recall": rate(attacks),
        "false_positive_rate": rate(benign),
        "flag_rate_by_kind": {k: rate(v) for k, v in sorted(by_kind.items())},
        "decided_by_layer": dict(layer_counts),
        "classifier_cost_usd": round(cost, 5),
        "errors": errors,
    }


def render_injection(rules_only: dict, combined: dict, split: str) -> str:
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"  # noqa: E731
    lines = [
        f"# Prompt-injection guardrail ({split} split)",
        "",
        f"Attacks: {combined['n_attacks']} · benign: {combined['n_benign']} (most are hard negatives)",
        "",
        "| Layers | Recall (target ≥ 90%) | False-positive rate (target ≤ 5%) |",
        "|---|---:|---:|",
        f"| rules only | {pct(rules_only['recall'])} | {pct(rules_only['false_positive_rate'])} |",
        f"| rules + LLM classifier | {pct(combined['recall'])} | {pct(combined['false_positive_rate'])} |",
        "",
        "Flag rate by kind (rules + LLM): "
        + ", ".join(f"{k} {pct(v)}" for k, v in combined["flag_rate_by_kind"].items()),
        "",
        f"Classifier spend this run: ${combined['classifier_cost_usd']:.4f} (cached verdicts cost $0)",
        "",
        f"## Errors, rules + LLM ({len(combined['errors'])})",
        "",
    ]
    lines += [
        f"- `{e['id']}` {e['kind']} {'flagged' if e['flagged'] else 'missed'} ({e['layer']}): {e['text']}"
        for e in combined["errors"]
    ] or ["- none"]
    return "\n".join(lines) + "\n"


def evaluate_compliance(items: list[dict], use_llm: bool = True) -> dict:
    """Detection of policy violations in replies: recall on violations, FP rate on compliant."""
    from guardrails.compliance import ComplianceGuard

    guard = ComplianceGuard(use_llm=use_llm)
    by_kind: dict[str, list[bool]] = defaultdict(list)
    per_rule: dict[str, list[bool]] = defaultdict(list)
    errors, cost, layers = [], 0.0, defaultdict(int)
    for item in items:
        rules, info = guard.final_check(item["text"])
        cost += info.get("cost", 0.0)
        layers[info["layer"]] += 1
        flagged = bool(rules)
        by_kind[item["kind"]].append(flagged)
        for r in item["violations"]:
            per_rule[r].append(flagged)
        if flagged != bool(item["violations"]):
            errors.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "flagged": flagged,
                    "rules": rules,
                    "layer": info["layer"],
                    "text": item["text"][:120],
                }
            )
    rate = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    compliant = by_kind.get("compliant_hard", []) + by_kind.get("compliant", [])
    return {
        "use_llm": use_llm,
        "n_violations": len(by_kind.get("violation", [])),
        "n_compliant": len(compliant),
        "recall": rate(by_kind.get("violation", [])),
        "false_positive_rate": rate(compliant),
        "recall_by_rule": {r: rate(v) for r, v in sorted(per_rule.items())},
        "flag_rate_by_kind": {k: rate(v) for k, v in sorted(by_kind.items())},
        "decided_by_layer": dict(layers),
        "classifier_cost_usd": round(cost, 5),
        "errors": errors,
    }


def render_compliance(rules_only: dict, combined: dict, split: str) -> str:
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"  # noqa: E731
    lines = [
        f"# Compliance guardrail ({split} split)",
        "",
        f"Violating replies: {combined['n_violations']} · compliant: {combined['n_compliant']} (most are hard negatives)",
        "",
        "| Layers | Recall | False-positive rate |",
        "|---|---:|---:|",
        f"| rules only | {pct(rules_only['recall'])} | {pct(rules_only['false_positive_rate'])} |",
        f"| rules + LLM classifier | {pct(combined['recall'])} | {pct(combined['false_positive_rate'])} |",
        "",
        "Recall by rule (rules + LLM): "
        + ", ".join(f"{k} {pct(v)}" for k, v in combined["recall_by_rule"].items()),
        "",
        f"Classifier spend this run: ${combined['classifier_cost_usd']:.4f}",
        "",
        f"## Errors, rules + LLM ({len(combined['errors'])})",
        "",
    ]
    lines += [
        f"- `{e['id']}` {e['kind']} {'flagged ' + str(e['rules']) if e['flagged'] else 'missed'} ({e['layer']}): {e['text']}"
        for e in combined["errors"]
    ] or ["- none"]
    return "\n".join(lines) + "\n"
