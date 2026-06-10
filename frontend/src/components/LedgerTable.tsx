import type { UrlEvent } from "../types";

// The live fetch ledger: url · host · ✓/✗ · outcome. (The reachable/blocked counts live in the
// FetchSummary now, so the two technical tables line up at the same level inside one accordion.)
export default function LedgerTable({ urls }: { urls: UrlEvent[] }) {
  return (
    <div className="ledger">
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
