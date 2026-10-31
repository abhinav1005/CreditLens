# Model comparison

Golden suite (150 cases), prompt v1, guardrails on. Pricing as of 2026-10-06.
Reproduce: `uv run python -m evals latency --models <ids> --tags smoke` then `uv run python -m evals matrix --models <ids>`.

| Model | Pass rate | Judge: helpful | Judge: compliant | Judge: grounded | Cost / case | Latency p50 / p95 (total) | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `claude-sonnet-5-5` | 90.7% | 97.3% | 98.7% | 95.3% | $0.0106 | 5.9s / 8.1s | 2.4s |
| `claude-haiku-5-5` | 94.7% | 96.0% | 100.0% | 94.7% | $0.0006 | 4.0s / 6.7s | 1.9s |
| `claude-haiku-4-5-20251001` | 78.7% | 96.0% | 98.7% | 83.3% | $0.0042 | 4.2s / 7.6s | 0.7s |

## Pass rate by category

| Category | `claude-sonnet-5-5` | `claude-haiku-5-5` | `claude-haiku-4-5-20251001` |
|---|---:|---:|---:|
| compliance | 100.0% | 100.0% | 100.0% |
| factual | 100.0% | 93.3% | 66.7% |
| injection | 100.0% | 100.0% | 95.0% |
| insight_grounding | 30.0% | 70.0% | 25.0% |
| pii | 100.0% | 100.0% | 100.0% |
| refusal | 100.0% | 100.0% | 73.3% |
| tool_use | 100.0% | 100.0% | 93.3% |

Latency comes from a sequential run of the smoke subset with fresh calls (`reports/latency/`); costs include the assistant's guardrail classifier calls but not the judge.
