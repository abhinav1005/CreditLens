import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { getJSON, streamChat, type ChatMessage, type ProfileSummary } from "./api";
import {
  applyEvent,
  emptyAssistantTurn,
  flagLabel,
  TOOL_LABELS,
  type AssistantTurn,
  type Turn,
} from "./chatState";

const EXAMPLES = [
  "Why did my score change last month?",
  "What's my credit utilization?",
  "What if I paid $500 off my biggest card?",
  "What is a hard inquiry?",
];

export default function Chat() {
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [profileId, setProfileId] = useState("story_001");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getJSON<ProfileSummary[]>("/profiles")
      .then(setProfiles)
      .catch((e: Error) => setLoadError(e.message));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  function switchProfile(id: string) {
    setProfileId(id);
    setTurns([]);
    setConversationId(null);
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    // History sent to the API: user messages plus the assistant's final replies.
    const history: ChatMessage[] = turns
      .filter((t) => t.text)
      .map((t) => ({ role: t.role, content: t.text }));
    history.push({ role: "user", content: text });
    setTurns((prev) => [...prev, { role: "user", text }, emptyAssistantTurn()]);
    setDraft("");
    setBusy(true);
    const updateLast = (fn: (t: AssistantTurn) => AssistantTurn) =>
      setTurns((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1] as AssistantTurn)]);
    try {
      await streamChat(
        { profile_id: profileId, conversation_id: conversationId, messages: history },
        (event) => {
          if (event.type === "transcript") setConversationId(event.conversation_id);
          updateLast((t) => applyEvent(t, event));
        },
      );
    } catch (e) {
      updateLast((t) => ({ ...t, error: (e as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  const profile = profiles.find((p) => p.profile_id === profileId);

  return (
    <div className="chat">
      <div className="toolbar">
        <label>
          Profile{" "}
          <select value={profileId} onChange={(e) => switchProfile(e.target.value)}>
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.profile_id} · score {p.score}
              </option>
            ))}
          </select>
        </label>
        {profile && (
          <span className="muted">
            {profile.n_accounts} accounts, data as of {profile.as_of}
            {profile.story ? ` · ${profile.story}` : ""}
          </span>
        )}
        {turns.length > 0 && (
          <button className="link" onClick={() => switchProfile(profileId)} disabled={busy}>
            New conversation
          </button>
        )}
      </div>
      {loadError && <p className="error">Can't reach the API ({loadError}). Is uvicorn running?</p>}

      <div className="messages">
        {turns.length === 0 && (
          <div className="empty">
            <p>Ask about this synthetic profile. Try:</p>
            <div className="examples">
              {EXAMPLES.map((q) => (
                <button key={q} onClick={() => send(q)} disabled={busy}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="msg user">
              {t.text}
            </div>
          ) : (
            <AssistantMessage key={i} turn={t} pending={busy && i === turns.length - 1} />
          ),
        )}
        <div ref={endRef} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about this profile…"
          aria-label="Message"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

function AssistantMessage({ turn, pending }: { turn: AssistantTurn; pending: boolean }) {
  return (
    <div className="msg assistant">
      {turn.tools.length > 0 && (
        <ul className="tools">
          {turn.tools.map((tool) => (
            <li key={tool.id} className={tool.isError ? "error" : tool.done ? "done" : ""}>
              {tool.done ? (tool.isError ? "✕" : "✓") : "…"} {TOOL_LABELS[tool.name] ?? tool.name}{" "}
              <code>{tool.name}</code>
            </li>
          ))}
        </ul>
      )}
      {turn.text ? (
        <div className="text">
          <Markdown>{turn.text}</Markdown>
        </div>
      ) : (
        pending && !turn.error && <p className="muted">Thinking…</p>
      )}
      {turn.error && <p className="error">Error: {turn.error}</p>}
      {(turn.flags.length > 0 || turn.retracted || turn.stop === "blocked") && (
        <div className="badges">
          {turn.flags.map((f, i) => (
            <span key={i} className={`badge ${f.action}`} title={f.reasons.join(", ")}>
              {flagLabel(f)}
            </span>
          ))}
          {turn.retracted && !turn.flags.some((f) => f.action === "retract") && (
            <span className="badge retract" title={turn.retracted.join(", ")}>
              Reply replaced by output check
            </span>
          )}
        </div>
      )}
      {turn.meta && (
        <p className="meta">
          {turn.meta.model} · prompt {turn.meta.promptVersion} · ${turn.meta.costUsd.toFixed(4)} ·{" "}
          {(turn.meta.latencyMs / 1000).toFixed(1)}s
          {turn.transcriptId && (
            <>
              {" · "}
              <a href={`#transcripts/${turn.transcriptId}`}>transcript</a>
            </>
          )}
        </p>
      )}
    </div>
  );
}
