import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";

import { getJSON, postJSON } from "./api";

// Blind hand-labeling for judge calibration. The server never sends the model, prompt
// version, or judge verdict, so none of it can bias the label (see evals/web_routes.py).

interface Dimension {
  name: string;
  hint: string;
}

interface ConversationMessage {
  role: "user" | "assistant" | "tool";
  content?: string;
  tool_calls?: { name: string; input: unknown }[];
  results?: { content: string }[];
}

interface Item {
  item_id: string;
  case_id: string;
  category: string;
  kind: "chat" | "insights";
  conversation: ConversationMessage[];
  tool_calls: { name: string; input: unknown; output: unknown }[];
  reply: string | null;
  cards: unknown;
  rubric_notes: string;
}

interface NextResponse {
  item: Item | null;
  progress: { done: number; target: number; pool_size: number };
}

type Verdict = "pass" | "fail";

const NAME_KEY = "creditlens.labeler";

function savedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export default function Label() {
  const [labeler, setLabeler] = useState(savedName);
  const [nameDraft, setNameDraft] = useState(savedName);
  const [dims, setDims] = useState<Dimension[]>([]);
  const [data, setData] = useState<NextResponse | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getJSON<Dimension[]>("/labeling/dimensions")
      .then(setDims)
      .catch((e: Error) => setStatus(`Can't reach the API (${e.message}).`));
  }, []);

  const load = useCallback(
    (skip: string[]) => {
      if (!labeler) return;
      const query = new URLSearchParams({ labeler, skip: skip.join(",") });
      getJSON<NextResponse>(`/labeling/next?${query}`)
        .then((d) => {
          setData(d);
          setVerdicts([]);
          setNote("");
        })
        .catch((e: Error) => setStatus(e.message));
    },
    [labeler],
  );

  useEffect(() => load([]), [load]);

  const item = data?.item ?? null;
  const complete = dims.length > 0 && verdicts.length === dims.length;

  const save = useCallback(async () => {
    if (!item || !complete || saving) return;
    setSaving(true);
    try {
      await postJSON("/labeling/labels", {
        item_id: item.item_id,
        labeler,
        verdicts: Object.fromEntries(dims.map((d, i) => [d.name, verdicts[i]])),
        note,
      });
      setStatus(`Saved ${item.case_id}.`);
      load(skipped);
    } catch (e) {
      setStatus(`Not saved: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }, [item, complete, saving, labeler, dims, verdicts, note, skipped, load]);

  const skip = useCallback(() => {
    if (!item) return;
    const next = [...skipped, item.item_id];
    setSkipped(next);
    setStatus(`Skipped ${item.case_id} (until you reload).`);
    load(next);
  }, [item, skipped, load]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") {
        if (e.key === "Escape") target.blur();
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || !item) return;
      const key = e.key.toLowerCase();
      if ((key === "p" || key === "f") && verdicts.length < dims.length) {
        setVerdicts([...verdicts, key === "p" ? "pass" : "fail"]);
      } else if (key === "backspace") {
        setVerdicts(verdicts.slice(0, -1));
      } else if (key === "s") {
        skip();
      } else if (key === "enter") {
        save();
      } else if (key === "n") {
        document.getElementById("label-note")?.focus();
      } else {
        return;
      }
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, verdicts, dims, save, skip]);

  if (!labeler) {
    return (
      <form
        className="stack narrow"
        onSubmit={(e) => {
          e.preventDefault();
          const name = nameDraft.trim();
          if (!name) return;
          try {
            localStorage.setItem(NAME_KEY, name);
          } catch {
            // Private window: the name just isn't remembered.
          }
          setLabeler(name);
        }}
      >
        <p>
          Label assistant replies pass/fail on each dimension. Your labels calibrate the LLM judge.
          You won't see which model or prompt wrote a reply, or what the judge said.
        </p>
        <label>
          Your name (recorded on each label){" "}
          <input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} autoFocus />
        </label>
        <button type="submit" disabled={!nameDraft.trim()}>
          Start labeling
        </button>
      </form>
    );
  }

  if (!data) return <p className="muted">{status ?? "Loading…"}</p>;

  const { progress } = data;
  return (
    <div className="stack">
      <div className="toolbar">
        <span>
          <strong>{progress.done}</strong> / {progress.target} labeled by {labeler}
        </span>
        <progress value={Math.min(progress.done, progress.target)} max={progress.target} />
        <button className="link" onClick={() => setLabeler("")}>
          Change name
        </button>
        {status && <span className="muted">{status}</span>}
      </div>

      {!item ? (
        <p>
          Nothing left to label{skipped.length > 0 ? " (reload to see skipped items)" : ""}. Next:{" "}
          <code>uv run python -m evals calibrate-judge</code>
        </p>
      ) : (
        <div className="label-layout">
          <section className="stack">
            <p className="muted">
              {item.category} · case {item.case_id}
            </p>
            <h2>Conversation</h2>
            <Conversation messages={item.conversation} />
            <h2>Tool results this turn</h2>
            {item.tool_calls.length === 0 ? (
              <p className="muted">None.</p>
            ) : (
              item.tool_calls.map((c, i) => (
                <details key={i}>
                  <summary>
                    <code>{c.name}</code> <code>{JSON.stringify(c.input)}</code>
                  </summary>
                  <pre>{JSON.stringify(c.output, null, 2)}</pre>
                </details>
              ))
            )}
            <h2>Reply to label</h2>
            <div className="msg assistant reply">
              {item.reply !== null ? (
                <Markdown>{item.reply}</Markdown>
              ) : (
                <pre>{JSON.stringify(item.cards, null, 2)}</pre>
              )}
            </div>
            {item.rubric_notes && (
              <p className="muted">
                <strong>Case notes:</strong> {item.rubric_notes}
              </p>
            )}
          </section>

          <aside className="stack panel">
            {dims.map((d, i) => {
              const v = verdicts[i];
              const current = i === verdicts.length;
              return (
                <div key={d.name} className={`dim ${current ? "current" : ""}`}>
                  <div className="dim-head">
                    <strong>{d.name}</strong>
                    <span className="choices">
                      <button
                        className={v === "pass" ? "chosen pass" : "ghost"}
                        onClick={() => setVerdicts([...verdicts.slice(0, i), "pass"])}
                        disabled={i > verdicts.length}
                      >
                        Pass
                      </button>
                      <button
                        className={v === "fail" ? "chosen fail" : "ghost"}
                        onClick={() => setVerdicts([...verdicts.slice(0, i), "fail"])}
                        disabled={i > verdicts.length}
                      >
                        Fail
                      </button>
                    </span>
                  </div>
                  <p className="muted">{d.hint}</p>
                </div>
              );
            })}
            <textarea
              id="label-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Note (optional): why it fails"
              rows={3}
            />
            <div className="toolbar">
              <button onClick={save} disabled={!complete || saving}>
                Save
              </button>
              <button className="ghost" onClick={skip}>
                Skip
              </button>
            </div>
            <p className="muted keys">
              <kbd>P</kbd> pass · <kbd>F</kbd> fail · <kbd>⌫</kbd> undo · <kbd>N</kbd> note ·{" "}
              <kbd>Enter</kbd> save · <kbd>S</kbd> skip · in the note: <kbd>Esc</kbd> leave,{" "}
              <kbd>⌘/Ctrl+Enter</kbd> save
            </p>
          </aside>
        </div>
      )}
    </div>
  );
}

function Conversation({ messages }: { messages: ConversationMessage[] }) {
  return (
    <div className="messages">
      {messages.map((m, i) => {
        if (m.role === "user")
          return (
            <div key={i} className="msg user">
              {m.content}
            </div>
          );
        if (m.role === "tool")
          return (
            <details key={i} className="msg tool">
              <summary>Earlier tool result</summary>
              {(m.results ?? []).map((r, j) => (
                <pre key={j}>{r.content}</pre>
              ))}
            </details>
          );
        return (
          <div key={i} className="msg assistant">
            {m.content && <Markdown>{m.content}</Markdown>}
            {(m.tool_calls ?? []).map((c, j) => (
              <p key={j} className="muted">
                Calls <code>{c.name}</code>
              </p>
            ))}
          </div>
        );
      })}
    </div>
  );
}
