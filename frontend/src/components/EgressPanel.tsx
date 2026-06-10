import { useEffect, useState } from "react";
import { api } from "../api";

// Read-only view of the preferred-source allowlist (domains.reachable_domains()). Public dev domains
// only — no .env, no internal hosts — so it's safe to surface. Lets a demo audience see exactly which
// sources the agent will try to fetch from in the restricted-network deploy.
export default function EgressPanel() {
  const [domains, setDomains] = useState<string[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .getEgress()
      .then((r) => setDomains(r.domains))
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="card editor">
      <h2>Egress allowlist</h2>
      <p className="muted small">
        Preferred-source domains the agent will fetch from (read-only). Other hosts are fast-skipped in
        this restricted-network deploy. Public domains only — set via <code>AER_REACHABLE_DOMAINS</code>.
      </p>
      {err && <p className="error">{err}</p>}
      {domains && (
        <div className="egress-chips">
          {domains.map((d) => (
            <span key={d} className="badge">{d}</span>
          ))}
        </div>
      )}
    </div>
  );
}
