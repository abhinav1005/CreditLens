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
**Decisions:**
- Domain code lives in `src/credit/` (factors, profile schema, scoring, months, generator, tools). `data/generate_profiles.py` will be a thin CLI wrapper.
- Profiles have no person names at all, only ids (`p_001`, `story_001`, `inj_001`). Data window is the 12 months ending 2026-06, fixed so output doesn't depend on today's date.
- `scripts/mark_task.sh <done_id> <next_id>` updates BUILD_STATUS.md.
**Blockers:** M0.2 (API key) is with the owner. Not needed until M1.10's live smoke call. M0.4 (GitHub repo) is deferred to M2.14.
**Next:** M1.3, the seeded generator in `src/credit/generate.py`.

## 2026-10-31 — Session 1 (planning)
**Done:** Read PRD. Grilling session settled 46 design decisions, written to PRD.md §14 (v2) and CLAUDE.md. Created BUILD_STATUS.md and BUILD_LOG.md.
**Decisions:** AWS → optional M6. Java conditional on target roles. Haiku 5.5 is the cheap route. Pinned Sonnet 5.5 judge. Local-only core.
**Environment found:** Python 3.14 system install (use uv-managed 3.12; Presidio/spaCy may not support 3.14), git + gh installed, no uv, no Docker, no `ANTHROPIC_API_KEY`. Not yet a git repo.
**Blockers:** M0.1 (uv) and M0.2 (API key) are owner tasks. M0.3 and M1.1–M1.9 don't need the key.
**Next:** Owner does M0.1 and M0.2. Claude does M0.3 (repo skeleton), then M1.1.
