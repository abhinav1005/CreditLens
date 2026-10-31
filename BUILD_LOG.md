# CreditLens Build Log

Append-only, newest entry at the top. One entry per session. Record what was done, decisions made during the build, blockers, and the exact next step.

Entry format:

```
## YYYY-MM-DD — Session N
**Done:** task ids + one line each (commit hash if any)
**Decisions:** anything decided that isn't in PRD §14 (and add it to §14 if it's durable)
**Blockers:** what's waiting on whom
**Next:** the exact next task id and its first concrete step
```

---

## 2026-10-31 — Session 2 (build)
**Done:**
- M0.1: installed uv 0.13.6 + Python 3.12.16 (owner said to do everything).
- M0.3: repo skeleton, `pyproject.toml`, ruff/black/pytest config. Run things with `uv run ...` (uv is at `~/.local/bin`).
- M1.1: `src/credit/factors.py` (FactorCode), `src/credit/profile.py` (schema).
- M1.2: `src/credit/scoring.py` + `docs/scoring.md` (score = 850 − six penalties).
- M1.3: `src/credit/generate.py` (seeded, 50 `p_` profiles, scores computed by the formula; final scores range 609–840) + `data/generate_profiles.py` CLI.
- M1.4: `src/credit/stories.py`. 4 story profiles (new card + high utilization, 60-day late, collection, paydown rise) with `change_cause` computed from the formula; 3 `inj_*` profiles (payloads in creditor_name, notes, inquiry creditor). `Story` schema now has `direction`/`change_month`/`change_cause`. Dataset is 57 profiles.
- M1.5: committed `data/profiles/v1.json` (57 profiles), `src/credit/dataset.py` loader, and the byte-for-byte reproducibility test.
- M1.6: `src/credit/tools/contracts.py` (inputs, outputs, `ToolError`, `TOOL_CONTRACTS` registry), exported to `contracts/tools/*.json` by `scripts/export_contracts.py` (`--check` mode for CI). `simulate_payoff` output carries a fixed no-score-promise note.
- M1.7: `src/credit/tools/impl.py` (5 tools + `call_tool(name, args)`, which never raises and returns `{"error": ...}` on failure), `factor_content.py` (static education text), 21 shared fixtures in `contracts/tools/fixtures/v1.json` (`scripts/make_fixtures.py --check`), hand-checked numbers in `tests/test_tools.py`.
- M1.8: `prompts/system/v1.md` (rules + fixed disclaimer line `_Educational information only, not financial advice._`, `{{profile_id}}` placeholder), `prompts/tools/v1.yaml` (descriptions only; schemas come from the contracts), `src/assistant/prompts.py` (`load_bundle()`, `content_hash`), `scripts/check_prompt_immutability.py` with `prompts/prompts.lock.json`. **v1 files are now locked: any prompt change means v2.**
- M1.9: `config.yaml` (models, effort per route, eval limits), `config/pricing.yaml` (as_of 2026-10-06; Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50, Haiku 4.5 $1/$5; cache write 1.25×, read 0.1×), `src/assistant/config.py` (`load_config`, `load_pricing`, `Usage`, `request_cost`).
- M1.10: `src/assistant/providers/`: `base.py` (neutral `ProviderRequest`/`ProviderResponse`/`ToolCall`, `Provider` protocol; thinking blocks replayed via `provider_blocks`), `fake.py` (scripted `FakeProvider`), `anthropic_provider.py` (streams via SDK 2.3.0, effort per model, structured output via `output_config.format`, optional refusal fallback), `get_provider(model)`. Live smoke test written but **not yet run** (needs key).
- M1.11: `src/assistant/loop.py` (`run_turn()` → `TurnResult`; stops on complete / refusal / max_tokens / max_iterations(6); cost priced per request) + `src/assistant/output_filters.py` (`SentenceBuffer` keeps decimals like 40.8% together; `OutputFilter` protocol with per-sentence pass/rewrite/block and final retract). Fixed a bug where requests shared the mutable message list.
- M1.12: `src/storage/transcripts.py` (`Transcript` model with prompt version/hash, model, served models, usage, cost, latency; `Storage` protocol; `transcript_from_turn`) + `src/storage/sqlite.py` (`SQLiteStorage`, one JSON table indexed by created_at).
- M1.13: `src/assistant/api.py` (`create_app()` with injectable provider factory + storage; `POST /chat` streams SSE frames tool_call/tool_result/text/retract/done/transcript/error; transcript saved to SQLite; `GET /health`). Run with `uv run uvicorn assistant.api:app --reload`.
- M1.14: `src/assistant/insights.py` (code gathers 3 tool outputs → one structured-output call → Pydantic `InsightCards` (1-3 cards, evidence required) → 1 retry with the validation error; retries counted), `prompts/insights/v1.md` (locked), `GET /insights/{profile_id}` (502 if both attempts fail). Live test written, skipped until key.
- M1.15: `evals/cases.py` (`Case` schema: kind chat|insights, 7 categories, expectations incl. must_call_tools with partial-arg match, must/must-not contain, regex must_not_match, expected_refusal, disclaimer, numeric_facts, must_mention_factors, rubric_notes; `load_cases` reports every problem at once), `python -m evals validate`, empty `evals/datasets/golden.jsonl`.
**Decisions:**
- Domain code lives in `src/credit/` (factors, profile schema, scoring, months, generator, tools). `data/generate_profiles.py` will be a thin CLI wrapper.
- Profiles have no person names at all, only ids (`p_001`, `story_001`, `inj_001`). Data window is the 12 months ending 2026-06, fixed so output doesn't depend on today's date.
- `scripts/mark_task.sh <done_id> <next_id>` updates BUILD_STATUS.md.
- **API constraints** (in PRD §14): there's no temperature 0 (sampling params return a 400), so reproducibility comes from the cache; no forced `tool_choice` on Sonnet 5.5, so insight cards use `output_config.format`; set `effort` per route; Haiku 4.5 has no effort param.
- Sonnet 5.5 has `refusal_fallback: true` (server-side `fallbacks: "default"`, beta `server-side-fallback-2026-07-01`), so a refused request is re-run on a fallback model. `served_model` is recorded on every response so evals can see when this happened.
- Tool executor (`assistant.loop.execute_tool`) refuses any `profile_id` other than the conversation's own, a deterministic guard against injection steering the model to other profiles.
**Blockers:** M0.2 (API key) is with the owner. Live tests (`@pytest.mark.live`) are skipped until then. Run them with `uv run pytest -m live` once `.env` has the key. M0.4 (GitHub repo) is deferred to M2.14.
**Next:** Owner: M1.16 (seed cases; template coming in `evals/datasets/SEED_TEMPLATE.md`). Claude: M1.18 (deterministic scorers in `evals/scorers/`), then M1.19–M1.21.

## 2026-10-31 — Session 1 (planning)
**Done:** Read PRD. Grilling session settled 46 design decisions, written to PRD.md §14 (v2) and CLAUDE.md. Created BUILD_STATUS.md and BUILD_LOG.md.
**Decisions:** AWS → optional M6. Java conditional on target roles. Haiku 5.5 is the cheap route. Pinned Sonnet 5.5 judge. Local-only core.
**Environment found:** Python 3.14 system install (use uv-managed 3.12; Presidio/spaCy may not support 3.14), git + gh installed, no uv, no Docker, no `ANTHROPIC_API_KEY`. Not yet a git repo.
**Blockers:** M0.1 (uv) and M0.2 (API key) are owner tasks. M0.3 and M1.1–M1.9 don't need the key.
**Next:** Owner does M0.1 and M0.2. Claude does M0.3 (repo skeleton), then M1.1.
