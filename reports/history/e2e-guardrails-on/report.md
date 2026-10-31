# Eval report: e2e-guardrails-on

- Suite: `golden` · Model: `claude-sonnet-5-5`
- Prompt: `v1` (hash `b83927f5d3e2c723`)
- Commit: `3059747` (dirty) · Pricing as of 2026-10-06
- Cases: 55 · Cache hits: 0 · Status: {'ok': 55}
- ⚠️ 55 case(s) are LLM-drafted and not yet human-reviewed.

## Overall pass rate: 100.0% (55/55)

| Category | Passed | Pass rate |
|---|---:|---:|
| compliance | 20/20 | 100.0% |
| injection | 20/20 | 100.0% |
| pii | 15/15 | 100.0% |

## Cost and latency

- Measured cost: $0.5289 total, $0.00962 per case
- API spend this run: $0.5289 (estimate before run: $0.9196)
- Latency p50 5,944 ms, p95 9,631 ms (measured under parallel load; M4.2 adds a clean sequential run)

## LLM judge (`v1`, `claude-sonnet-5-5`)

Mode `report`: shown only, not counted.

Judge spend this run: $0.4047

| Category | helpfulness | clarity | compliance | groundedness |
|---|---:|---:|---:|---:|
| compliance | 100.0% | 100.0% | 100.0% | 95.0% |
| injection | 80.0% | 90.0% | 100.0% | 75.0% |
| pii | 100.0% | 93.3% | 100.0% | 100.0% |

## Guardrails (on)

Measured on each guardrail's held-out test set (`python -m evals guardrail <name>`):

| Guardrail | Recall | Precision | False-positive rate |
|---|---:|---:|---:|
| pii | 91.4% | 100.0% | 0.0% |
| injection | 100.0% | n/a | 0.0% |
| compliance | 100.0% | n/a | 0.0% |

In this run: 10 blocked turn(s); compliance checked 45, regenerated 0, fell back 0.

- `injection:input:block`: 10
- `injection:tool_result:rewrite`: 10
- `pii:input:redact`: 12

## Failed checks by scorer

- none

## Failing cases (0)

