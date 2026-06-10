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
import FetchSummary from "./FetchSummary";
import Accordion from "./Accordion";
import Loading from "./Loading";
import Stepper from "./Stepper";

interface Props {
  runId: string;
  mode: "lean" | "multi-agent";
  live: boolean;
  onBack: () => void;
}

// Single-page run view (no tabs): a live diagram + delegations band on top, the report below, and the
// technical detail (fetch ledger, event log, files) tucked into collapsed accordions.
export default function RunView({ runId, mode, live, onBack }: Props) {
  const s = useEventStream(live ? runId : null);
  const [detail, setDetail] = useState<RunDetail | null>(null);

  // Load the polished artifact: immediately for a historical run, and once a live run finishes.
  const finished = !live || s.done != null;
  useEffect(() => {
    if (finished) api.runDetail(runId).then(setDetail).catch(() => setDetail(null));
  }, [runId, finished]);

  const report = s.report || detail?.artifact?.report_markdown || "";
  const repos = detail?.artifact?.reference_repos || [];
  const running = live && !s.done;
  const tokens = s.tokens.prompt + s.tokens.completion;

  return (
    <div className="runview step-enter">
      {live && <Stepper step={2} />}
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
            <Loading />
          </span>
        ) : (
          <span className="status-line">{s.done?.status || "finished"}</span>
        )}
        {detail?.langfuse_host && (
          <a className="link langfuse" href={detail.langfuse_host} target="_blank" rel="noreferrer">
            ↗ Langfuse{detail.langfuse_session_id ? ` (${detail.langfuse_session_id})` : ""}
          </a>
        )}
        {s.error && <span className="error">{s.error}</span>}
      </header>

      {/* Top band: the live pipeline + the lead's delegations side by side. */}
      <div className="run-band two-col">
        <div className="col">
          <Diagram mode={mode} leanStage={s.leanStage} running={s.running} engaged={s.engaged} />
        </div>
        <div className="col">
          <h3>Subagent delegations</h3>
          <SubagentTree delegations={s.delegations} />
        </div>
      </div>

      <div className="panel overview">
        <div className="counters">
          <span className="ok">✓ {s.coverage?.fetched_ok ?? 0}</span>
          <span className="bad">✗ {s.coverage?.blocked_or_failed ?? 0}</span>
          <span className="muted">tokens ~{tokens.toLocaleString()}</span>
        </div>
        <FetchSummary urls={s.urls} />
        <ReferenceRepos repos={repos} />
        <h3>Report</h3>
        {report ? <ReportView markdown={report} /> : running ? <Loading label="awaiting report…" /> : <p className="muted">No report.</p>}
      </div>

      <div className="accordions">
        <Accordion title="Fetch ledger" count={s.urls.length}>
          <LedgerTable urls={s.urls} coverage={s.coverage} />
        </Accordion>
        <Accordion title="Event log" count={s.log.length}>
          <EventLog log={s.log} />
        </Accordion>
        {detail?.files && detail.files.length > 0 && (
          <Accordion title="Run files" count={detail.files.length}>
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
          </Accordion>
        )}
        {s.files?.comparison && (
          <Accordion title="comparison.md">
            <ReportView markdown={s.files.comparison} />
          </Accordion>
        )}
      </div>
    </div>
  );
}
