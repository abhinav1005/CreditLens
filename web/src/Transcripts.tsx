import { useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";

import { getJSON, type GuardrailFlag } from "./api";
import { flagLabel } from "./chatState";

export interface TranscriptRow {
  transcript_id: string;
  created_at: string;
  conversation_id: string;
  profile_id: string;
  model: string;
  prompt_version: string;
  variant: string | null;
  stop: string;
  cost_usd: number;
  latency_ms: number;
  question: string;
  tools: string[];
  guardrails: GuardrailFlag[];
}

// The stored record (storage/transcripts.py). Only the fields the viewer shows are typed.
interface StoredMessage {
  role: "user" | "assistant" | "tool";
  content?: string;
  tool_calls?: { id: string; name: string; input: unknown }[];
  results?: { tool_call_id: string; content: string }[];
}

interface GuardrailDecision extends GuardrailFlag {
  allowed: boolean;
  scores: Record<string, number>;
  tool?: string;
}

interface TranscriptDetail extends Omit<TranscriptRow, "question" | "tools" | "guardrails"> {
  served_models: string[];
  prompt_hash: string;
  messages: StoredMessage[];
  tool_calls: { id: string; name: string; input: unknown; output: unknown }[];
  filter_decisions: { filter_name: string; action: string; reasons: string[]; text: string }[];
  guardrail_decisions: GuardrailDecision[];
  final_text: string;
  usage: Record<string, number>;
  ttft_ms: number | null;
  extra: Record<string, unknown>;
}

export default function Transcripts({ selectedId }: { selectedId: string | null }) {
  return selectedId ? <TranscriptView id={selectedId} /> : <TranscriptList />;
}

function TranscriptList() {
  const [rows, setRows] = useState<TranscriptRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState("");
  const [model, setModel] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getJSON<TranscriptRow[]>("/transcripts")
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  const options = (key: "profile_id" | "model") =>
    [...new Set((rows ?? []).map((r) => r[key]))].sort();

  const shown = useMemo(
    () =>
      (rows ?? []).filter(
        (r) =>
          (!profile || r.profile_id === profile) &&
          (!model || r.model === model) &&
          (!flaggedOnly || r.guardrails.length > 0 || r.stop !== "complete") &&
          (!search || r.question.toLowerCase().includes(search.toLowerCase())),
      ),
    [rows, profile, model, flaggedOnly, search],
  );

  if (error) return <p className="error">Can't load transcripts ({error}).</p>;
  if (rows === null) return <p className="muted">Loading…</p>;

  return (
    <div className="stack">
      <div className="toolbar">
        <select value={profile} onChange={(e) => setProfile(e.target.value)} aria-label="Profile">
          <option value="">All profiles</option>
          {options("profile_id").map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model">
          <option value="">All models</option>
          {options("model").map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
        <label>
          <input
            type="checkbox"
            checked={flaggedOnly}
            onChange={(e) => setFlaggedOnly(e.target.checked)}
          />{" "}
          Guardrail action or incomplete
        </label>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search questions"
          aria-label="Search questions"
        />
        <span className="muted">
          {shown.length} of {rows.length}
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="muted">No transcripts yet. Chat first; every turn is saved.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When (UTC)</th>
                <th>Profile</th>
                <th>Question</th>
                <th>Model</th>
                <th>Flags</th>
                <th className="num">Cost</th>
                <th className="num">Latency</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={r.transcript_id}
                  onClick={() => (window.location.hash = `transcripts/${r.transcript_id}`)}
                >
                  <td className="nowrap">{r.created_at.replace("T", " ").slice(0, 16)}</td>
                  <td>{r.profile_id}</td>
                  <td>{r.question}</td>
                  <td className="nowrap">
                    {r.model}
                    {r.variant ? ` (${r.variant})` : ""}
                  </td>
                  <td>
                    {r.stop !== "complete" && <span className="badge block">{r.stop}</span>}
                    {r.guardrails.map((f, i) => (
                      <span key={i} className={`badge ${f.action}`}>
                        {f.name} {f.action}
                      </span>
                    ))}
                  </td>
                  <td className="num">${r.cost_usd.toFixed(4)}</td>
                  <td className="num">{(r.latency_ms / 1000).toFixed(1)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TranscriptView({ id }: { id: string }) {
  const [t, setT] = useState<TranscriptDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJSON<TranscriptDetail>(`/transcripts/${id}`)
      .then(setT)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) return <p className="error">Can't load transcript ({error}).</p>;
  if (t === null) return <p className="muted">Loading…</p>;

  const outputs = new Map(t.tool_calls.map((c) => [c.id, c.output]));
  const acted = t.filter_decisions.filter((d) => d.action !== "pass");

  return (
    <div className="stack">
      <p>
        <a href="#transcripts">← All transcripts</a>
      </p>
      <dl className="facts">
        <dt>Transcript</dt>
        <dd>
          <code>{t.transcript_id}</code>
        </dd>
        <dt>Profile</dt>
        <dd>{t.profile_id}</dd>
        <dt>Model</dt>
        <dd>
          {t.model}
          {t.served_models.some((m) => m !== t.model) && ` (served: ${t.served_models.join(", ")})`}
          {t.variant && ` · A/B arm ${t.variant}`}
        </dd>
        <dt>Prompt</dt>
        <dd>
          {t.prompt_version} <code>{t.prompt_hash.slice(0, 12)}</code>
        </dd>
        <dt>Outcome</dt>
        <dd>
          {t.stop} · ${t.cost_usd.toFixed(4)} · {(t.latency_ms / 1000).toFixed(1)}s total
          {t.ttft_ms !== null && ` · first text ${(t.ttft_ms / 1000).toFixed(1)}s`}
        </dd>
        <dt>Tokens</dt>
        <dd>
          {Object.entries(t.usage)
            .map(([k, v]) => `${k.replace("_tokens", "")} ${v}`)
            .join(" · ")}
        </dd>
      </dl>

      <h2>Conversation (as stored, after PII redaction)</h2>
      <div className="messages">
        {t.messages.map((m, i) => {
          if (m.role === "user")
            return (
              <div key={i} className="msg user">
                {m.content}
              </div>
            );
          if (m.role === "tool")
            return (
              <div key={i} className="msg tool">
                {(m.results ?? []).map((r) => (
                  <details key={r.tool_call_id}>
                    <summary>Tool result</summary>
                    <pre>{pretty(outputs.get(r.tool_call_id) ?? r.content)}</pre>
                  </details>
                ))}
              </div>
            );
          return (
            <div key={i} className="msg assistant">
              {m.content && <Markdown>{m.content}</Markdown>}
              {(m.tool_calls ?? []).map((c) => (
                <p key={c.id} className="muted">
                  Calls <code>{c.name}</code> <code>{JSON.stringify(c.input)}</code>
                </p>
              ))}
            </div>
          );
        })}
      </div>

      <h2>Final reply shown to the user</h2>
      <div className="msg assistant">
        <Markdown>{t.final_text}</Markdown>
      </div>

      <h2>Guardrail decisions</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Stage</th>
              <th>Guardrail</th>
              <th>Action</th>
              <th>Reasons</th>
              <th>Scores</th>
            </tr>
          </thead>
          <tbody>
            {t.guardrail_decisions.map((d, i) => (
              <tr key={i}>
                <td>
                  {d.stage}
                  {d.tool ? ` (${d.tool})` : ""}
                </td>
                <td>{d.name}</td>
                <td>
                  {d.action === "pass" ? (
                    "pass"
                  ) : (
                    <span className={`badge ${d.action}`}>{flagLabel(d)}</span>
                  )}
                </td>
                <td>{d.reasons.join(", ")}</td>
                <td className="muted">
                  {Object.entries(d.scores)
                    .map(([k, v]) => `${k} ${v}`)
                    .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        Output sentence filters: {t.filter_decisions.length} checks, {acted.length} acted.
      </p>
      {acted.map((d, i) => (
        <p key={i}>
          <span className={`badge ${d.action}`}>
            {d.filter_name} {d.action}
          </span>{" "}
          {d.reasons.join(", ")}
        </p>
      ))}
      {Object.keys(t.extra).length > 0 && (
        <details>
          <summary>Extra (compliance retries, routing, trimming)</summary>
          <pre>{pretty(t.extra)}</pre>
        </details>
      )}
    </div>
  );
}

function pretty(value: unknown): string {
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}
