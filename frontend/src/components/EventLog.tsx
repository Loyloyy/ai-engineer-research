import type { LogEntry } from "../useEventStream";

// The technical event feed: tool calls (+ args) and LLM calls, newest first.
export default function EventLog({ log }: { log: LogEntry[] }) {
  if (log.length === 0) return <p className="muted">No events yet.</p>;
  return (
    <ul className="eventlog">
      {[...log].reverse().map((e, i) => (
        <li key={i} className={`ev ev-${e.kind}`}>
          <span className="tag">{e.kind}</span>
          <span className="txt">{e.text}</span>
        </li>
      ))}
    </ul>
  );
}
