import { useEffect, useState, type ReactNode } from "react";

// Static dashboard: renders /dashboard.json, which `uv run python -m evals dashboard` builds
// from the committed reports. Nothing here computes or types in a number; it only formats.

interface RunRow {
  name: string;
  pass_rate: number;
  n_passed: number;
  n_cases: number;
  cost_usd: number;
  latency_p50_ms?: number;
  ttft_p50_ms?: number;
  input_tokens?: number;
}

interface DashboardData {
  golden: {
    source: string;
    n_cases: number;
    by_category: Record<string, number>;
    human_reviewed: number;
    smoke: number;
  };
  models: {
    source: string;
    n_cases: number;
    pricing_as_of: string;
    rows: {
      model: string;
      pass_rate: number;
      categories: Record<string, number>;
      judge: Record<string, number>;
      cost_per_case_usd: number;
      latency_p50_ms: number | null;
      latency_p95_ms: number | null;
      ttft_p50_ms: number | null;
    }[];
  };
  guardrails: {
    source: string;
    rows: {
      guardrail: string;
      n_positive: number;
      n_negative: number;
      recall: number;
      false_positive_rate: number;
      rules_only_recall: number | null;
    }[];
  };
  end_to_end: {
    source: string;
    scenarios: { prompt: string; n: number; harm_off: number; harm_on: number }[];
  };
  variants: { source: string; routing: RunRow[]; caching: RunRow[]; trimming: RunRow[] };
  gate: {
    source: string;
    baseline_run: string;
    model: string;
    n_cases: number;
    pass_rate: number;
  };
  calibration: {
    source: string;
    status: string;
    rows: {
      judge_version: string;
      n_labeled: number;
      main_dimension: string;
      test_kappa: number | null;
      test_kappa_ci95: [number, number] | null;
      test_n: number;
    }[];
  };
  experiments: Experiments | null;
}

interface Experiments {
  source: string;
  model: string;
  reliability: {
    runs: string[];
    n_cases: number;
    pass_rates: number[];
    mean: number;
    min: number;
    max: number;
    stdev: number;
    always_pass: number;
    always_fail: number;
    flaky: string[];
    flaky_by_category: Record<string, number>;
    smoke_n: number;
    smoke_passed: number[];
    smoke_swing: number;
    gate_limit_cases: number;
  };
  ablation: {
    prompt: string;
    what: string;
    pass_rate: number;
    n_passed: number;
    n_cases: number;
    harm: number;
    harm_n: number;
    grounding_failures: number;
    output_tokens_per_case: number;
  }[];
  defense: { prompt: string; guardrails: string; harm: number; n: number }[];
  effort: {
    effort: string;
    runs: number;
    pass_rate: number;
    pass_rate_range: [number, number] | null;
    cost_per_case_usd: number;
    output_tokens_per_case: number;
  }[];
}

const CHECK_NAMES: Record<string, string> = {
  pii: "Personal data",
  injection: "Trick instructions",
  compliance: "Rule-breaking answers",
};

const pct = (x: number | null | undefined, digits = 1) =>
  x === null || x === undefined ? "n/a" : `${(100 * x).toFixed(digits)}%`;
const secs = (ms: number | null | undefined) =>
  ms === null || ms === undefined ? "n/a" : `${(ms / 1000).toFixed(1)}s`;
const usd = (x: number, digits = 4) => `$${x.toFixed(digits)}`;

// A single-series bar for a 0–1 value, next to its number. The number is the label, so
// the bar is never the only way to read the value.
function Meter({ value, label }: { value: number; label: string }) {
  return (
    <span className="meter" title={label}>
      <span className="meter-track">
        <span
          className="meter-fill"
          style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
        />
      </span>
      <span className="num">{label}</span>
    </span>
  );
}

