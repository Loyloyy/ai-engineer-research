import type { DelegateEvent } from "../types";

// The orchestrator decisions: which subagent the lead delegated to, with the instruction it was given.
export default function SubagentTree({ delegations }: { delegations: DelegateEvent[] }) {
  if (delegations.length === 0)
    return <p className="muted">No delegations yet (multi-agent runs show the lead's hand-offs here).</p>;
  return (
    <ul className="subagents">
      {delegations.map((d, i) => (
        <li key={i}>
          <div className="sa-name">→ {d.subagent}</div>
          <div className="sa-instr muted">{d.instruction}</div>
        </li>
      ))}
    </ul>
  );
}
