import { useEffect, useState } from "react";

import Chat from "./Chat";
import Dashboard from "./Dashboard";
import Evals from "./Evals";
import Label from "./Label";
import Overview from "./Overview";
import Transcripts from "./Transcripts";

// Views are picked by the URL hash (#chat, #transcripts/<id>, ...), so no router library.
const VIEWS = [
  { id: "overview", label: "Overview", intro: "" },
  { id: "chat", label: "Try it", intro: "Chat with the assistant about a made-up person." },
  {
    id: "evals",
    label: "Test runs",
    intro: "Every saved exam: open one to see each question, the answer and its mark.",
  },
  {
    id: "transcripts",
    label: "Conversations",
    intro: "Saved chats, and what the safety checks did in each one.",
  },
  { id: "dashboard", label: "All data", intro: "Every number behind the Overview page." },
  { id: "label", label: "Label", intro: "Mark answers by hand, to check the AI marker." },
] as const;

function currentHash(): string {
  return window.location.hash.slice(1) || "overview";
}

export default function App() {
  const [hash, setHash] = useState(currentHash);

  useEffect(() => {
    const onChange = () => setHash(currentHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const [view, ...params] = hash.split("/");
  const param = params[0];
  const intro = VIEWS.find((v) => v.id === view)?.intro;

  return (
    <div className="app">
      <header>
        <h1>CreditLens</h1>
        <nav>
          {VIEWS.map((v) => (
            <a key={v.id} href={`#${v.id}`} className={view === v.id ? "active" : ""}>
              {v.label}
            </a>
          ))}
        </nav>
      </header>
      <p className="disclaimer">
        Educational demo on synthetic data. Not financial advice. The compliance policy is a demo
        policy, not legal compliance.
      </p>
      <main>
        {intro && <p className="view-intro">{intro}</p>}
        {view === "overview" && <Overview />}
        {view === "chat" && <Chat />}
        {view === "transcripts" && <Transcripts selectedId={param ?? null} />}
        {view === "evals" && <Evals params={params} />}
        {view === "label" && <Label />}
        {view === "dashboard" && <Dashboard />}
        {!VIEWS.some((v) => v.id === view) && <p>Unknown view.</p>}
      </main>
    </div>
  );
}
