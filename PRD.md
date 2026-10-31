# CreditLens — Product Requirements Document

**Owner:** Abhinav Khanna
**Status:** Draft v2 (2026-10-31). §14 records design decisions and takes precedence over earlier sections where they conflict.
**One-line summary:** A consumer credit-education chat assistant wrapped in a production-style **evaluation, guardrail, and model-comparison system**. The assistant is the test subject; the quality system around it is the product.

---

## 1. Why this exists

This is a portfolio project built to demonstrate applied-AI quality engineering: measuring, guarding, and improving an LLM assistant with evidence. It is modeled on the kind of work done on consumer financial AI assistants (e.g. personalized credit insights + a chat assistant).

Skills it must demonstrate, each with real, inspectable artifacts:

| Skill | Where it shows up |
|---|---|
| Prompt design, tool calling, structured outputs, streaming | Assistant service (§5.1) |
| Evaluation framework: golden sets, regression suites, LLM-as-judge | Eval system (§5.3) |
| Measuring evaluator reliability against human labels (precision, recall, agreement) | Judge calibration (§5.3.4) |
| Guardrails: input/output classifiers, PII redaction, prompt-injection defense, compliance rules | Guardrail layer (§5.2) |
| Model upgrades: comparing quality, cost, latency | Model comparison (§5.4) |
| Cost/latency reduction: prompt caching, model routing, context management | §5.4 |
| Tools for analysts/QA: transcript viewer, labeling workflow, dashboards | Analyst UI (§5.5) |
| Python + Java microservices | Python assistant + Spring Boot tool service (§5.6) |
| AWS (S3, Lambda, DynamoDB; Bedrock optional) | Deployment (§7) |
| CI/CD, code review hygiene, tests | §8 |

**Hard rule:** every number that ends up in the README or on a resume must come from a reproducible script in this repo. No hand-typed metrics.

## 2. Goals and non-goals

### Goals
1. A working chat assistant that answers credit-education questions about a **synthetic** user's credit profile using tools.
2. An eval framework that runs locally and in CI, blocks regressions, and produces a versioned report.
3. An LLM judge whose reliability is measured against human labels.
4. Guardrails whose effectiveness is itself measured by evals.
5. A model comparison report (quality × cost × latency) and a measured cost reduction from caching/routing.
6. A small analyst UI for reviewing transcripts, labeling them, and promoting failures to test cases.
7. A clean README with architecture diagram, results tables, and how to reproduce.

### Non-goals
- **No real credit data, ever.** All profiles are generated. No real names, SSNs, or account numbers (the PII test set uses fake-but-realistic formats).
- Not a real financial advice product; it is an educational demo with a visible disclaimer.
- No user accounts/auth beyond a simple API key for the deployed demo.
- No fine-tuning or model training.
- No Kubernetes.

## 3. Users (personas for the demo)

| Persona | Needs |
|---|---|
| **Consumer** (end user) | Ask "why did my score drop?", "how does utilization work?", "what if I pay off card X?" and get grounded, compliant, plain-language answers. |
| **Conversation Analyst** | Browse transcripts, see guardrail/judge flags, label responses, turn bad conversations into test cases. |
| **QA / AI engineer** (you) | Change a prompt or model, run the suite, see exactly what got better or worse before merging. |

## 4. Architecture

```
            React UI (chat + analyst views)
                     │  SSE
                     ▼
   ┌──────────────────────────────────────────┐
   │ FastAPI assistant service (Python)       │
   │  ┌───────────┐  ┌──────────┐  ┌────────┐ │
   │  │ input     │→ │ LLM +    │→ │ output │ │
   │  │ guardrails│  │ tool loop│  │ guards │ │
   │  └───────────┘  └────┬─────┘  └────────┘ │
   │        model router  │                   │
   └──────────────────────┼───────────────────┘
                          │ REST
                          ▼
          Spring Boot credit-profile tool service (Java)
                          │
                   synthetic profiles (JSON / SQLite)

   Transcripts + labels → SQLite locally / DynamoDB in AWS
   Eval runner (CLI + GitHub Actions) → reports → local dir / S3
```

