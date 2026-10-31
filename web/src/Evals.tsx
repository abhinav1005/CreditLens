import { useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";

import { getJSON } from "./api";

// Eval run browser. Reads saved runs (reports/) through evals/web_routes.py; no API calls
// to a model happen here. Routes: #evals, #evals/<run>, #evals/<run>/<case>,
// #evals/compare/<a>/<b>.

interface RunSummary {
  run_id: string;
  location: string;
  suite: string;
  model: string;
  prompt_version: string;
  created_at: string;
  n_cases: number;
  n_passed: number;
  pass_rate: number;
  categories: Record<string, { n: number; passed: number; pass_rate: number }>;
  cost_usd: number;
  judge_mode: string;
  tags: string[] | null;
}

interface CaseRow {
  case_id: string;
  category: string;
  passed: boolean;
  status: string;
  failed_checks: { name: string; scorer: string; detail: string }[];
  n_checks: number;
  question: string | null;
  kind: string | null;
  expectations: Record<string, unknown> | null;
  final_text: string | null;
  cards: unknown;
  tools: string[];
  judge: Record<string, { verdict: string; rationale: string }>;
  cost_usd: number | null;
  latency_ms: number | null;
}

interface Comparison {
  a: string;
  b: string;
  n_shared: number;
  a_pass_rate: number | null;
  b_pass_rate: number | null;
  per_category: Record<string, { n: number; a_passed: number; b_passed: number; lost: number }>;
  newly_failing: { case_id: string; category: string; checks: string[] }[];
  newly_passing: { case_id: string; category: string }[];
}

const pct = (x: number | null) => (x === null ? "n/a" : `${(100 * x).toFixed(1)}%`);

function useFetch<T>(path: string) {
  const [state, setState] = useState<{ path: string; data?: T; error?: string } | null>(null);
  useEffect(() => {
    let live = true;
    getJSON<T>(path)
      .then((data) => live && setState({ path, data }))
      .catch((e: Error) => live && setState({ path, error: e.message }));
    return () => {
      live = false;
    };
  }, [path]);
  // Ignore a result that belongs to a previous path.
  return state?.path === path ? state : null;
}

export default function Evals({ params }: { params: string[] }) {
  if (params[0] === "compare" && params[1] && params[2])
    return <CompareView a={params[1]} b={params[2]} />;
  if (params[0]) return <RunView runId={params[0]} openCase={params[1] ?? null} />;
  return <RunList />;
}

function RunList() {
  const state = useFetch<RunSummary[]>("/evals/runs");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  if (!state) return <p className="muted">Loading…</p>;
  if (state.error) return <p className="error">Can't load runs ({state.error}).</p>;
  const runs = state.data!;

  return (
    <div className="stack">
      <p className="muted">
        Every saved eval run (from <code>reports/</code>). Open one to see each case, the checks
        that failed, and the model's answer. Runs are made with{" "}
        <code>uv run python -m evals run …</code>.
      </p>
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          if (a && b) window.location.hash = `evals/compare/${a}/${b}`;
        }}
      >
        <strong>Compare</strong>
        <select value={a} onChange={(e) => setA(e.target.value)} aria-label="Run A">
          <option value="">Run A (before)…</option>
          {runs.map((r) => (
            <option key={r.run_id}>{r.run_id}</option>
          ))}
        </select>
        <span>→</span>
        <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Run B">
          <option value="">Run B (after)…</option>
          {runs.map((r) => (
            <option key={r.run_id}>{r.run_id}</option>
          ))}
        </select>
        <button type="submit" disabled={!a || !b || a === b}>
          Compare
        </button>
      </form>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Suite</th>
              <th>Model · prompt</th>
              <th>Pass rate</th>
              <th className="num">Cost</th>
              <th>Judge</th>
              <th>When (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id} onClick={() => (window.location.hash = `evals/${r.run_id}`)}>
                <td>
                  <a href={`#evals/${r.run_id}`}>{r.run_id}</a>
                  {r.location !== "reports" && <span className="muted"> · {r.location}</span>}
                </td>
                <td>
                  {r.suite}
                  {r.tags?.length ? ` (${r.tags.join(",")})` : ""}
                </td>
                <td className="nowrap">
                  {r.model} · {r.prompt_version}
                </td>
                <td>
                  <span className="meter">
                    <span className="meter-track">
                      <span className="meter-fill" style={{ width: `${100 * r.pass_rate}%` }} />
                    </span>
                    <span className="num">
                      {pct(r.pass_rate)} ({r.n_passed}/{r.n_cases})
                    </span>
                  </span>
                </td>
                <td className="num">${r.cost_usd.toFixed(3)}</td>
                <td>{r.judge_mode}</td>
                <td className="nowrap">{r.created_at.replace("T", " ").slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RunView({ runId, openCase }: { runId: string; openCase: string | null }) {
  const state = useFetch<{ summary: RunSummary; cases: CaseRow[] }>(`/evals/runs/${runId}`);
  const [category, setCategory] = useState("");
  const [failingOnly, setFailingOnly] = useState(false);
  const [search, setSearch] = useState("");

  const rows = state?.data?.cases;
  const shown = useMemo(
    () =>
      (rows ?? []).filter(
        (c) =>
          (!category || c.category === category) &&
          (!failingOnly || !c.passed) &&
          (!search ||
            `${c.case_id} ${c.question ?? ""}`.toLowerCase().includes(search.toLowerCase())),
      ),
    [rows, category, failingOnly, search],
  );

  useEffect(() => {
    if (openCase) document.getElementById(`case-${openCase}`)?.scrollIntoView({ block: "start" });
  }, [openCase, rows]);

  if (!state) return <p className="muted">Loading…</p>;
  if (state.error) return <p className="error">Can't load run ({state.error}).</p>;
  const { summary } = state.data!;
  const categories = Object.keys(summary.categories).sort();

  return (
    <div className="stack">
      <p>
        <a href="#evals">← All runs</a>
      </p>
      <h2>{summary.run_id}</h2>
      <p className="muted">
        {summary.suite} suite · {summary.model} · prompt {summary.prompt_version} · judge{" "}
        {summary.judge_mode} · ${summary.cost_usd.toFixed(3)} ·{" "}
        {summary.created_at.replace("T", " ").slice(0, 16)} UTC
      </p>
      <div className="tiles">
        <div className="tile">
          <span className="tile-label">Passed</span>
          <span className="tile-value">{pct(summary.pass_rate)}</span>
          <span className="muted">
            {summary.n_passed} of {summary.n_cases} cases
          </span>
        </div>
        {categories.map((c) => {
          const s = summary.categories[c];
          return (
            <button
              key={c}
              className={`tile tile-button ${category === c ? "selected" : ""}`}
              onClick={() => setCategory(category === c ? "" : c)}
              title="Filter to this category"
            >
              <span className="tile-label">{c}</span>
              <span className="tile-value small">
                {s.passed}/{s.n}
              </span>
            </button>
          );
        })}
      </div>
      <div className="toolbar">
        <label>
          <input
            type="checkbox"
            checked={failingOnly}
            onChange={(e) => setFailingOnly(e.target.checked)}
          />{" "}
          Failing only
        </label>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search id or question"
          aria-label="Search cases"
        />
        {category && (
          <button className="link" onClick={() => setCategory("")}>
            Clear category ({category})
          </button>
        )}
        <span className="muted">
          {shown.length} of {rows!.length}
        </span>
      </div>
      <div className="case-list">
        {shown.map((c) => (
          <CaseItem key={c.case_id} row={c} runId={runId} open={c.case_id === openCase} />
        ))}
      </div>
    </div>
  );
}

function CaseItem({ row, runId, open }: { row: CaseRow; runId: string; open: boolean }) {
  const expectations = Object.entries(row.expectations ?? {}).filter(
    ([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0),
  );
  return (
    <details id={`case-${row.case_id}`} className="case" open={open}>
      <summary>
        <span className={`badge ${row.passed ? "pass" : "block"}`}>
          {row.passed ? "pass" : row.status === "ok" ? "fail" : row.status}
        </span>{" "}
        <code>{row.case_id}</code> <span className="muted">{row.category}</span>{" "}
        <span className="case-q">{row.question ?? "(insight cards)"}</span>
        {row.failed_checks.length > 0 && (
          <span className="error"> · {row.failed_checks.map((f) => f.name).join(", ")}</span>
        )}
      </summary>
      <div className="stack case-body">
        <p className="muted">
          <a href={`#evals/${runId}/${row.case_id}`}>Link to this case</a> ·{" "}
          {row.n_checks - row.failed_checks.length}/{row.n_checks} checks passed
          {row.tools.length > 0 && ` · tools: ${row.tools.join(", ")}`}
          {row.latency_ms !== null && ` · ${(row.latency_ms / 1000).toFixed(1)}s`}
        </p>
        {row.failed_checks.length > 0 && (
          <div>
            <h3>Failed checks</h3>
            <ul>
              {row.failed_checks.map((f, i) => (
                <li key={i}>
                  <code>{f.name}</code> <span className="muted">({f.scorer})</span>{" "}
                  {f.detail && <span>{f.detail}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <h3>Answer</h3>
        <div className="msg assistant reply">
          {row.final_text ? (
            <Markdown>{row.final_text}</Markdown>
          ) : (
            <pre>{JSON.stringify(row.cards, null, 2)}</pre>
          )}
        </div>
        {Object.keys(row.judge).length > 0 && (
          <div>
            <h3>LLM judge (report only)</h3>
            <ul>
              {Object.entries(row.judge).map(([dim, v]) => (
                <li key={dim}>
                  <span className={`badge ${v.verdict === "pass" ? "pass" : "block"}`}>
                    {dim}: {v.verdict}
                  </span>{" "}
                  <span className="muted">{v.rationale}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {expectations.length > 0 && (
          <details>
            <summary>What the case expects</summary>
            <pre>{JSON.stringify(Object.fromEntries(expectations), null, 2)}</pre>
          </details>
        )}
      </div>
    </details>
  );
}

function CompareView({ a, b }: { a: string; b: string }) {
  const state = useFetch<Comparison>(`/evals/compare?${new URLSearchParams({ a, b }).toString()}`);
  if (!state) return <p className="muted">Loading…</p>;
  if (state.error) return <p className="error">Can't compare ({state.error}).</p>;
  const d = state.data!;

  return (
    <div className="stack">
      <p>
        <a href="#evals">← All runs</a>
      </p>
      <h2>
        {a} → {b}
      </h2>
      <p>
        {d.n_shared} shared cases · overall <strong>{pct(d.a_pass_rate)}</strong> →{" "}
        <strong>{pct(d.b_pass_rate)}</strong>
      </p>
      <div className="table-wrap">
        <table className="static">
          <thead>
            <tr>
              <th>Category</th>
              <th className="num">{a}</th>
              <th className="num">{b}</th>
              <th className="num">Lost</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(d.per_category).map(([cat, c]) => (
              <tr key={cat}>
                <td>{cat}</td>
                <td className="num">
                  {c.a_passed}/{c.n}
                </td>
                <td className="num">
                  {c.b_passed}/{c.n}
                </td>
                <td className={`num ${c.lost >= 2 ? "error" : ""}`}>{c.lost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Newly failing ({d.newly_failing.length})</h3>
      {d.newly_failing.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul>
          {d.newly_failing.map((c) => (
            <li key={c.case_id}>
              <a href={`#evals/${b}/${c.case_id}`}>
                <code>{c.case_id}</code>
              </a>{" "}
              <span className="muted">{c.category}</span> · {c.checks.join(", ")}
            </li>
          ))}
        </ul>
      )}
      <h3>Newly passing ({d.newly_passing.length})</h3>
      {d.newly_passing.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul>
          {d.newly_passing.map((c) => (
            <li key={c.case_id}>
              <a href={`#evals/${b}/${c.case_id}`}>
                <code>{c.case_id}</code>
              </a>{" "}
              <span className="muted">{c.category}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
