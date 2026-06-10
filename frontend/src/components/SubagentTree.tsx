import type { DelegateEvent } from "../types";
import { agentName } from "../agents";

// The Director's hand-offs: which helper it tapped + the instruction it wrote for that helper this run.
export default function SubagentTree({ delegations }: { delegations: DelegateEvent[] }) {
  if (delegations.length === 0)
    return <p className="muted">No instructions yet (these appear as the Research Director hands out jobs).</p>;
  return (
    <ul className="subagents">
      {delegations.map((d, i) => (
        <li key={i}>
          <div className="sa-name">→ {agentName(d.subagent)} <span className="muted small">({d.subagent})</span></div>
          <div className="sa-instr muted">{d.instruction}</div>
        </li>
      ))}
    </ul>
  );
}
