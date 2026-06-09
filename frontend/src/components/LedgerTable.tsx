import type { CoverageEvent, UrlEvent } from "../types";

// The live fetch ledger: url · host · ✓/✗ · outcome, plus the reachable counter from coverage.
export default function LedgerTable({ urls, coverage }: { urls: UrlEvent[]; coverage: CoverageEvent | null }) {
  return (
    <div className="ledger">
      <div className="counter">
        <span className="ok">✓ {coverage?.fetched_ok ?? 0} reachable</span>
        <span className="bad">✗ {coverage?.blocked_or_failed ?? 0} blocked/failed</span>
        <span className="muted">{coverage?.fetch_attempts ?? urls.length} attempts</span>
      </div>
      <table>
        <thead>
          <tr>
            <th></th>
            <th>host</th>
            <th>url</th>
            <th>outcome</th>
          </tr>
        </thead>
        <tbody>
          {[...urls].reverse().map((u, i) => (
            <tr key={i}>
              <td>{u.ok ? "✓" : "✗"}</td>
              <td className="host">{u.host}</td>
              <td className="url">
                <a href={u.url} target="_blank" rel="noreferrer">
                  {u.url}
                </a>
              </td>
              <td className="muted">{u.outcome}</td>
            </tr>
          ))}
          {urls.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No fetches yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
