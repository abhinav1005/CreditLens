# Compliance guardrail (test split)

Violating replies: 19 · compliant: 16 (most are hard negatives)

| Layers | Recall | False-positive rate |
|---|---:|---:|
| rules only | 36.8% | 0.0% |
| rules + LLM classifier | 100.0% | 0.0% |

Recall by rule (rules + LLM): no_legal_advice 100.0%, no_product_recommendations 100.0%, no_protected_characteristics 100.0%, no_score_promises 100.0%

Classifier spend this run: $0.0037

## Errors, rules + LLM (0)

- none
