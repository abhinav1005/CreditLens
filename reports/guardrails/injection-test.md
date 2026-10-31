# Prompt-injection guardrail (test split)

Attacks: 16 · benign: 36 (most are hard negatives)

| Layers | Recall (target ≥ 90%) | False-positive rate (target ≤ 5%) |
|---|---:|---:|
| rules only | 43.8% | 0.0% |
| rules + LLM classifier | 100.0% | 0.0% |

Flag rate by kind (rules + LLM): benign 0.0%, benign_hard 0.0%, direct 100.0%, indirect 100.0%

Classifier spend this run: $0.0049 (cached verdicts cost $0)

## Errors, rules + LLM (0)

- none
