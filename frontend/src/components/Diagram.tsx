// A lightweight CSS/flex pipeline diagram — no heavy graph lib (keeps the committed dist small, since
// the server's egress blocks npm so dist ships in-repo). Lean = a scope→…→report stepper; multi-agent =
// a Lead box feeding the fixed subagents, lit up as the lead delegates. Connectors are a pure-CSS
// org-chart (stem + rail + per-branch drop) drawn via .stem/.branch borders in styles.css.

const LEAN_STAGES = ["scope", "search", "fetch", "reflect", "report"];
// The three fixed subagents always run; focused-investigator is spawned on demand by the lead during
// REFLECT only for a genuine topic-specific gap, so it stays idle on most runs (by design).
const SUBAGENTS = ["code-scout", "landscape", "maturity", "focused-investigator"];
const ON_DEMAND = new Set(["focused-investigator"]);

interface Props {
  mode: "lean" | "multi-agent";
  leanStage: string;
  running: string[]; // subagents currently executing → blue
  engaged: string[]; // subagents that have run → green
}

function Node({ label, state, hint }: { label: string; state: string; hint?: string }) {
  return (
    <div className={`node node-${state}`}>
      {label}
      {hint && <span className="node-hint">{hint}</span>}
    </div>
  );
}

function Legend() {
  return (
    <div className="legend">
      <span className="legend-item"><span className="swatch idle" /> idle</span>
      <span className="legend-item"><span className="swatch active" /> running</span>
      <span className="legend-item"><span className="swatch engaged" /> done</span>
      <span className="legend-item muted small">focused-investigator runs on demand</span>
    </div>
  );
}

export default function Diagram(p: Props) {
  if (p.mode === "lean") {
    const active = LEAN_STAGES.indexOf(p.leanStage);
    return (
      <div className="diagram lean">
        {LEAN_STAGES.map((s, i) => (
          <div key={s} className="step">
            <Node label={s} state={i === active ? "active" : i < active ? "done" : "idle"} />
            {i < LEAN_STAGES.length - 1 && <span className="arrow">→</span>}
          </div>
        ))}
      </div>
    );
  }

  const nodeState = (n: string) => {
    // Lead is blue while it's orchestrating (no subagent running — i.e. scoping/reconciling/writing),
    // green while it's waiting on delegated subagents.
    if (n === "lead") return p.running.length ? "engaged" : "active";
    if (p.running.includes(n)) return "active"; // currently executing → blue
    if (p.engaged.includes(n)) return "engaged"; // has run → green
    return "idle";
  };

  return (
    <div className="diagram multi">
      <Node label="Lead" state={nodeState("lead")} />
      <span className="stem" />
      <div className="fanout">
        {SUBAGENTS.map((s) => (
          <div key={s} className="branch">
            <Node label={s} state={nodeState(s)} hint={ON_DEMAND.has(s) ? "on demand" : undefined} />
          </div>
        ))}
      </div>
      <Legend />
    </div>
  );
}
