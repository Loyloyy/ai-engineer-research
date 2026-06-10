import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunSummary } from "../types";

// Chatbot-style left sidebar: brand + New run + past-runs list (a "resumable" pill flags truncated runs;
// open one and use its Resume banner) + a footer with Settings and a theme toggle. Collapsible (state
// owned by App, persisted to localStorage).
interface Props {
  open: boolean;
  theme: "light" | "dark";
  activeRunId: string | null;
  refreshKey: string; // bump to refetch the list (e.g. on navigation)
  onToggle: () => void;
  onToggleTheme: () => void;
  onNewRun: () => void;
  onOpenRun: (id: string) => void;
  onSettings: () => void;
}

export default function Sidebar(p: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.listRuns().then((r) => setRuns(r.runs)).catch((e) => setErr(String(e)));
  }, [p.refreshKey]);

  if (!p.open) {
    return (
      <button className="sb-open" onClick={p.onToggle} title="Open sidebar" aria-label="Open sidebar">
        ☰
      </button>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sb-head">
        <h1 className="brand" onClick={p.onNewRun}>Deep Researcher</h1>
        <button className="sb-collapse" onClick={p.onToggle} title="Collapse sidebar" aria-label="Collapse sidebar">
          «
        </button>
      </div>

      <button className="sb-new" onClick={p.onNewRun}>＋ New run</button>

      <div className="sb-runs">
        <div className="sb-section">Past runs</div>
        {err && <p className="error small">{err}</p>}
        {runs.length === 0 && !err && <p className="muted small">No runs yet.</p>}
        <ul>
          {runs.map((r) => (
            <li key={r.id} className={r.id === p.activeRunId ? "active" : ""}>
              <button className="sb-run" onClick={() => p.onOpenRun(r.id)} title={r.topic || r.id}>
                <span className="sb-run-topic">{r.topic || r.id}</span>
                <span className="sb-run-meta">
                  {r.mode && <span className={`pill ${r.mode}`}>{r.mode}</span>}
                  {r.resumable && <span className="pill warn">resumable</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="sb-footer">
        <button className="sb-foot-btn" onClick={p.onSettings}>⚙ Settings</button>
        <button className="sb-foot-btn" onClick={p.onToggleTheme}>
          {p.theme === "dark" ? "☀ Light" : "🌙 Dark"}
        </button>
      </div>
    </aside>
  );
}
