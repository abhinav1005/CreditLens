import { useEffect, useState } from "react";

import Chat from "./Chat";
import Dashboard from "./Dashboard";
import Evals from "./Evals";
import Label from "./Label";
import Transcripts from "./Transcripts";

// Views are picked by the URL hash (#chat, #transcripts/<id>, ...), so no router library.
const VIEWS = [
  { id: "chat", label: "Chat" },
  { id: "transcripts", label: "Transcripts" },
  { id: "evals", label: "Evals" },
  { id: "label", label: "Label" },
  { id: "dashboard", label: "Dashboard" },
] as const;

function currentHash(): string {
  return window.location.hash.slice(1) || "chat";
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
