# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

M1 and M2 are done (M2 done-when: PR #1 blocked by the eval gate). Judge calibration waits on owner labels. M3 is next. Read `PRD.md` before starting any milestone. **PRD §14 (design decisions, including "API constraints found during the build") takes precedence over earlier PRD sections.** Keep this file in sync with the code as milestones land.

## Commands (working now)

Python 3.12 via uv (`~/.local/bin/uv`). Run everything with `uv run`.

```bash
uv sync                                            # install deps
uv run pytest -q                                   # unit tests (live API tests skipped)
uv run pytest -m live                              # live API smoke tests (needs ANTHROPIC_API_KEY in .env)
uv run ruff check . && uv run black --check .      # lint / format
uv run python data/generate_profiles.py            # regenerate data/profiles/v1.json (must be byte-identical)
uv run python scripts/export_contracts.py --check  # tool JSON Schemas in sync with Pydantic
uv run python scripts/make_fixtures.py --check     # shared tool fixtures in sync
uv run python scripts/check_prompt_immutability.py # committed prompt files unchanged (--lock adds NEW files)
uv run python -m evals validate                    # validate golden.jsonl, print counts
uv run python -m evals run --suite golden --model claude-sonnet-5-5 --prompt-version v1
uv run uvicorn assistant.api:app --reload          # /chat (SSE), /insights/{id}, /health
```

## Code map

- `src/credit/`: domain. `factors.py` (FactorCode enum), `profile.py` (schema), `scoring.py` (toy formula, `docs/scoring.md`), `generate.py` + `stories.py` (seeded data), `dataset.py` (loads committed v1.json), `tools/` (contracts, impl, static factor content).
- `src/assistant/`: `config.py` (config + pricing + `request_cost`), `prompts.py` (versioned bundle + content hash), `providers/` (neutral types, Fake, Anthropic), `loop.py` (`run_turn`, the one code path for API and evals), `output_filters.py` (sentence buffer + filter chain), `insights.py`, `api.py`.
- `src/storage/`: `Transcript` + `Storage` protocol, `SQLiteStorage`.
- `evals/`: `cases.py` (schema/loader), `runner.py`, `cache.py`, `report.py`, `scorers/` (deterministic, grounding, insights).
- Gotcha: black reformats code, so string-replace edits in Python heredocs can silently miss. Use the Edit tool or assert that the replacement happened.

## Build workflow (every session)

Claude Code builds this project across many sessions. The owner reviews, does the 👤 tasks, and approves.

1. **Start:** read `BUILD_STATUS.md` (what's next) and the top entry of `BUILD_LOG.md` (context and blockers). Tell the owner which task you're picking up.
2. **Pick** the "Next task". If it's a 👤 task or blocked, say what the owner needs to do and take the next unblocked non-👤 task *in the same milestone*. Never start a later milestone early.
3. **One task = one commit.** Do the task, make its "Check" pass (tests, lint), commit, then mark it `[x]` in `BUILD_STATUS.md` and update "Next task".
4. **End of session** (or when the owner stops): append a `BUILD_LOG.md` entry with what was done, decisions, blockers, and the exact next step. Mark any half-done task `[~]` and describe its state in the log.
5. A durable design decision made during the build goes into PRD §14, not only the log.
6. Tasks too big for one commit get split into sub-ids (e.g. M1.11a, M1.11b) in `BUILD_STATUS.md` before starting.

CreditLens is a portfolio project. It is a credit-education chat assistant built over **synthetic** credit profiles, but the assistant is only the test subject. The real product is the quality system around it: evals, an LLM judge calibrated against human labels, guardrails with measured precision/recall, and model/cost/latency comparison.

## Non-negotiable rules

- **No real personal or credit data, ever.** Generate all profiles with `data/generate_profiles.py` (seeded). The PII test sets use fake values in realistic formats.
- **Every metric must be reproducible from a command in this repo.** Never hand-type a number into the README, docs, or reports. If a target is missed, report the real number.
- **Build milestone by milestone** (PRD §10: M1 core assistant → M2 judge + calibration + CI gate → M3 guardrails → M4 models/cost/latency → M5 UI (+ Java if target roles need it) → optional M6 AWS). Don't start M(n+1) until M(n)'s "Done when" passes. M1 and M2 matter most; don't let M5 block anything.
- **Clarity over cleverness.** The owner must be able to explain every line in an interview. Write the eval runner and metrics directly instead of using heavy eval frameworks. scikit-learn for metrics is fine.
- **Prefer deterministic scorers.** Use the LLM judge only where a rule can't decide.
- Compliance policy (`policy/compliance.md`) is a demo policy, not legal compliance, and the README must say so.

## Planned architecture (PRD §4, §9, §14)

Request flow: React UI → (SSE) → FastAPI assistant → input guardrails → LLM + tool loop (behind a model router) → output guardrails → streamed response. Tools are served by a Spring Boot service over REST. An in-process Python implementation of the same tools exists first (M1) and is kept as the fallback for unit tests after the Java service takes over (M5, only if target roles list Java; otherwise optional M6). Python and Java must both pass the shared fixtures in `contracts/tools/`.

Cross-cutting design points:

- **Provider interface:** every LLM call goes through one small provider abstraction so models can be swapped by config (`config.yaml` + env vars). Primary model is `claude-sonnet-5-5`; the cheap route is `claude-haiku-5-5`. `claude-haiku-4-5-20251001` appears only in the model matrix as the "old model". The LLM judge is pinned to `claude-sonnet-5-5`. Second provider (M4) is OpenAI.
- **Versioned prompts:** system prompt, tool descriptions, and judge rubric live in `prompts/{system,tools,judge}/vN.*`. Every transcript and eval result records **prompt version + model id**, so a change to a prompt means a new version file, not an in-place edit.
- **Guardrail interface:** all guardrails (PII via Presidio + custom recognizers, prompt injection via heuristics + LLM classifier, compliance via rules + LLM classifier, off-topic) implement `check(text, context) -> GuardrailResult{allowed, action: pass|redact|block|rewrite, reasons[], scores{}}` and run as a pipeline in `src/guardrails/pipeline.py`. PII is redacted *before* text reaches the model or the logs. Tool results count as untrusted input (indirect injection).
- **Transcripts** log messages, tool calls/results, guardrail decisions, model id, prompt version, tokens, cost, and latency. Storage is SQLite behind a minimal `put/get/list` interface in `src/storage/`. AWS (DynamoDB/S3) is optional M6; the core plan is local-only.
- **Insight cards** (`/insights/{profile_id}`) are Pydantic models. Every number in `summary` must appear in `evidence`, and an eval checks this.
- `simulate_payoff` returns new utilization only. Neither it nor the assistant may promise a score change.

## Planned commands (PRD §5.3, §5.4, §8)

```bash
python -m evals run --suite golden --model <id> --prompt-version <v>   # writes reports/<run_id>/{results.jsonl,summary.json,report.md}
python -m evals compare <run_a> <run_b>       # newly failing / newly passing cases
python -m evals calibrate-judge               # precision/recall/F1/kappa vs human labels
python -m evals matrix --models a,b,c         # quality × cost × latency → reports/model-comparison.md
python -m evals promote <transcript_id>       # labeled transcript → golden case
docker compose up                             # full local stack
```

Model responses in evals are cached by a **content hash** of (case, model params, rendered prompt + tool definitions), so reruns with unchanged inputs don't hit the API, and editing a prompt always invalidates the cache. Committed `prompts/**/vN` files are immutable. Every run has a `--max-cost-usd` limit.

```bash
python -m evals baseline <run_id>             # the only way to change reports/baseline/
```

Tooling: pytest + ruff + black (Python), JUnit + spotless (Java, `tool-service/`), eslint + prettier (TS, `web/`).

CI (GitHub Actions): lint and unit tests run on every PR. A PR that touches `prompts/`, `src/assistant/`, guardrails, or model config also runs the eval **smoke gate** (~40 fixed `smoke`-tagged cases, pinned Sonnet judge, ≤5 min). Evals run at temperature 0. The gate fails if the overall pass rate drops more than a threshold, or if any category loses ≥2 cases that passed in the committed baseline; it posts the newly failing case ids as a PR comment. The full suite runs nightly or on demand.
