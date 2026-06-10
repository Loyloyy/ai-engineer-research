// Three jumping dots — the "I'm working" feedback so the UI never looks idle while waiting (clarify
// fetch, run startup, and the run view before the first SSE event lands). Animation is pure CSS.
export default function Loading({ label }: { label?: string }) {
  return (
    <span className="loading">
      <span className="loading-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {label && <span className="loading-label">{label}</span>}
    </span>
  );
}
