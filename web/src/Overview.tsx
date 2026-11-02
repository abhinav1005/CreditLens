import { useEffect, useState } from "react";

// The landing page: plain-language conclusions, one simple chart each. All of the text and
// numbers come from the `story` part of /dashboard.json, built by evals/story.py, so the
// README and this page say the same thing and nothing here is typed in by hand.

interface BarsChart {
  type: "bars";
  title: string;
  rows: { label: string; value: number; display: string; highlight: boolean }[];
}

interface DotsChart {
  type: "dots";
  title: string;
  axis_min: number;
  axis_max: number;
  points: { label: string; value: number; display: string }[];
}

interface BeforeAfterChart {
  type: "before_after";
  title: string;
  before_label: string;
  after_label: string;
  rows: { label: string; before: number; after: number; n: number }[];
}

type Chart = BarsChart | DotsChart | BeforeAfterChart;

interface Finding {
  id: string;
  headline: string;
  meaning: string;
  fine_print: string;
  charts: Chart[];
}

interface Story {
  title: string;
  summary: string;
  steps: { title: string; text: string }[];
  findings: Finding[];
  gaps: string[];
}

function Bars({ chart }: { chart: BarsChart }) {
  return (
    <figure className="viz">
      <figcaption className="viz-title">{chart.title}</figcaption>
      {chart.rows.map((r) => (
        <div className="viz-row" key={r.label} title={`${r.label}: ${r.display}`}>
          <span>{r.label}</span>
          <span className="viz-bar">
            <span
              className={r.highlight ? "viz-fill highlight" : "viz-fill"}
              style={{ width: `${r.value * 75}%` }}
            />
            <span className="viz-value">{r.display}</span>
          </span>
        </div>
      ))}
    </figure>
  );
}

function Dots({ chart }: { chart: DotsChart }) {
  const height = (value: number) =>
    `${(100 * (value - chart.axis_min)) / (chart.axis_max - chart.axis_min)}%`;
  return (
    <figure className="viz">
      <figcaption className="viz-title">{chart.title}</figcaption>
      <div className="viz-plot">
        {chart.points.map((p) => (
          <div className="viz-column" key={p.label} title={`${p.label}: ${p.display}`}>
            <span className="viz-dot" style={{ bottom: height(p.value) }} />
            <span className="viz-dot-label" style={{ bottom: height(p.value) }}>
              {p.display}
            </span>
          </div>
        ))}
      </div>
      <div className="viz-axis">
        {chart.points.map((p) => (
          <span key={p.label}>{p.label}</span>
        ))}
      </div>
    </figure>
  );
}

function BeforeAfter({ chart }: { chart: BeforeAfterChart }) {
  return (
    <figure className="viz">
      <figcaption className="viz-title">{chart.title}</figcaption>
      <div className="versus">
        {chart.rows.map((r) => (
          <div className="versus-card" key={r.label}>
            <div className="versus-label">{r.label}</div>
            <div className="versus-numbers">
              <span>
                <span className="versus-number">{r.before}</span>
                <span className="versus-caption">
                  of {r.n}, {chart.before_label.toLowerCase()}
                </span>
              </span>
              <span className="versus-arrow" aria-hidden="true">
                →
              </span>
              <span>
                <span className="versus-number">{r.after}</span>
                <span className="versus-caption">
                  of {r.n}, {chart.after_label.toLowerCase()}
                </span>
              </span>
            </div>
          </div>
        ))}
      </div>
    </figure>
  );
}

function ChartView({ chart }: { chart: Chart }) {
  if (chart.type === "bars") return <Bars chart={chart} />;
  if (chart.type === "dots") return <Dots chart={chart} />;
  return <BeforeAfter chart={chart} />;
}

export default function Overview() {
  const [story, setStory] = useState<Story | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/dashboard.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<{ story: Story }>;
      })
      .then((data) => setStory(data.story))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error)
    return (
      <p className="error">
        Can't load the results ({error}). Run <code>uv run python -m evals dashboard</code>.
      </p>
    );
  if (!story) return <p className="muted">Loading…</p>;

  return (
    <div className="overview">
      <section className="hero">
        <h2>{story.title}</h2>
        <p>{story.summary}</p>
        <div className="hero-links">
          <a href="#chat">Try the chatbot</a>
          <a href="#evals">See the exam answers</a>
        </div>
      </section>

      <ol className="steps">
        {story.steps.map((s) => (
          <li key={s.title}>
            <strong>{s.title}</strong>
            {s.text}
          </li>
        ))}
      </ol>

      <h3 className="group">What the exam found</h3>
      {story.findings.map((f) => (
        <article className="finding" key={f.id}>
          <h4>{f.headline}</h4>
          <p>{f.meaning}</p>
          {f.charts.length > 0 && (
            <div className="small-multiples">
              {f.charts.map((c) => (
                <ChartView chart={c} key={c.title} />
              ))}
            </div>
          )}
          <details>
            <summary>Fine print</summary>
            <p>{f.fine_print}</p>
          </details>
        </article>
      ))}

      <section>
        <h3 className="group">Still to do</h3>
        <ul className="todo">
          {story.gaps.map((g) => (
            <li key={g}>{g}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
