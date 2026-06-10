import { useEffect, useState } from "react";
import { api } from "./api";
import type { ActiveRun } from "./types";
import RunForm from "./components/RunForm";
import History from "./components/History";
import RunView from "./components/RunView";
import PromptEditor from "./components/PromptEditor";
import ParamsEditor from "./components/ParamsEditor";
import EgressPanel from "./components/EgressPanel";

type View =
  | { name: "home" }
  | { name: "run"; runId: string; mode: "lean" | "multi-agent"; live: boolean }
  | { name: "settings" };

export default function App() {
  const [view, setView] = useState<View>({ name: "home" });
  const [active, setActive] = useState<ActiveRun | null>(null);
  // Presentation mode: scales up fonts/diagram + hides chrome for a lecture-theatre projector.
  const [present, setPresent] = useState(false);

  // On load (and when returning home), check for an in-progress run so we can offer to reconnect.
  useEffect(() => {
    if (view.name === "home") api.activeRun().then((r) => setActive(r.active)).catch(() => setActive(null));
  }, [view.name]);

  function openLive(runId: string, multi: boolean) {
    setView({ name: "run", runId, mode: multi ? "multi-agent" : "lean", live: true });
  }

  async function openHistorical(runId: string) {
    // Determine mode from the id tag (-m/-l) or the detail; default lean.
    const mode = runId.endsWith("-m") ? "multi-agent" : "lean";
    setView({ name: "run", runId, mode, live: active?.run_id === runId });
  }

  return (
    <div className={`app${present ? " present" : ""}`}>
      <header className="topbar">
        <h1 onClick={() => setView({ name: "home" })} className="brand">
          Deep Researcher <span className="muted">· Stage 2</span>
        </h1>
        <nav>
          <button className={view.name === "home" ? "active" : ""} onClick={() => setView({ name: "home" })}>
            Runs
          </button>
          <button className={view.name === "settings" ? "active" : ""} onClick={() => setView({ name: "settings" })}>
            Prompts & Params
          </button>
          <button
            className={`present-toggle${present ? " active" : ""}`}
            onClick={() => setPresent((v) => !v)}
            title="Toggle presentation mode (larger, projector-friendly)"
          >
            ⛶ Present
          </button>
        </nav>
      </header>

      <main>
        {view.name === "home" && (
          <div className="home">
            {active && active.status === "running" && (
              <div className="card banner">
                <span>
                  A run is in progress: <code>{active.run_id}</code> ({active.elapsed_s.toFixed(0)}s)
                </span>
                <button onClick={() => openLive(active.run_id, active.multi_agent)}>Watch it live</button>
              </div>
            )}
            <div className="two-col">
              <RunForm onStarted={(id, multi) => openLive(id, multi)} />
              <History onOpen={openHistorical} />
            </div>
          </div>
        )}

        {view.name === "run" && (
          <RunView
            runId={view.runId}
            mode={view.mode}
            live={view.live}
            onBack={() => setView({ name: "home" })}
          />
        )}

        {view.name === "settings" && (
          <div className="settings">
            <div className="two-col">
              <PromptEditor />
              <ParamsEditor />
            </div>
            <EgressPanel />
          </div>
        )}
      </main>
    </div>
  );
}
