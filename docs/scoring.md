# Toy scoring formula

**This is not a real credit-scoring model.** It exists so that every score in the synthetic
data has a cause that can be read straight off the profile, which lets evals check whether
the assistant's explanation of a score change is correct. Code: `src/credit/scoring.py`.

```
score = 850 − (sum of the six factor penalties), clamped to 300..850
```

Each penalty is computed for one month from the profile's state in that month.

| Factor | Penalty |
|---|---|
| `UTILIZATION` | 150 × (total balance on open cards ÷ total limit on open cards), with utilization capped at 100%. 0 if there are no open cards. |
| `PAYMENT_HISTORY` | Per late payment in the last 24 months: 30 days → 40, 60 days → 60, 90 days → 80. Lates older than 12 months count half. Capped at 200. |
| `RECENT_INQUIRIES` | 12 per hard inquiry in the last 12 months. Capped at 60. |
| `ACCOUNT_AGE` | 0.7 × (84 − average age of open accounts in months), never below 0. |
| `CREDIT_MIX` | Distinct open account types: 1 → 30, 2 → 15, 3 or more → 0. |
| `DEROGATORY` | 100 per collection or charge-off on file. Capped at 200. |

"Top factors" for a month are the factors with the largest non-zero penalties (ties broken
in the order listed above).

## Example

Open cards with $1,500 balance on $5,000 of limit (30% utilization → 45), no lates (0),
one inquiry this year (12), average account age 60 months (0.7 × 24 = 17), two account
types (15), no derogatory marks (0): score = 850 − 89 = **761**.