### Tech stack
- **Assistant:** Python 3.12, FastAPI, Pydantic v2, SSE streaming.
- **LLM providers:** behind one small provider interface so models can be swapped by config. Default: Anthropic Claude (e.g. `claude-sonnet-5-5` as primary, `claude-haiku-5-5` as the cheap route; `claude-haiku-4-5-20251001` appears only in the model matrix as the "old model" for the upgrade playbook). Second provider: OpenAI. Optional (M6): Amazon Bedrock.
- **Tool service:** Java 21, Spring Boot 3, REST/JSON.
- **Guardrails:** Microsoft Presidio (PII), custom rules + LLM classifiers.
- **Storage:** SQLite locally; DynamoDB + S3 in AWS.
- **Frontend:** React + TypeScript (Vite).
- **Tests/CI:** pytest, JUnit, GitHub Actions.
- **Packaging:** Docker + docker-compose for local; AWS Lambda (container image) or App Runner for deploy.

## 5. Functional requirements

### 5.1 Assistant service

**FR-1.1 Synthetic profiles.** A generator script creates N (default 50) synthetic credit profiles with: score history (12 months), accounts (cards, loans) with balances/limits, payment history incl. late payments, hard inquiries, account ages. Deterministic with a seed. Includes deliberate "story" profiles (e.g. score dropped after a new card + high utilization) used by tests.

**FR-1.2 Tools** (served by the Java service, called by the LLM via tool calling):

| Tool | Returns |
|---|---|
| `get_credit_profile(profile_id)` | Summary: score, factors, account list |
| `get_score_history(profile_id, months)` | Monthly score series |
| `get_utilization(profile_id)` | Overall + per-card utilization |
| `simulate_payoff(profile_id, account_id, amount)` | New utilization (does **not** promise a score change) |
| `explain_factor(factor_code)` | Plain-language explanation of a scoring factor (static content) |

Tool descriptions are versioned in the repo as prompt assets.

**FR-1.3 Structured output.** Besides chat, an `/insights/{profile_id}` endpoint returns 1–3 **Insight Cards** as validated Pydantic objects:
```
InsightCard { title, summary, factor_code, evidence: [ {tool, field, value} ], suggested_next_step, disclaimer_required: bool }
```
Every number in `summary` must appear in `evidence` (checked by an eval).

**FR-1.4 Streaming.** `/chat` streams tokens over SSE; tool calls are surfaced as events so the UI can show "looking up your utilization…".

**FR-1.5 Prompts as versioned assets.** System prompt, tool descriptions, and judge prompts live in `prompts/` with a version id. Every transcript and eval result records the prompt version and model id.

**FR-1.6 Transcript logging.** Every conversation stores: messages, tool calls + results, guardrail decisions, model id, prompt version, token counts, cost estimate, latency.

### 5.2 Guardrails

All guardrails run as a pipeline with a common interface: `check(text, context) -> GuardrailResult {allowed, action: pass|redact|block|rewrite, reasons[], scores{}}`. Each decision is logged.

**FR-2.1 PII redaction (input + output).** Detect and redact SSNs, account/card numbers, phone, email, DOB, addresses before text reaches the model or the logs. Presidio + custom recognizers for account-number formats.

**FR-2.2 Prompt-injection defense (input).** Two layers: heuristic rules + an LLM classifier. Tool results are also treated as untrusted (indirect injection test cases included).

**FR-2.3 Financial-advice compliance (output).** A written policy in `policy/compliance.md`, enforced by rules + an LLM classifier. Initial rules:
- Never promise or predict a specific score change ("this will raise your score 40 points").
- Never recommend a specific lender, card, or product.
- Never reference protected characteristics (race, religion, sex, national origin, marital status, age) as factors.
- Never give legal advice; point to official resources for disputes.
- Include the educational disclaimer when `disclaimer_required`.
Policy is loosely informed by public CFPB consumer guidance; the README must say it is a demo policy, not legal compliance.

**FR-2.4 Off-topic handling.** Politely decline non-credit questions.

**FR-2.5 Guardrail evaluation.** Each guardrail has its own labeled test set and reported precision/recall (see §5.3).

