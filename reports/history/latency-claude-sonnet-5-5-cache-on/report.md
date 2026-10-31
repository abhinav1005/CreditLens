# Eval report: latency-claude-sonnet-5-5-cache-on

- Suite: `latency` · Model: `claude-sonnet-5-5`
- Prompt: `v1` (hash `b83927f5d3e2c723`)
- Commit: `9302a1c` · Pricing as of 2026-10-06
- Cases: 41 · Cache hits: 0 · Status: {'ok': 41}
- ⚠️ 41 case(s) are LLM-drafted and not yet human-reviewed.

## Overall pass rate: 90.2% (37/41)

| Category | Passed | Pass rate |
|---|---:|---:|
| compliance | 6/6 | 100.0% |
| factual | 5/6 | 83.3% |
| injection | 6/6 | 100.0% |
| insight_grounding | 2/5 | 40.0% |
| pii | 5/5 | 100.0% |
| refusal | 5/5 | 100.0% |
| tool_use | 8/8 | 100.0% |

## Cost and latency

- Measured cost: $0.3859 total, $0.00941 per case
- API spend this run: $0.3859 (estimate before run: $0.6855)
- Latency p50 4,544 ms, p95 7,381 ms (measured under parallel load; M4.2 adds a clean sequential run)

## Guardrails (on)

Measured on each guardrail's held-out test set (`python -m evals guardrail <name>`):

| Guardrail | Recall | Precision | False-positive rate |
|---|---:|---:|---:|
| pii | 91.4% | 100.0% | 0.0% |
| injection | 100.0% | n/a | 0.0% |
| compliance | 100.0% | n/a | 0.0% |

In this run: 4 blocked turn(s); compliance checked 32, regenerated 0, fell back 0.

- `injection:input:block`: 4
- `injection:tool_result:rewrite`: 3
- `pii:input:redact`: 5

## Failed checks by scorer

- grounding: 1
- insights: 3

## Failing cases (4)

- **fact_011** [factual]: `numeric_grounding` (ungrounded: ['10,000', '3,000'])
- **ins_008** [insight_grounding]: `card1:summary_in_evidence` (not in evidence: ['1'])
- **ins_009** [insight_grounding]: `card0:summary_in_evidence` (not in evidence: ['2025', '2025'])
- **ins_010** [insight_grounding]: `card1:summary_in_evidence` (not in evidence: ['3'])
