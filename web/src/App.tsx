import { useEffect, useState } from "react";

import Chat from "./Chat";

// Views are picked by the URL hash (#chat, #transcripts/<id>, ...), so no router library.
const VIEWS = [{ id: "chat", label: "Chat" }] as const;

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

  const view = hash.split("/")[0];

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
      <main>{view === "chat" ? <Chat /> : <p>Unknown view.</p>}</main>
    </div>
  );
}