### 5.3 Evaluation framework

**FR-3.1 Golden set.** `evals/datasets/golden.jsonl`, ≥150 cases at v1. Each case:
```
{ id, category, profile_id, conversation: [...], expectations: {
    must_call_tools?: [...], must_not_call_tools?: [...],
    must_contain?: [...], must_not_contain?: [...],
    expected_refusal?: bool, numeric_facts?: [{field, value}],
    rubric_notes?: str }, tags: [...], source: "authored" | "promoted_from_transcript" }
```
Categories (target counts): factual/explanatory (30), tool-use correctness (30), insight-card grounding (20), refusal/off-topic (15), prompt injection direct + indirect (20), PII (15), compliance traps (20).

**FR-3.2 Scorers.** Deterministic first, LLM judge only where needed:
- Tool-call correctness (expected tools called with right args).
- Numeric grounding (every number in the answer matches a tool result).
- Schema validity (insight cards).
- String rules (must/must-not contain).
- Guardrail outcome (blocked/redacted as expected).
- **LLM judge** for: helpfulness, clarity, compliance, groundedness — rubric in `prompts/judge/`, outputs structured scores + rationale.

**FR-3.3 Runner.** `python -m evals run --suite golden --model <id> --prompt-version <v>`
- Parallel execution with a concurrency limit.
- Caches model responses by (case, model, prompt version) hash to save cost on reruns.
- Writes `reports/<run_id>/results.jsonl` + `summary.json` + `report.md` (per-category pass rates, regressions vs baseline, cost, latency p50/p95).
- `python -m evals compare <run_a> <run_b>` prints a diff: newly failing / newly passing cases.

**FR-3.4 Judge calibration (key differentiator).**
- A labeling set of ≥100 assistant responses, labeled by hand in the analyst UI (pass/fail per rubric dimension + notes).
- `python -m evals calibrate-judge` computes, per dimension: precision, recall, F1, accuracy, and **Cohen's kappa** between judge and human labels, plus a confusion matrix.
- Results are versioned so judge-prompt changes show agreement over time.
- Iterate on the judge prompt at least once and report before/after agreement.

**FR-3.5 Promote failures to tests.** From the analyst UI or CLI: `python -m evals promote <transcript_id>` converts a labeled bad transcript into a golden case with `source: promoted_from_transcript`.

**FR-3.6 Regression gate in CI.** On any PR touching `prompts/`, `src/assistant/`, guardrails, or model config: run a fast subset (smoke, ~40 cases, cheap model for judge) and fail if any category drops more than a configurable threshold vs the committed baseline. Post the summary as a PR comment. The full suite runs on demand / nightly.

### 5.4 Model comparison, cost, latency

**FR-4.1 Model comparison.** `python -m evals matrix --models a,b,c` runs the golden set on 2–3 models and outputs a table: pass rate per category, judge scores, cost per conversation, latency p50/p95. Committed to `reports/model-comparison.md`.

**FR-4.2 Prompt caching.** Use provider prompt caching for the static system prompt + tool definitions. Measure before/after cost and latency on the same suite.

**FR-4.3 Model routing.** A router classifies requests (simple explanatory vs needs tools/reasoning) and sends simple ones to the cheaper model. Report quality vs cost of: always-big, always-small, routed.

**FR-4.4 Context management.** Trim/summarize long conversations past a token budget; include eval cases with long conversations to show quality holds.

**FR-4.5 Model upgrade playbook.** `docs/model-upgrade.md`: the steps to evaluate and ship a new model (run matrix → check regressions → shadow/A-B plan). A simple A/B flag in config routes a % of traffic to a candidate model and tags transcripts with the variant.

### 5.5 Analyst UI (React + TypeScript)

**FR-5.1 Chat view.** Pick a synthetic profile, chat, see streamed answer + tool-call events + guardrail badges.
**FR-5.2 Transcript viewer.** List + filter by date, model, prompt version, guardrail flag, judge score. Detail view shows messages, tool calls, guardrail decisions, cost, latency.
**FR-5.3 Labeling workflow.** Label a response per rubric dimension (pass/fail + note). Keyboard shortcuts. Labels feed judge calibration.
**FR-5.4 Promote to test case** button.
**FR-5.5 Dashboard.** Pass rate by category over eval runs; judge–human agreement over time; guardrail block rates; cost per conversation by model.

