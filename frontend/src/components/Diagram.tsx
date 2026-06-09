// A lightweight CSS/flex pipeline diagram — no heavy graph lib (keeps the committed dist small, since
// the server's egress blocks npm so dist ships in-repo). Lean = a scope→…→report stepper; multi-agent =
// a Lead box feeding the fixed subagents, lit up as the lead delegates.

const LEAN_STAGES = ["scope", "search", "fetch", "reflect", "report"];
const SUBAGENTS = ["code-scout", "landscape", "maturity", "focused-investigator"];

interface Props {
  mode: "lean" | "multi-agent";
  leanStage: string;
  lastNode: string;
  engaged: string[];
}

function Node({ label, state }: { label: string; state: "active" | "done" | "engaged" | "idle" }) {
  return <div className={`node node-${state}`}>{label}</div>;
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

  const nodeState = (n: string) =>
    p.lastNode === n ? "active" : p.engaged.includes(n) || n === "lead" ? "engaged" : "idle";

  return (
    <div className="diagram multi">
      <Node label="Lead" state={nodeState("lead")} />
      <div className="fanout">
        {SUBAGENTS.map((s) => (
          <div key={s} className="branch">
            <span className="connector" />
            <Node label={s} state={nodeState(s)} />
          </div>
        ))}
      </div>
    </div>
  );
}