// Collapsed by default, so the page reads as a short list of questions.
function Section({
  title,
  source,
  children,
}: {
  title: string;
  source: string;
  children: ReactNode;
}) {
  return (
    <details className="dash-section">
      <summary>{title}</summary>
      <div className="stack">
        {children}
        <p className="source">
          Reproduce with: <code>{source}</code>
        </p>
      </div>
    </details>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/dashboard.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<DashboardData>;
      })
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error)
    return (
      <p className="error">
        Can't load dashboard.json ({error}). Run <code>uv run python -m evals dashboard</code>.
      </p>
    );
  if (!data) return <p className="muted">Loading…</p>;

  const { golden, models, guardrails, end_to_end, variants, gate, calibration } = data;
  const categories = Object.keys(golden.by_category);

  return (
    <div className="stack">
      <p className="muted">Open any question below to see the numbers.</p>
      <div className="tiles">
        <div className="tile">
          <span className="tile-label">Test questions</span>
          <span className="tile-value">{golden.n_cases}</span>
          <span className="muted">
            {golden.human_reviewed} checked by a person · {golden.smoke} in the shorter automatic
            check
          </span>
        </div>
        <div className="tile">
          <span className="tile-label">Automatic check: starting score</span>
          <span className="tile-value">{pct(gate.pass_rate)}</span>
          <span className="muted">
            of {gate.n_cases} questions · {gate.model}
          </span>
        </div>
        <div className="tile">
          <span className="tile-label">AI marker vs human marking</span>
          <span className="tile-value">
            {calibration.rows.length ? (calibration.rows.at(-1)!.test_kappa ?? "n/a") : "—"}
          </span>
          <span className="muted">{calibration.status}</span>
        </div>
      </div>

      <Section title="Which AI model did best?" source={models.source}>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>Model</th>
                <th>Score</th>
                <th className="num">Cost per question</th>
                <th className="num">Reply time: typical / slow</th>
                <th className="num">Time to first word</th>
                <th className="num">AI marker: follows the rules</th>
                <th className="num">AI marker: sticks to facts</th>
              </tr>
            </thead>
            <tbody>
              {models.rows.map((r) => (
                <tr key={r.model}>
                  <td className="nowrap">
                    <code>{r.model}</code>
                  </td>
                  <td>
                    <Meter value={r.pass_rate} label={pct(r.pass_rate)} />
                  </td>
                  <td className="num">{usd(r.cost_per_case_usd)}</td>
                  <td className="num">
                    {secs(r.latency_p50_ms)} / {secs(r.latency_p95_ms)}
                  </td>
                  <td className="num">{secs(r.ttft_p50_ms)}</td>
                  <td className="num">{pct(r.judge.compliance)}</td>
                  <td className="num">{pct(r.judge.groundedness)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>Question type (how many)</th>
                {models.rows.map((r) => (
                  <th key={r.model} className="num">
                    <code>{r.model}</code>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c}>
                  <td>
                    {c} ({golden.by_category[c]})
                  </td>
                  {models.rows.map((r) => (
                    <td key={r.model} className="num">
                      {pct(r.categories[c], 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          One run per model. An AI wrote the questions and a person hasn't checked them yet. Prices
          as of {models.pricing_as_of}.
        </p>
      </Section>

      <Section title="How well do the safety checks work?" source={guardrails.source}>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>Safety check</th>
                <th>Bad examples caught</th>
                <th className="num">False alarms</th>
                <th className="num">Caught by simple rules alone</th>
                <th className="num">Bad / good examples</th>
              </tr>
            </thead>
            <tbody>
              {guardrails.rows.map((r) => (
                <tr key={r.guardrail}>
                  <td>{CHECK_NAMES[r.guardrail] ?? r.guardrail}</td>
                  <td>
                    <Meter value={r.recall} label={pct(r.recall)} />
                  </td>
                  <td className="num">{pct(r.false_positive_rate)}</td>
                  <td className="num">{pct(r.rules_only_recall)}</td>
                  <td className="num">
                    {r.n_positive} / {r.n_negative}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          Small test sets written for this project: treat 100% as "no misses found here", not as
          proof.
        </p>
      </Section>

      <Section title="Do attacks get through?" source={end_to_end.source}>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>Chatbot instructions</th>
                <th className="num">Safety checks off</th>
                <th className="num">Safety checks on</th>
              </tr>
            </thead>
            <tbody>
              {end_to_end.scenarios.map((s) => (
                <tr key={s.prompt}>
                  <td>
                    <code>{s.prompt}</code>
                  </td>
                  <td className="num">
                    {s.harm_off}/{s.n} ({pct(s.harm_off / s.n, 0)})
                  </td>
                  <td className="num">
                    {s.harm_on}/{s.n} ({pct(s.harm_on / s.n, 0)})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          <code>v1-degraded</code> has deliberately weakened instructions, to show what the safety
          checks catch when the chatbot alone doesn't.
        </p>
      </Section>

      {data.experiments && <ExperimentsSection x={data.experiments} />}

      <Section title="Can it be cheaper or faster?" source={variants.source}>
        <RunTable
          caption="Choosing a model for each question"
          rows={variants.routing}
          extra={[{ head: "Cost", cell: (r) => usd(r.cost_usd, 2) }]}
        />
        <RunTable
          caption="Reusing saved instructions (prompt caching)"
          rows={variants.caching}
          extra={[
            { head: "Cost", cell: (r) => usd(r.cost_usd, 3) },
            { head: "Typical reply time", cell: (r) => secs(r.latency_p50_ms) },
            { head: "Time to first word", cell: (r) => secs(r.ttft_p50_ms) },
          ]}
        />
        <RunTable
          caption="Shortening long conversations"
          rows={variants.trimming}
          extra={[
            { head: "Tokens sent", cell: (r) => (r.input_tokens ?? 0).toLocaleString() },
            { head: "Cost", cell: (r) => usd(r.cost_usd, 3) },
          ]}
        />
      </Section>

      <p className="muted">
        Every number comes from <code>web/public/dashboard.json</code>, generated by{" "}
        <code>uv run python -m evals dashboard</code> from the committed reports. Demo on synthetic
        data; the compliance policy is a demo policy, not legal compliance.
      </p>
    </div>
  );
}

function RunTable({
  caption,
  rows,
  extra,
}: {
  caption: string;
  rows: RunRow[];
  extra: { head: string; cell: (r: RunRow) => string }[];
}) {
  return (
    <div className="table-wrap">
      <table className="static">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th>Option</th>
            <th>Score</th>
            {extra.map((e) => (
              <th key={e.head} className="num">
                {e.head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td>{r.name}</td>
              <td>
                <Meter
                  value={r.pass_rate}
                  label={`${pct(r.pass_rate)} (${r.n_passed}/${r.n_cases})`}
                />
              </td>
              {extra.map((e) => (
                <td key={e.head} className="num">
                  {e.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExperimentsSection({ x }: { x: Experiments }) {
  const rel = x.reliability;
  const cell = (prompt: string, guards: string) => {
    const c = x.defense.find((d) => d.prompt === prompt && d.guardrails === guards);
    return c ? `${c.harm}/${c.n}` : "n/a";
  };
  return (
    <Section title="The experiments" source={x.source}>
      <h3>Does the same test give the same score?</h3>
      <p>
        Score {pct(rel.min)}–{pct(rel.max)} (average {pct(rel.mean)}).{" "}
        <strong>{rel.flaky.length}</strong> of {rel.n_cases} questions changed between runs. The
        shorter {rel.smoke_n}-question check moved by <strong>{rel.smoke_swing}</strong> with
        nothing changed (it allows {rel.gate_limit_cases}).
      </p>
      <div className="table-wrap">
        <table className="static">
          <thead>
            <tr>
              <th>Run</th>
              {rel.runs.map((r) => (
                <th key={r} className="num">
                  {r.replace("exp-repeat-", "#")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Score</td>
              {rel.pass_rates.map((p, i) => (
                <td key={i} className="num">
                  {pct(p)}
                </td>
              ))}
            </tr>
            <tr>
              <td>Short check passed (of {rel.smoke_n})</td>
              {rel.smoke_passed.map((p, i) => (
                <td key={i} className="num">
                  {p}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <h3>What happens when parts of the instructions are removed?</h3>
      <div className="table-wrap">
        <table className="static">
          <thead>
            <tr>
              <th>Instructions</th>
              <th>Score</th>
              <th className="num">Attacks that worked</th>
              <th className="num">Numbers it couldn't back up</th>
              <th className="num">Tokens per question</th>
            </tr>
          </thead>
          <tbody>
            {x.ablation.map((r) => (
              <tr key={r.prompt}>
                <td>
                  <code>{r.prompt}</code> <span className="muted">{r.what}</span>
                </td>
                <td>
                  <Meter value={r.pass_rate} label={`${pct(r.pass_rate)}`} />
                </td>
                <td className="num">
                  {r.harm}/{r.harm_n}
                </td>
                <td className="num">{r.grounding_failures}</td>
                <td className="num">{r.output_tokens_per_case}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Do safety checks make up for weak instructions?</h3>
      <div className="table-wrap">
        <table className="static">
          <thead>
            <tr>
              <th>Instructions</th>
              <th className="num">Safety checks off</th>
              <th className="num">Safety checks on</th>
            </tr>
          </thead>
          <tbody>
            {["v1", "v1-minimal"].map((p) => (
              <tr key={p}>
                <td>
                  <code>{p}</code>
                </td>
                <td className="num">{cell(p, "off")}</td>
                <td className="num">{cell(p, "on")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Does letting it think harder help?</h3>
      <div className="table-wrap">
        <table className="static">
          <thead>
            <tr>
              <th>Effort</th>
              <th>Score</th>
              <th className="num">Tokens per question</th>
            </tr>
          </thead>
          <tbody>
            {x.effort.map((r) => (
              <tr key={r.effort}>
                <td>
                  {r.effort}
                  {r.runs > 1 && <span className="muted"> (average of {r.runs})</span>}
                </td>
                <td>
                  <Meter
                    value={r.pass_rate}
                    label={
                      pct(r.pass_rate) +
                      (r.pass_rate_range
                        ? ` (${pct(r.pass_rate_range[0])}–${pct(r.pass_rate_range[1])})`
                        : "")
                    }
                  />
                </td>
                <td className="num">{r.output_tokens_per_case}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        Compared by tokens (roughly, words generated) rather than cost, because cost here depends on
        the order the tests ran in.
      </p>
    </Section>
  );
}
