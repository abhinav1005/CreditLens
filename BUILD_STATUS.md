# CreditLens Build Status

The single tracker for the build. Claude Code reads this at the start of every session and updates it after every task.
Specs: `PRD.md` (§14 takes precedence). History and notes: `BUILD_LOG.md`.

**Legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (reason in log) · 👤 = needs the owner (Abhinav)

**Current milestone:** M2 done-when PASSED 2026-10-31 (PR #1 blocked by the gate). Open in M2: owner labels (M2.5), then calibration (M2.7 run) + judge iteration (M2.8). Next build milestone: M3
**Next task:** M3.8 (guardrails section + on/off end-to-end)

Each task is one small, reviewable commit. "Check" is how we know it's done.

---

## M0 — Setup

| ID | Status | Task | Check |
|---|---|---|---|
| M0.1 👤 | [x] | Install `uv` (`curl -LsSf https://astral.sh/uv/install.sh \| sh`) | `uv --version` works |
| M0.2 👤 | [x] | Create Anthropic API key, put it in `.env` as `ANTHROPIC_API_KEY`, set a monthly spend limit in the console | Key in `.env` (never committed) |
| M0.3 | [x] | `git init`, `.gitignore`, `.env.example`, `pyproject.toml` (Python 3.12 via uv; fastapi, pydantic, anthropic, pyyaml, pytest, ruff, black), folder skeleton per PRD §9 | `uv run pytest` and `uv run ruff check .` pass |
| M0.4 👤 | [x] | Create a GitHub repo (private ok). Claude can run `gh repo create` once you approve | `git push` works. Needed by M2.14. |

## M1 — Core assistant

**Done when:** `python -m evals run` prints per-category pass rates and cost for one model.

### Data
| ID | Status | Task | Check |
|---|---|---|---|
| M1.1 | [x] | `FactorCode` enum + Pydantic profile schema (accounts with masked numbers, payments, inquiries, `creditor_name`, `notes`) | Schema unit tests |
| M1.2 | [x] | Toy scoring formula + `docs/scoring.md` | Tests: higher utilization / more lates / more inquiries → lower score; range 300–850 |
| M1.3 | [x] | `data/generate_profiles.py`: seeded, 50 profiles, monthly events → 12-month score history via the formula | Same seed → identical output |
| M1.4 | [x] | ≥3 story profiles with stored true causes; `inj_*` profiles with payloads in free-text fields | Story causes match what the formula produces |
| M1.5 | [x] | Commit `data/profiles/v1.json` + byte-for-byte reproducibility test | Test passes |

### Tools
| ID | Status | Task | Check |
|---|---|---|---|
| M1.6 | [x] | Pydantic input/output contracts for the 5 tools; export JSON Schema to `contracts/tools/` | Export script is idempotent |
| M1.7 | [x] | Python tool implementations + `explain_factor` static content + shared fixtures | Contract fixture tests pass |

### Assistant core
| ID | Status | Task | Check |
|---|---|---|---|
| M1.8 | [x] | `prompts/system/v1.md`, `prompts/tools/v1.yaml`, prompt loader with content hash, immutability lint script | Lint fails when a committed `vN` file changes |
| M1.9 | [x] | `config.yaml`, `config/pricing.yaml` (with `as_of`), config loader | Loader tests |
| M1.10 | [x] | `Provider` protocol + `FakeProvider` (tests) + `AnthropicProvider` | Unit tests use fake; one live smoke call (needs M0.2) |
| M1.11 | [x] | Tool loop + `run_turn()` → `TurnResult` (events, tool calls, tokens, cost, latency), max-iterations cap, empty `OutputFilter` chain | Tests with `FakeProvider` |
| M1.12 | [x] | `Storage` interface (`put/get/list`) + SQLite transcripts; `run_turn` logs prompt version + model id | Round-trip test |

### API
| ID | Status | Task | Check |
|---|---|---|---|
| M1.13 | [x] | FastAPI `/chat` over SSE: tool events live, text buffered by sentence through the filter chain | Test client receives ordered events |
| M1.14 | [x] | `/insights/{profile_id}`: forced structured output, Pydantic validation, 1 retry, retry count logged | Tests with fake provider; 1 live call |

### Evals
| ID | Status | Task | Check |
|---|---|---|---|
| M1.15 | [x] | Golden case schema + loader + validator (`authored_by`, `tags`, categories) | Invalid cases are rejected with a clear error |
| M1.16 👤 | [~] | **Owner reviews** the 50 drafted cases in `evals/datasets/golden.jsonl` (Claude drafted them all, per owner's instruction; see `docs/reviewing-cases.md`). Flip each reviewed case to `llm_drafted_human_reviewed`, editing anything wrong | `evals validate` shows no unreviewed warning |
| M1.17 | [x] | `scripts/draft_golden_v1.py` drafts 50 cases with expected numbers pulled from real tool outputs (no LLM API needed: Claude Code wrote them) | 50 valid cases |
| M1.18 | [x] | Deterministic scorers: tool-call correctness, must/must-not contain, expected refusal, schema validity | Unit tests per scorer |
| M1.19 | [x] | Numeric grounding scorer + `policy/constants.yaml` (tolerance, series differences, balance ÷ limit) | Unit tests incl. derived-number cases |
| M1.20 | [x] | Insight-card evidence scorer (evidence must match actual tool calls; `factor_code` in top factors) | Unit tests |
| M1.21 | [x] | `python -m evals run`: parallel, content-hash cache, `--max-cost-usd`, writes `results.jsonl` / `summary.json` / `report.md` | Second run hits cache at $0 |
| M1.22 | [x] | **M1 exit:** live run on `claude-sonnet-5-5`, commit report, update CLAUDE.md commands | Done-when passes |

## M2 — Judge, calibration, CI gate

**Done when:** a PR that degrades the system prompt is blocked by CI with a readable diff.

| ID | Status | Task | Check |
|---|---|---|---|
| M2.1 | [x] | `prompts/judge/v1.md` + judge module (pinned Sonnet; pass/fail per dimension, rationale first, structured output) | Tests with fake provider |
| M2.2 | [x] | `prompts/system/v1-degraded.md` | Exists, immutable |
| M2.3 | [x] | Labeling-pool builder (≥2 models × ≥2 prompt versions × hard categories; sampling recorded) | Pool of ≥130 responses |
| M2.4 | [x] | CLI labeler: blind to judge, shuffled, keyboard-driven, writes `labels.jsonl` | Manual try-out |
| M2.5 👤 | [ ] | Owner labels ≥100 responses (4 batches of 25) | ≥100 labels |
| M2.6 | [x] | Freeze held-out 30 (committed split file) | Split file committed before M2.8 |
| M2.7 | [x] | `calibrate-judge`: P/R/F1/accuracy/kappa + bootstrap 95% CI + confusion matrix + Sonnet-vs-Haiku self-preference | Report generated |
| M2.8 | [ ] | Judge-prompt iteration → `judge/v2.md`, tuned on dev only; before/after on held-out | Versioned calibration reports |
| M2.9 | [x] | Judge integrated into the runner (per-category check map) | Report shows judge columns |
| M2.10 | [x] | Grow golden set to ≥150 (drafts + 👤 review) | ≥150 valid cases, target category counts |
| M2.11 | [x] | `evals compare` + `evals promote` | Tests |
| M2.12 | [x] | `smoke` tags (≥5/category) + `evals baseline` + `reports/baseline/` | Baseline committed |
| M2.13 | [x] | Gate logic (overall drop > X, or ≥2 lost cases in a category) + test that `v1-degraded` is blocked | Test passes |
| M2.14 | [x] | GitHub Actions: lint + tests on every PR; smoke gate on relevant paths, `actions/cache`, PR comment. 👤 adds `ANTHROPIC_API_KEY` repo secret | Workflow green on a no-op PR. **Known issue:** a cold-cache smoke run estimates ~$1.44 (40 × $0.036) vs the $1 CI limit, so restore the cache first and/or set the CI limit from a measured smoke-run cost |
| M2.15 | [x] | **M2 exit:** demo PR switching to the degraded prompt is blocked | Done-when passes |

## M3 — Guardrails

**Done when:** the eval report has a guardrails section with per-guardrail precision/recall.

| ID | Status | Task | Check |
|---|---|---|---|
| M3.1 | [x] | `GuardrailResult` interface + pipeline + decisions logged in transcripts | Tests |
| M3.2 | [x] | PII: Presidio + custom recognizers, numbered placeholders, masked-account allowlist | Unit tests |
| M3.3 | [x] | `pii.jsonl` (dev/test) + metrics + "originals never reach SQLite" eval | Recall reported |
| M3.4 | [x] | Injection: heuristics + LLM classifier; `injection.jsonl` with hard negatives, dev/test | P/R/FPR reported |
| M3.5 | [x] | Indirect injection via tool results (`inj_*` profiles) | Cases in suite |
| M3.6 | [x] | `policy/compliance.md` + rules + classifier; `compliance.jsonl` with compliant hard negatives | P/R reported |
| M3.7 | [x] | Compliance action: regenerate once → fallback; rates reported | Tests |
| M3.8 | [ ] | Report guardrails section: per-guardrail P/R + end-to-end attack success on vs off | **M3 exit** |

## M4 — Models, cost, latency

**Done when:** `reports/model-comparison.md` shows quality × cost × latency for all variants.

| ID | Status | Task | Check |
|---|---|---|---|
| M4.1 | [ ] | OpenAI provider. 👤 provides `OPENAI_API_KEY` | Live smoke call |
| M4.2 | [ ] | Sequential latency run (TTFT + total) | p50/p95 in report |
| M4.3 | [ ] | `evals matrix` (Sonnet 5.5, Haiku 5.5, Haiku 4.5, OpenAI) → `reports/model-comparison.md` | Table generated |
| M4.4 | [ ] | Prompt caching: verify cached tokens, measure before/after | Honest result in report |
| M4.5 | [ ] | Router rule + misroute rate + always-big / always-small / routed comparison | In comparison report |
| M4.6 | [ ] | Context trimming + long-conversation suite | Quality holds (reported) |
| M4.7 | [ ] | A/B flag (hash of conversation id, `variant` tagged) + `docs/model-upgrade.md` | **M4 exit** |

## M5 — Analyst UI (+ Java if needed)

**Done when:** a fresh clone runs everything with `docker compose up`.

| ID | Status | Task | Check |
|---|---|---|---|
| M5.0 👤 | [ ] | Decide: do target roles list Java? (yes → M5.8 here; no → M6) | Decision logged |
| M5.1 👤 | [ ] | Install Docker Desktop | `docker --version` |
| M5.2 | [ ] | Vite + React + TS scaffold, eslint/prettier, chat view (SSE, tool events, guardrail badges) | Manual + lint |
| M5.3 | [ ] | Transcript viewer (list + filter + detail) | Manual |
| M5.4 | [ ] | Labeling view (keyboard shortcuts) feeding `labels.jsonl` | Manual |
| M5.5 | [ ] | Promote-to-test button → `evals promote` code path | Test |
| M5.6 | [ ] | Static dashboard from `reports/*.json` | Renders |
| M5.7 | [ ] | `docker-compose.yml` for the full local stack | Fresh clone works |
| M5.8 | [ ] | (Conditional) Spring Boot tool service passing `contracts/tools/` fixtures, JUnit, spotless, OpenAPI | Fixtures pass |
| M5.9 | [ ] | README: architecture diagram, results tables generated by a script, demo GIF (👤 records), demo-policy disclaimer | **M5 exit** |

## M6 — Optional: AWS (and Java if not done in M5)

Start only if target roles ask for it. Tasks get broken down when it starts.
