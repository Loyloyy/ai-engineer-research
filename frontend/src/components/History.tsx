import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunSummary } from "../types";

// Past runs browser: lists artifacts/<id>/, click → open the run (replays the report snapshot + detail).
export default function History({ onOpen }: { onOpen: (id: string) => void }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .listRuns()
      .then((r) => setRuns(r.runs))
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="card history">
      <h2>Past runs</h2>
      {err && <p className="error">{err}</p>}
      {runs.length === 0 && !err && <p className="muted">No runs yet.</p>}
      <ul>
        {runs.map((r) => (
          <li key={r.id}>
            <button className="link" onClick={() => onOpen(r.id)}>
              {r.id}
            </button>
            {r.mode && <span className={`pill ${r.mode}`}>{r.mode}</span>}
            {r.resumable && <span className="pill warn">resumable</span>}
            <div className="muted topic">{r.topic}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
