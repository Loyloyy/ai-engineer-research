import type { UrlEvent } from "../types";

// A visual roll-up of which sites the run actually reached vs. which were blocked/failed — derived
// entirely from the `url` events already streamed into RunState (host + ok + outcome). Fills in live and
// is complete at run end. Hosts are de-duped; a host counts as reached if ANY of its attempts succeeded.
export default function FetchSummary({ urls }: { urls: UrlEvent[] }) {
  if (urls.length === 0) return null;

  const byHost = new Map<string, { ok: boolean; outcome: string }>();
  for (const u of urls) {
    const host = u.host || "(unknown)";
    const prev = byHost.get(host);
    byHost.set(host, { ok: u.ok || (prev?.ok ?? false), outcome: u.ok ? "ok" : u.outcome || prev?.outcome || "" });
  }

  const reached = [...byHost].filter(([, v]) => v.ok).map(([h]) => h).sort();
  const blocked = [...byHost].filter(([, v]) => !v.ok).map(([h, v]) => ({ host: h, outcome: v.outcome })).sort((a, b) => a.host.localeCompare(b.host));

  return (
    <div className="fetch-summary">
      <div className="fs-group">
        <div className="fs-head ok">✓ Reached <span className="fs-n">{reached.length}</span></div>
        <div className="fs-chips">
          {reached.length === 0 && <span className="muted small">none yet</span>}
          {reached.map((h) => (
            <span key={h} className="fs-chip ok">{h}</span>
          ))}
        </div>
      </div>
      <div className="fs-group">
        <div className="fs-head bad">✗ Blocked / failed <span className="fs-n">{blocked.length}</span></div>
        <div className="fs-chips">
          {blocked.length === 0 && <span className="muted small">none</span>}
          {blocked.map((b) => (
            <span key={b.host} className="fs-chip bad" title={b.outcome}>
              {b.host}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
