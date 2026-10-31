# Model upgrade playbook

How to evaluate a new model and ship it safely. Every step is a command in this repo, and
every number you quote should come from its output.

## 1. Add the model

- Add it under `models:` in `config.yaml`, with `supports_effort` and `refusal_fallback`
  set to what the model supports.
- Add its prices to `config/pricing.yaml`, and update `as_of`.
- Check the API surface (thinking, effort, sampling, tool choice) against the current
  docs. The 2026 changes we hit are recorded in PRD §14.

## 2. Offline comparison

```bash
uv run python -m evals latency --models <current>,<candidate>          # sequential, fresh calls
uv run python -m evals matrix  --models <current>,<candidate>          # quality × cost × latency
uv run python -m evals compare matrix-<current> matrix-<candidate>     # which cases changed
```

Read `reports/model-comparison.md`, then the newly failing cases. Look at categories, not
only the overall rate: a cheaper model that loses compliance or injection cases isn't a
cheaper model.

## 3. Guardrails and gate

```bash
uv run python -m evals run --suite golden --categories injection,pii,compliance --model <candidate> --judge report
uv run python -m evals run --suite golden --tags smoke --model <candidate> --run-id candidate-smoke
uv run python -m evals gate candidate-smoke
```

The candidate must pass the gate against the committed baseline. If it should become the
new default, re-baseline in a reviewed PR (`python -m evals baseline <run_id>`).

## 4. Shadow / A/B in the app

- Set `ab_test.enabled: true`, `candidate_model: <candidate>` and a small `percent` (e.g. 5–10).
- Assignment is sticky per conversation (a hash of the conversation id), and every
  transcript records its `variant`.
- Compare the arms with the transcript viewer and the judge on sampled transcripts. Look
  at cost and latency per conversation from the transcripts.
- Roll back by setting `enabled: false`. No deploy is needed beyond config.

## 5. Ship

- Switch `assistant.model`, then run the full suite and the gate in a PR.
- Record the decision and the numbers behind it in PRD §14.
