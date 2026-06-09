import type { ReferenceRepo } from "../types";

// The enriched reference repos with stars / reproducibility / code_gathered badges (from _finalize).
export default function ReferenceRepos({ repos }: { repos: ReferenceRepo[] }) {
  if (!repos || repos.length === 0) return null;
  return (
    <div className="repos">
      <h3>Reference implementations</h3>
      {repos.map((r, i) => (
        <div className="repo" key={i}>
          <div className="repo-head">
            <a href={r.url} target="_blank" rel="noreferrer">
              {r.name}
            </a>
            <span className="badges">
              {r.stars != null && <span className="badge star">★ {r.stars.toLocaleString()}</span>}
              {r.license && <span className="badge">{r.license}</span>}
              {r.reproducibility && (
                <span className={`badge repro repro-${r.reproducibility.toLowerCase()}`}>
                  repro: {r.reproducibility}
                </span>
              )}
              {r.code_gathered && <span className="badge code">code ✓</span>}
              {r.archived && <span className="badge archived">archived</span>}
            </span>
          </div>
          <div className="muted">{r.why_relevant}</div>
          {r.last_commit && <div className="muted small">last commit {r.last_commit}</div>}
        </div>
      ))}
    </div>
  );
}
