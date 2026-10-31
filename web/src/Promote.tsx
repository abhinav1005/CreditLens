import { useState } from "react";

import { postJSON } from "./api";

// "Promote to test": turn a bad transcript into a golden case, through the same code as
// `python -m evals promote`. The case is appended to evals/datasets/golden.jsonl, where it
// shows up in `git diff` for review like any hand-written case.

// Values of evals.cases.Category; chat transcripts can't be insight_grounding cases.
const CATEGORIES = ["compliance", "factual", "tool_use", "refusal", "injection", "pii"];

const lines = (text: string) =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

export default function Promote({ transcriptId }: { transcriptId: string }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("compliance");
  const [note, setNote] = useState("");
  const [mustNot, setMustNot] = useState("");
  const [must, setMust] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (result) {
    return (
      <p className="notice">
        Added case <code>{result}</code> to <code>evals/datasets/golden.jsonl</code>. Review it in{" "}
        <code>git diff</code>, then run <code>uv run python -m evals validate</code> and regenerate
        the dashboard and README (<code>uv run python -m evals dashboard</code>,{" "}
        <code>uv run python -m evals readme</code>).
      </p>
    );
  }

  if (!open) {
    return (
      <p>
        <button onClick={() => setOpen(true)}>Promote to test case…</button>
      </p>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { category, note, must_not_contain: lines(mustNot), must_contain: lines(must) };
      const caseRecord = await postJSON<{ id: string }>(
        `/transcripts/${transcriptId}/promote`,
        body,
      );
      setResult(caseRecord.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack panel promote" onSubmit={submit}>
      <h2>Promote to test case</h2>
      <p className="muted">
        The case replays this conversation up to the last user message; only the reply is
        regenerated when the suite runs.
      </p>
      <label>
        Category{" "}
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <label className="stack">
        What was wrong (becomes the case's rubric notes)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} required />
      </label>
      <label className="stack">
        Must NOT contain (one phrase per line)
        <textarea value={mustNot} onChange={(e) => setMustNot(e.target.value)} rows={2} />
      </label>
      <label className="stack">
        Must contain (one phrase per line)
        <textarea value={must} onChange={(e) => setMust(e.target.value)} rows={2} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="toolbar">
        <button type="submit" disabled={busy || !note.trim()}>
          Add to golden set
        </button>
        <button type="button" className="ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