### 5.6 Java tool service

**FR-6.1** Spring Boot 3 REST service exposing the tools in FR-1.2 over JSON, reading synthetic profiles.
**FR-6.2** Input validation, consistent error responses, JUnit tests, OpenAPI spec.
**FR-6.3** Python calls it via a typed client; a fallback in-process implementation exists for unit tests.

## 6. Success metrics (report actual values in README; these are targets)

| Metric | Target |
|---|---|
| Golden-set overall pass rate (primary model) | ≥ 85% |
| Numeric grounding failures | 0 on golden set |
| Judge vs human agreement (Cohen's kappa), main dimension | ≥ 0.6, with before/after judge-prompt iteration shown |
| PII redaction recall on PII test set | ≥ 95% |
| Prompt-injection detection recall / false-positive rate | ≥ 90% / ≤ 5% |
| Compliance violation rate on compliance traps | ≤ 5% |
| Cost reduction from caching + routing at equal quality (±2 pts) | measurable, reported honestly |
| CI smoke suite runtime | ≤ 5 min |

If a target is missed, report the real number and what was learned. That is more credible than a perfect score.

## 7. Deployment (AWS) — optional M6

AWS is not part of the core plan. Start M6 only if target job postings ask for AWS; the cheapest version is eval reports to S3 plus the nightly eval as a scheduled Lambda.

- Assistant: AWS Lambda (container image) behind API Gateway, or App Runner if streaming on Lambda is awkward. Document the choice.
- Java service: App Runner or Lambda (SnapStart).
- DynamoDB: transcripts, labels. S3: eval reports.
- Secrets in AWS Secrets Manager / SSM Parameter Store.
- Optional: run one model through **Amazon Bedrock** in the model matrix.
- Infrastructure as code: AWS SAM or CDK (pick one; keep it small).
- Budget guard: a spending alarm; the deployed demo is rate-limited and API-key protected.

Local development must work fully offline from AWS (SQLite + local files) with `docker compose up`.

## 8. Engineering quality

- Monorepo; small PRs with clear descriptions.
- pytest unit tests for guardrails, scorers, router, tool client; JUnit for the Java service.
- Lint/format: ruff + black (Python), eslint + prettier (TS), spotless (Java).
- GitHub Actions: lint + unit tests on every PR; eval smoke gate on relevant PRs; nightly full eval.
- Config via env vars + `config.yaml`; no secrets in the repo.
- Structured JSON logging with request ids.

## 9. Repo structure

```
CreditLens/
  README.md
  PRD.md
  docker-compose.yml
  config.yaml
  prompts/
    system/v1.md
    tools/v1.yaml
    judge/v1.md
  policy/compliance.md
  src/assistant/          # FastAPI app, LLM provider interface, tool loop, router, streaming
  src/guardrails/         # pii.py, injection.py, compliance.py, pipeline.py
  src/storage/            # sqlite + dynamodb adapters
  evals/
    datasets/             # golden.jsonl, pii.jsonl, injection.jsonl, compliance.jsonl, labels.jsonl
    scorers/
    runner.py  compare.py  calibrate.py  matrix.py  promote.py
  reports/                # committed baselines + comparison tables
  data/generate_profiles.py
  tool-service/           # Spring Boot (Java)
  web/                    # React + TS (Vite)
  infra/                  # SAM or CDK
  docs/architecture.md  docs/model-upgrade.md
  .github/workflows/
  tests/
```

## 10. Milestones and acceptance criteria

### M1 — Core assistant (≈ 1 weekend)
- [ ] Profile generator with seed + ≥3 story profiles
- [ ] FastAPI `/chat` (SSE) and `/insights/{id}` with tool calling (Python tool implementations first)
- [ ] Prompts as versioned files; transcripts logged to SQLite
- [ ] 50 golden cases + deterministic scorers + `evals run` producing `report.md`
**Done when:** `evals run` prints per-category pass rates and cost for one model.

### M2 — Judge + calibration + CI gate (≈ 1 weekend)  ← highest priority after M1
- [ ] LLM judge with rubric and structured output
- [ ] ≥100 hand labels (simple CLI labeler is fine before the UI exists)
- [ ] `calibrate-judge`: precision/recall/F1/kappa + confusion matrix; one judge-prompt iteration with before/after
- [ ] Golden set grown to ≥150
- [ ] GitHub Actions smoke gate with baseline + PR comment
**Done when:** a PR that degrades the system prompt is blocked by CI with a readable diff.

### M3 — Guardrails (≈ 3–4 evenings)
- [ ] PII redaction in + out, with PII test set and recall/precision
- [ ] Prompt-injection detector (direct + indirect) with test set and metrics
- [ ] Compliance policy + classifier with trap test set and metrics
- [ ] Guardrail decisions in transcripts and eval reports
**Done when:** the eval report has a guardrails section with per-guardrail precision/recall.

### M4 — Models, cost, latency (≈ 2–3 evenings)
- [ ] Provider interface supports ≥2 providers/models
- [ ] `evals matrix` comparison table committed
- [ ] Prompt caching on, with measured before/after
- [ ] Router with always-big vs always-small vs routed comparison
- [ ] `docs/model-upgrade.md` + A/B config flag
**Done when:** `reports/model-comparison.md` shows quality × cost × latency for all variants.

### M5 — Analyst UI (+ Java service if target roles list Java) (≈ 1–2 weekends)
- [ ] React chat view, transcript viewer, labeling, promote-to-test (button calls the `evals promote` code path)
- [ ] Dashboard as a static page rendered from `reports/*.json`
- [ ] Spring Boot tool service passes the shared `contracts/tools/` fixtures and replaces the Python tools (Python fallback kept for tests). Only if target roles list Java; otherwise moves to M6.
- [ ] README: architecture diagram, results tables, demo GIF, how to reproduce
**Done when:** a fresh clone can run everything locally with `docker compose up`.

### M6 — Optional: AWS (and Java, if not done in M5)
- [ ] AWS SAM deploy; Lambda vs App Runner streaming choice documented in `docs/architecture.md`; spending alarm; API key + rate limit
- [ ] Optional Bedrock column in the model matrix
**Done when:** the deployed demo works.

**Ship order matters:** M1 + M2 alone are enough to talk about in interviews. Don't let M5 block applying.

## 11. Risks

| Risk | Mitigation |
|---|---|
| API cost from repeated eval runs | Response cache keyed by (case, model, prompt version); cheap model for smoke judge; small smoke subset |
| Hand-labeling takes long | Label in batches of 25; keyboard-driven labeler; 100 is the floor, not 500 |
| Scope creep in the UI | UI is M5; CLI tools first |
| SSE streaming on Lambda | Use App Runner or Lambda response streaming; document the decision |
| Judge overfits to your labels | Keep a held-out label split (e.g. 70/30) and report kappa on the held-out part |

## 12. Resume bullets this should unlock (fill in real numbers only after measured)

- Built an LLM **evaluation framework** (150-case golden set, deterministic scorers + LLM-as-judge) with **CI regression gates** on every prompt/model change
- Calibrated an **LLM-as-judge** against 100+ human labels, raising agreement from κ=__ to κ=__ via rubric iteration
- Added **guardrails** (PII redaction, prompt-injection detection, financial-advice compliance) with measured precision/recall
- Compared __ models on quality, cost, and latency; **prompt caching** and **model routing** cut cost per conversation by __% at equal quality
- Built analyst tooling (React/TypeScript transcript viewer, labeling workflow, dashboards) and a **Spring Boot** tool microservice; deployed on **AWS** (Lambda/App Runner, DynamoDB, S3)

## 13. Instructions for the implementing Claude Code session

- Build milestone by milestone; don't start M(n+1) until M(n)'s "done when" passes.
- Prefer deterministic scorers; use the LLM judge only where a rule can't decide.
- Keep every metric reproducible from a command; never hard-code results into docs.
- Never use real personal or credit data; generate everything.
- Keep the code something Abhinav can explain line by line in an interview: favor clarity over cleverness, and avoid heavy eval frameworks that hide the logic (write the runner and metrics directly; libraries like scikit-learn for metrics are fine).

## 14. Design decisions (grilling session, 2026-10-31)

These take precedence over earlier sections where they conflict.

### Scope
- Local-only core: SQLite, local `reports/`, `docker compose up`, GitHub Actions. AWS and Bedrock are optional M6.
- Java service stays in M5 only if target roles list Java; otherwise M6. The tool contracts (below) stay either way.
- UI: chat, transcript viewer, labeling; dashboard is static from `reports/*.json`.

### Data
- A documented toy scoring formula computes each month's score from profile events. Story profiles store their true cause (e.g. `score_drop_cause: [RECENT_INQUIRIES, UTILIZATION]`).
- Factor codes are one closed enum (`UTILIZATION`, `PAYMENT_HISTORY`, `RECENT_INQUIRIES`, `ACCOUNT_AGE`, `CREDIT_MIX`, `DEROGATORY`), shared by the formula, `explain_factor`, insight cards, and story causes. An insight card's `factor_code` must be one of that profile's actual top factors.
- Generated profiles are committed (`data/profiles/v1.json`); golden cases reference that file. A test asserts `generate_profiles.py --seed 42` reproduces it byte for byte. Generator changes produce `v2`.
- Profiles have free-text fields (`creditor_name`, `notes`). A subset with ids `inj_*` carries indirect-injection payloads.
- Tools return masked account numbers only (`****4821`). The output PII redactor allows that form and blocks anything longer.

### Assistant
- Hand-written tool loop with a max-iterations cap, behind a `Provider` protocol (Anthropic first; OpenAI added in M4).
- One function, `run_turn(conversation, profile_id, config) -> TurnResult`, serves both FastAPI `/chat` and the eval runner.
- Streaming: tool events stream live; answer text is buffered per sentence and passed through an `OutputFilter` chain (empty in M1) before sending. The full-answer compliance classifier can emit a `retract` event. Buffering latency is measured.
- Insight cards: forced tool call / JSON schema, Pydantic validation, one retry; retry count logged and reported.
- Tool inputs/outputs are Pydantic models exported to JSON Schema in `contracts/tools/`, with shared input→output fixtures the Python fallback (and later Java) must pass.

### Evals
- Golden cases: ~15 hand-written seeds; the rest LLM-drafted and human-reviewed. Each case records `authored_by: human | llm_drafted_human_reviewed`.
- Multi-turn cases: earlier turns (including tool calls/results) are fixed in the case; only the final assistant turn is generated and scored. Long-conversation cases (FR-4.4) are a separate suite.
- A case passes only if every check that applies to its category passes. Results store per-check pass/fail.
- Numeric grounding: extract every number; accept it if it matches a tool result in the conversation within a set rounding tolerance, is a difference of two values from the same tool series, is utilization recomputed as balance ÷ limit, or is in the versioned allowlist `policy/constants.yaml`. Everything else fails.
- Insight-card evidence entries must match tool calls actually made in that request (from the transcript).
- Cache key = content hash of rendered system prompt + tool definitions + model params (plus the version label). A CI lint fails if a committed `prompts/**/vN` file changes.
- Temperature 0. Gate fails if overall pass rate drops more than X points or any category loses ≥2 cases that passed in the baseline. The PR comment lists newly failing case ids.
- Smoke suite: fixed cases tagged `smoke` in `golden.jsonl`, ≥5 per category, biased to the hardest cases; changed only in a reviewed PR.
- Baseline changes only via `python -m evals baseline <run_id>` in a PR that runs the gate against the old baseline. CI persists the response cache with `actions/cache`.
- Runner has `--max-cost-usd` (default $5 locally, $1 in CI): estimates cost up front from uncached cases and aborts mid-run if actual spend exceeds it.

### Judge
- One pinned judge model (`claude-sonnet-5-5`) for smoke and full runs; this exact judge + rubric is what gets calibrated.
- Output: pass/fail per dimension, rationale written before the verdict, structured output enforced.
- Main dimension for the kappa ≥ 0.6 target: **compliance**. Other dimensions reported without targets.
- Labeling pool spans ≥2 models (incl. Haiku), ≥2 prompt versions (incl. `prompts/system/v1-degraded.md`), and the hard categories, aiming for 30–50% failures per main dimension. Sampling is recorded in `labels.jsonl`.
- Labels are made blind to the judge, in shuffled order. A held-out 30 is frozen before the first judge-prompt iteration. Every kappa is reported with a bootstrap 95% CI. If possible, a second person labels 30 for a human–human ceiling.
- Self-preference bias: compare judge kappa on Sonnet-written vs Haiku-written responses.
- `v1-degraded.md` (no disclaimer instruction, permits score speculation) supplies labeling failures, is the M2 demo PR, and is a test fixture asserting the gate blocks it.

### Guardrails
- PII placeholders are typed and numbered per conversation (`<SSN_1>`, `<EMAIL_1>`); originals are never stored. An eval asserts they never reach SQLite.
- Injection and compliance test sets: benign cases ≥ attack cases, at least half of the benign ones hard negatives. Each guardrail dataset has a dev/test split; tune on dev, report test.
- Report both per-guardrail precision/recall and end-to-end attack success rate through `run_turn` with guardrails on vs off.
- Compliance violation: regenerate once with the broken rule named, then return a fixed safe fallback. Regeneration and fallback rates are reported.
- Off-topic: system-prompt instruction only, unless the refusal/off-topic category misses its target.

### Models, cost, latency
- Cost = API usage tokens (input, output, cache write, cache read) × `config/pricing.yaml` (with an `as_of` date); reports record the pricing version.
- Latency (TTFT + total) comes from a separate sequential run of a fixed subset; parallel runs measure only quality and cost.
- Prompt caching: verify real cached token counts first; if the prompt is below the caching minimum, report that rather than padding.
- Router: deterministic rule first, scored by misroute rate against golden `must_call_tools` labels; cheap LLM classifier only if needed.
- A/B: assignment by hash of conversation id; `variant` recorded on every transcript.

### Storage
- `Storage` interface: `put`, `get(id)`, `list(date_range, limit)`; callers filter. SQLite only in the core plan.

### API constraints found during the build (2026-10-31)
These replace the matching decisions above. Source: Claude API reference, checked while writing config.
- **No temperature 0.** Since API version 2026-10-21, `temperature`/`top_p`/`top_k` return a 400 on every model. Eval reproducibility comes from the content-hash response cache: an unchanged case is never re-sampled. Run-to-run noise on changed inputs is handled by the gate rule (a regression is ≥2 previously passing cases lost in a category), plus the overall-drop threshold.
- **No forced tool calls on Sonnet 5.5** (`tool_choice` `any`/`tool` return a 400). Insight cards use structured outputs (`output_config.format`) validated by Pydantic, with one retry. The tool loop runs first to gather data, then one structured-output call writes the cards.
- **Effort, not thinking budgets.** Sonnet 5.5 and Haiku 5.5 run adaptive thinking; depth is set with `output_config.effort` (chat route `low`, judge `medium`, both in `config.yaml`). Haiku 4.5 has no `effort` parameter, so the provider skips it via `supports_effort: false`. Thinking blocks returned during a tool loop are passed back unchanged.
- **Prompt caching minimum** is 512 tokens on Sonnet 5.5 / Haiku 5.5 and 4096 on Haiku 4.5, so caching may not apply to Haiku 4.5 at all. M4.4 reports what actually happened.
- **Insight-card data is gathered by code, not the model.** `/insights` calls `get_credit_profile`, `get_utilization` and `get_score_history` directly, then makes one structured-output request. The evidence check therefore compares against a known, fixed set of tool outputs. The prompt is versioned in `prompts/insights/vN.md`.
- **Tool calls are scoped to the conversation's profile.** The tool executor rejects any `profile_id` other than the conversation's own. This is a deterministic layer under the injection guardrails.
- **Numeric grounding scope (refined after the first live runs).** If the assistant had the person's data this turn, every number in every sentence must trace to it. Without data (general education), only sentences making claims about the person ("your", "you have") are checked; the accuracy of general facts is the judge's groundedness dimension. List numbering and explicit "for example" sentences without "your" are never checked. Also grounded: last four digits of known masked accounts, totals per account type, account ages, and spelled-out counts for expected facts. Constants are unit-aware (`policy/constants.yaml` v3).
- **Judge modes.** `evals run --judge off|report|gate`. Use `report` until the judge's test-split kappa on compliance meets the ≥0.6 target, then `gate`.
- **PII guardrail result (M3.3, measured).** `python -m evals guardrail pii --split test`: **recall 91.4% (target ≥95%, missed)**, precision 100%, 0% false positives on 30 hard negatives. Misses are messy formats (lowercase or single first names, "12B" street numbers, ordinal dates, digit-spaced SSNs). The guardrail was tuned on dev only; fixing these needs new dev examples and a fresh test set, not edits based on the test set.
- **Injection guardrail result (M3.4, measured).** `python -m evals guardrail injection --split test`: rules alone 43.8% recall; **rules + Haiku 5.5 classifier: 100% recall, 0% false positives** (52 test items, hard negatives included). Caveat: a small, self-written set; the end-to-end attack runs (M3.8) are the stronger evidence. Tuned on dev only (two ambiguous phrases moved from "block" to "suspicion"). Order is PII → injection, so the classifier never sees raw PII. Unit tests run with guardrails off unless a test passes its own (`tests/conftest.py`), so they never call a real API.
- **Compliance guardrail result (M3.6, measured).** `python -m evals guardrail compliance --split test`: rules alone 36.8% recall; **rules + Haiku classifier: 100% recall, 0% false positives** (35 test replies, hard negatives included). Same caveat: small and self-written. Sentence rules drop a clearly violating sentence before it streams. The classifier checks the whole reply; on a violation run_turn retracts, regenerates once naming the broken rule, then falls back to a fixed safe reply (M3.7). Rates are in `TurnResult.extra["compliance"]`.
- **Guardrails end to end (M3.8, measured).** The 55 attack-category cases (injection, pii, compliance) on Sonnet 5.5, guardrails off vs on (`python -m evals guardrail-e2e ... --label ...`, runs in `reports/history/e2e-*`). Attack success = a harm check failed. **v1 prompt: 0/55 → 0/55** (the prompt alone already resists; judge compliance-fails 2 → 0). **Safety-stripped prompt (v1-degraded): 4/55 → 0/55** (echoed email and address, a "guarantee", and an injected "120 points" are all prevented; judge compliance-fails 6 → 2). The guardrails are defense in depth: they matter most when the prompt or model fails. Small n; one run per arm.
- **OpenAI deferred (owner, 2026-10-31).** M4 compares Anthropic models only (Sonnet 5.5, Haiku 5.5, Haiku 4.5). The provider interface stays provider-neutral, so an OpenAI provider can be added later without touching the loop; M4.1 is deferred, not dropped.
- **M4 results (measured; `reports/model-comparison.md`, `reports/cost-variants.md`).** 150-case golden suite, guardrails on, judge in report mode: **Sonnet 5.5 90.7% at $0.0106/case; Haiku 5.5 94.7% at $0.0006/case; Haiku 4.5 78.7% at $0.0042/case.** Haiku 5.5's lead comes almost entirely from insight cards (70% vs 30%: Sonnet's summaries cite numbers missing from their evidence); other categories are within a case. Latency (smoke, sequential, fresh): Sonnet p50 5.9s, Haiku 5.5 4.0s, Haiku 4.5 4.2s (TTFT 0.7s). Router: 0 misroutes, 24/150 cases sent small, −10% cost (88.7%). Prompt caching: −8% cost, TTFT 2.4s → 1.6s, same quality within noise; **enabled**. The profile id in the system prompt limits cross-conversation cache reuse (next: prompt v2 moving it out). Context trimming: 5/5 both ways, −46% input tokens. All single runs on unreviewed (llm_drafted) cases. **Switching the default model to Haiku 5.5 is the owner's call** after case review and a second run.
