import { useEffect, useState } from "react";
import { api } from "../api";
import { useEventStream } from "../useEventStream";
import type { RunDetail } from "../types";
import Diagram from "./Diagram";
import ReportView from "./ReportView";
import LedgerTable from "./LedgerTable";
import EventLog from "./EventLog";
import SubagentTree from "./SubagentTree";
import ReferenceRepos from "./ReferenceRepos";

interface Props {
  runId: string;
  mode: "lean" | "multi-agent";
  live: boolean;
  onBack: () => void;
}

export default function RunView({ runId, mode, live, onBack }: Props) {
  const s = useEventStream(live ? runId : null);
  const [tab, setTab] = useState<"overview" | "technical">("overview");
  const [detail, setDetail] = useState<RunDetail | null>(null);

  // Load the polished artifact: immediately for a historical run, and once a live run finishes.
  const finished = !live || s.done != null;
  useEffect(() => {
    if (finished) api.runDetail(runId).then(setDetail).catch(() => setDetail(null));
  }, [runId, finished]);

  const report = s.report || detail?.artifact?.report_markdown || "";
  const repos = detail?.artifact?.reference_repos || [];
  const running = live && !s.done;

  return (
    <div className="runview">
      <header className="runhead">
        <button className="link" onClick={onBack}>
          ← back
        </button>
        <code>{runId}</code>
        <span className={`pill ${mode}`}>{mode}</span>
        {running ? (
          <span className="status-line">
            <span className={`dot ${s.connected ? "live" : "off"}`} />
            {s.status || "working…"} · {s.elapsed.toFixed(0)}s
          </span>
        ) : (
          <span className="status-line">{s.done?.status || "finished"}</span>
        )}
        {s.error && <span className="error">{s.error}</span>}
      </header>

      <Diagram mode={mode} leanStage={s.leanStage} lastNode={s.lastNode} engaged={s.engaged} />

      <nav className="tabs">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>
          Overview
        </button>
        <button className={tab === "technical" ? "active" : ""} onClick={() => setTab("technical")}>
          Technical
        </button>
      </nav>

      {tab === "overview" ? (
        <div className="panel overview">
          <div className="counters">
            <span className="ok">✓ {s.coverage?.fetched_ok ?? 0}</span>
            <span className="bad">✗ {s.coverage?.blocked_or_failed ?? 0}</span>
            <span className="muted">tokens ~{(s.tokens.prompt + s.tokens.completion).toLocaleString()}</span>
          </div>
          <ReferenceRepos repos={repos} />
          <h3>Report</h3>
          <ReportView markdown={report} />
        </div>
      ) : (
        <div className="panel technical two-col">
          <div className="col">
            <h3>Fetch ledger</h3>
            <LedgerTable urls={s.urls} coverage={s.coverage} />
            <h3>Subagent delegations</h3>
            <SubagentTree delegations={s.delegations} />
            {detail?.langfuse_host && (
              <p>
                <a className="link" href={detail.langfuse_host} target="_blank" rel="noreferrer">
                  Open Langfuse (session {detail.langfuse_session_id})
                </a>
              </p>
            )}
          </div>
          <div className="col">
            <h3>Event log</h3>
            <EventLog log={s.log} />
            {detail?.files && detail.files.length > 0 && (
              <>
                <h3>Run files</h3>
                <ul className="files">
                  {detail.files.map((f) => (
                    <li key={f.name}>
                      <a href={api.fileUrl(runId, f.name)} target="_blank" rel="noreferrer">
                        {f.name}
                      </a>
                      <span className="muted small"> {f.bytes}b</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {s.files?.comparison && (
              <>
                <h3>comparison.md</h3>
                <ReportView markdown={s.files.comparison} />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
