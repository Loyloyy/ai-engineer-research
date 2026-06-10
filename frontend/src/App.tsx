import { useEffect, useState } from "react";
import { api } from "./api";
import type { ActiveRun, RunSummary } from "./types";
import RunForm from "./components/RunForm";
import RunView from "./components/RunView";
import Sidebar from "./components/Sidebar";
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
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("aer-theme") as "light" | "dark") || "light"
  );
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem("aer-sidebar") !== "closed");

  // Theme lives on <html> so body (outside .app) picks up the CSS variables too.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("aer-theme", theme);
  }, [theme]);
  useEffect(() => {
    localStorage.setItem("aer-sidebar", sidebarOpen ? "open" : "closed");
  }, [sidebarOpen]);

  // Track the in-progress run so the sidebar can mark it live and the home banner can offer reconnect.
  useEffect(() => {
    api.activeRun().then((r) => setActive(r.active)).catch(() => setActive(null));
  }, [view]);

  function openLive(runId: string, multi: boolean) {
    setView({ name: "run", runId, mode: multi ? "multi-agent" : "lean", live: true });
  }
  function openHistorical(runId: string) {
    const mode = runId.endsWith("-m") ? "multi-agent" : "lean";
    setView({ name: "run", runId, mode, live: active?.run_id === runId });
  }
  async function resumeRun(run: RunSummary) {
    try {
      const { run_id } = await api.resumeRun(run.id);
      openLive(run_id, run.mode === "multi-agent");
    } catch (e) {
      alert(`Could not resume: ${e}`);
    }
  }

  const refreshKey = `${view.name}:${view.name === "run" ? view.runId : ""}`;

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        theme={theme}
        activeRunId={active?.run_id ?? null}
        refreshKey={refreshKey}
        onToggle={() => setSidebarOpen((v) => !v)}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        onNewRun={() => setView({ name: "home" })}
        onOpenRun={openHistorical}
        onSettings={() => setView({ name: "settings" })}
      />

      <main className={`main${sidebarOpen ? "" : " full"}`}>
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
            <RunForm onStarted={(id, multi) => openLive(id, multi)} />
          </div>
        )}

        {view.name === "run" && (
          <RunView
            runId={view.runId}
            mode={view.mode}
            live={view.live}
            onResume={() => resumeRun({ id: view.runId, mode: view.mode } as RunSummary)}
          />
        )}

        {view.name === "settings" && (
          <div className="settings">
            <h2 className="settings-title">Settings</h2>
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
