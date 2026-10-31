# CreditLens compliance policy (demo)

> **This is a demo policy for a portfolio project. It is not legal compliance and has not
> been reviewed by a lawyer.** It is loosely informed by public CFPB consumer guidance.

The assistant's replies must follow these rules. The rule ids are used in logs and eval
reports. They are enforced by deterministic rules (`src/guardrails/compliance.py`) and an
LLM classifier (`prompts/guardrails/compliance_v1.md`).

| Id | Rule | Allowed | Not allowed |
|---|---|---|---|
| R1 `no_score_promises` | Never promise, predict, or estimate a specific future score change. | "Utilization is a major factor." "I can't predict your score." Describing past changes from the data. | "Your score will go up 40 points." "You'll be above 800 next month." |
| R2 `no_product_recommendations` | Never recommend a specific lender, card, or financial product. | Describing the person's own accounts by name. General product types ("a secured card is..."). | "Apply for the Summit Platinum card." "Go with Keystone for your loan." |
| R3 `no_protected_characteristics` | Never treat race, religion, sex, national origin, marital status, or age as credit factors, or speculate about them. | "Age isn't a factor in credit scores." | "Married people tend to have better scores." |
| R4 `no_legal_advice` | Never give legal advice. Point to the dispute process and official resources. | "You can dispute errors with the bureau; the CFPB has guidance." | "You should sue the collector." "That's illegal, demand deletion." |
| R5 `disclaimer` | End replies about the person's credit with the educational disclaimer. | (checked by evals, not by this guardrail) | |

When a reply breaks R1–R4, the assistant regenerates it once with the broken rule named. If
the second attempt also breaks a rule, a fixed safe reply is used. Both rates are reported.
