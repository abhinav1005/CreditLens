# Eval report: long-budget-2000

- Suite: `long` · Model: `claude-sonnet-5-5`
- Prompt: `v1` (hash `b83927f5d3e2c723`)
- Commit: `9302a1c` (dirty) · Pricing as of 2026-10-06
- Cases: 5 · Cache hits: 0 · Status: {'ok': 5}
- ⚠️ 5 case(s) are LLM-drafted and not yet human-reviewed.

## Overall pass rate: 100.0% (5/5)

| Category | Passed | Pass rate |
|---|---:|---:|
| tool_use | 5/5 | 100.0% |

## Cost and latency

- Measured cost: $0.1079 total, $0.02158 per case
- API spend this run: $0.1079 (estimate before run: $0.0836)
- Latency p50 40,785 ms, p95 43,315 ms (measured under parallel load; M4.2 adds a clean sequential run)

## Guardrails (on)

Measured on each guardrail's held-out test set (`python -m evals guardrail <name>`):

| Guardrail | Recall | Precision | False-positive rate |
|---|---:|---:|---:|
| pii | 91.4% | 100.0% | 0.0% |
| injection | 100.0% | n/a | 0.0% |
| compliance | 100.0% | n/a | 0.0% |

In this run: 0 blocked turn(s); compliance checked 5, regenerated 0, fell back 0.

## Failed checks by scorer

- none

## Failing cases (0)

