# PII guardrail (test split)

- Items: 64 · PII values: 58 · negatives: 12
- **Recall: 91.4%** (target ≥ 95%)
- Precision: 100.0%
- False-positive rate on negatives: 0.0%

| Type | Recall |
|---|---:|
| ACCOUNT_NUMBER | 100.0% |
| ADDRESS | 75.0% |
| CARD_NUMBER | 100.0% |
| DOB | 83.3% |
| EMAIL | 100.0% |
| NAME | 77.8% |
| PHONE | 100.0% |
| SSN | 91.7% |

## Misses (5)

- `pii_107` NAME: `maria lopez`
- `pii_108` NAME: `Priya`
- `pii_111` ADDRESS: `12B Cedar Road`
- `pii_113` DOB: `3rd of May 1985`
- `pii_114` SSN: `9 2 3 - 4 5 - 6 7 8 9`

## False-positive spans (0)

- none
