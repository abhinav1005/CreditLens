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
}

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
    <section className="stack dash-section">
      <h2>{title}</h2>
      {children}
      <p className="source">
        Source: <code>{source}</code>
      </p>
    </section>
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
      <div className="tiles">
        <div className="tile">
          <span className="tile-label">Golden cases</span>
          <span className="tile-value">{golden.n_cases}</span>
          <span className="muted">
            {golden.human_reviewed} human-reviewed · {golden.smoke} in the CI smoke set
          </span>
        </div>
        <div className="tile">
          <span className="tile-label">CI gate baseline</span>
          <span className="tile-value">{pct(gate.pass_rate)}</span>
          <span className="muted">
            of {gate.n_cases} smoke cases · {gate.model}
          </span>
        </div>
        <div className="tile">
          <span className="tile-label">
            Judge vs human (κ, {calibration.rows[0]?.main_dimension ?? "compliance"})
          </span>
          <span className="tile-value">
            {calibration.rows.length ? (calibration.rows.at(-1)!.test_kappa ?? "n/a") : "—"}
          </span>
          <span className="muted">{calibration.status}</span>
        </div>
      </div>

      <Section title={`Models (golden suite, ${models.n_cases} cases)`} source={models.source}>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>Model</th>
                <th>Pass rate</th>
                <th className="num">Cost / case</th>
                <th className="num">Latency p50 / p95</th>
                <th className="num">First text p50</th>
                <th className="num">Judge: compliant</th>
                <th className="num">Judge: grounded</th>
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
                <th>Category (cases)</th>
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
          One run per model; cases are LLM-drafted and not yet human-reviewed. Pricing as of{" "}
          {models.pricing_as_of}.
        </p>
      </Section>

      <Section title="Guardrails (held-out test split)" source={guardrails.source}>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>Guardrail</th>
                <th>Recall</th>
                <th className="num">False-positive rate</th>
                <th className="num">Rules-only recall</th>
                <th className="num">Positives / negatives</th>
              </tr>
            </thead>
            <tbody>
              {guardrails.rows.map((r) => (
                <tr key={r.guardrail}>
                  <td>{r.guardrail}</td>
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
          Small, self-written test sets: treat 100% as "no misses found here", not as proof.
        </p>
      </Section>

      <Section title="Attack success end to end (guardrails off → on)" source={end_to_end.source}>
        <div className="table-wrap">
          <table className="static">
            <thead>
              <tr>
                <th>System prompt</th>
                <th className="num">Guardrails off</th>
                <th className="num">Guardrails on</th>
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
          <code>v1-degraded</code> is a deliberately weakened prompt, to show what the guardrails
          catch when the model alone doesn't.
        </p>
      </Section>

      <Section title="Cost and latency variants" source={variants.source}>
        <RunTable
          caption="Model routing (golden suite)"
          rows={variants.routing}
          extra={[{ head: "Measured cost", cell: (r) => usd(r.cost_usd, 2) }]}
        />
        <RunTable
          caption="Prompt caching (Sonnet 5.5, smoke suite, sequential)"
          rows={variants.caching}
          extra={[
            { head: "Cost", cell: (r) => usd(r.cost_usd, 3) },
            { head: "Latency p50", cell: (r) => secs(r.latency_p50_ms) },
            { head: "First text p50", cell: (r) => secs(r.ttft_p50_ms) },
          ]}
        />
        <RunTable
          caption="Context trimming (long conversations)"
          rows={variants.trimming}
          extra={[
            { head: "Input tokens", cell: (r) => (r.input_tokens ?? 0).toLocaleString() },
            { head: "Measured cost", cell: (r) => usd(r.cost_usd, 3) },
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
            <th>Variant</th>
            <th>Pass rate</th>
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
