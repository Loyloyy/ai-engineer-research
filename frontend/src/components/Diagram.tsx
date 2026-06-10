// A lightweight CSS/flex pipeline diagram — no heavy graph lib (keeps the committed dist small, since
// the server's egress blocks npm so dist ships in-repo). Lean = a scope→…→report stepper; multi-agent =
// a Lead box feeding the fixed subagents. Nodes carry FRIENDLY names + a one-line role so a non-technical
// viewer can follow what each part does. Connectors are a pure-CSS org-chart (see styles.css).

// Friendly identities for the multi-agent roster (item 1: legibility for non-technical viewers).
const AGENTS: Record<string, { name: string; role: string }> = {
  lead: { name: "Research Director", role: "Plans the work, hands out jobs, then reconciles findings and writes the report" },
  "code-scout": { name: "Code Finder", role: "Hunts down real, working code on GitHub & Hugging Face" },
  landscape: { name: "Market Mapper", role: "Finds the competing tools and compares them" },
  maturity: { name: "Reality Checker", role: "Digs into bugs, limits and production-readiness" },
  "focused-investigator": { name: "Specialist", role: "Called in on demand for one specific deep-dive" },
};

// Friendlier labels for the lean stepper stages.
const LEAN: { id: string; label: string }[] = [
  { id: "scope", label: "Plan" },
  { id: "search", label: "Search" },
  { id: "fetch", label: "Read" },
  { id: "reflect", label: "Reflect" },
  { id: "report", label: "Report" },
];
const SUBAGENTS = ["code-scout", "landscape", "maturity", "focused-investigator"];
const ON_DEMAND = new Set(["focused-investigator"]);

interface Props {
  mode: "lean" | "multi-agent";
  leanStage: string;
  running: string[]; // subagents currently executing → blue
  engaged: string[]; // subagents that have run → green
}

function Node({ id, state }: { id: string; state: string }) {
  const meta = AGENTS[id];
  const hint = ON_DEMAND.has(id) ? "on demand" : undefined;
  return (
    <div className={`node node-${state}`} title={meta ? `${id} — ${meta.role}` : id}>
      <span className="node-name">{meta ? meta.name : id}</span>
      {meta && <span className="node-tech">{id}</span>}
      {meta && <span className="node-role">{meta.role}</span>}
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
      <span className="legend-item muted small">Specialist runs only when a gap needs it</span>
    </div>
  );
}

export default function Diagram(p: Props) {
  if (p.mode === "lean") {
    const active = LEAN.findIndex((s) => s.id === p.leanStage);
    return (
      <div className="diagram lean">
        {LEAN.map((s, i) => (
          <div key={s.id} className="step">
            <div className={`node node-${i === active ? "active" : i < active ? "done" : "idle"}`}>
              <span className="node-name">{s.label}</span>
            </div>
            {i < LEAN.length - 1 && <span className="arrow">→</span>}
          </div>
        ))}
      </div>
    );
  }

  const nodeState = (n: string) => {
    // Lead is blue while it's orchestrating (no subagent running), green while waiting on subagents.
    if (n === "lead") return p.running.length ? "engaged" : "active";
    if (p.running.includes(n)) return "active"; // currently executing → blue
    if (p.engaged.includes(n)) return "engaged"; // has run → green
    return "idle";
  };

  return (
    <div className="diagram multi">
      <Node id="lead" state={nodeState("lead")} />
      <span className="stem" />
      <div className="fanout">
        {SUBAGENTS.map((s) => (
          <div key={s} className="branch">
            <Node id={s} state={nodeState(s)} />
          </div>
        ))}
      </div>
      <Legend />
    </div>
  );
}
