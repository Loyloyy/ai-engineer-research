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

interface Props {
  runId: string;
  mode: "lean" | "multi-agent";
  live: boolean;
  onResume: () => void;
}

// Single-page run view: a plain-language phase banner + live diagram + caption on top, the report below,
// and the technical detail (delegations, fetch ledger, event log, files) tucked into collapsed accordions.
export default function RunView({ runId, mode, live, onResume }: Props) {
  const s = useEventStream(live ? runId : null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [stopping, setStopping] = useState(false);

  const finished = !live || s.done != null;
  useEffect(() => {
    if (finished) api.runDetail(runId).then(setDetail).catch(() => setDetail(null));
  }, [runId, finished]);

  const report = s.report || detail?.artifact?.report_markdown || "";
  const repos = detail?.artifact?.reference_repos || [];
  const running = live && !s.done;
  const tokens = s.tokens.prompt + s.tokens.completion;
  const outcome = s.done?.status || (live ? "" : "finished");
  const noReport = finished && !report;

  // Friendly phase banner: live phase while running, "Complete" once a report exists at the end.
  const phaseLabel = report && finished ? "Complete" : s.phase?.label || (running ? "Starting" : "");

  async function doStop() {
    setStopping(true);
    try {
      await api.stopRun(runId);
    } catch (e) {
      alert(`Could not stop: ${e}`);
      setStopping(false);
    }
  }

  return (
    <div className="runview step-enter">
      <header className="runhead">
        <code>{runId}</code>
        <span className={`pill ${mode}`}>{mode}</span>
        {running ? (
          <span className="status-line">
            <span className={`dot ${s.connected ? "live" : "off"}`} />
            {s.status || "working…"} · {s.elapsed.toFixed(0)}s
          </span>
        ) : (
          <span className="status-line">{outcome}</span>
        )}
        {running && (
          <button className="stop-btn" onClick={doStop} disabled={stopping}>
            {stopping ? "Stopping…" : "■ Stop"}
          </button>
        )}
        {detail?.langfuse_host && (
          <a className="link langfuse" href={detail.langfuse_host} target="_blank" rel="noreferrer">
            ↗ Langfuse{detail.langfuse_session_id ? ` (${detail.langfuse_session_id})` : ""}
          </a>
        )}
        {s.error && <span className="error">{s.error}</span>}
      </header>

      {phaseLabel && (
        <div className="phase-banner">
          <span className="phase-label">{phaseLabel}</span>
          {running && <Loading />}
        </div>
      )}

      <Diagram mode={mode} leanStage={s.leanStage} running={s.running} engaged={s.engaged} />

      {running && <div className="caption">{s.status || "Working…"}</div>}

      <div className="panel overview">
        <div className="counters">
          <span className="ok">✓ {s.coverage?.fetched_ok ?? 0} sites read</span>
          <span className="bad">✗ {s.coverage?.blocked_or_failed ?? 0} blocked</span>
          <span className="muted small">~{tokens.toLocaleString()} tokens</span>
          <Deliverables phase={s.phase} />
        </div>

        <FetchSummary urls={s.urls} />

        {noReport ? (
          <div className="card no-report">
            <strong>No report was produced.</strong>{" "}
            <span className="muted">
              This run {outcome === "stopped" ? "was stopped" : "ended early"} before the report was written.
              You can resume it to continue from where it left off.
            </span>
            <div className="actions">
              <button onClick={onResume}>▸ Resume run</button>
            </div>
          </div>
        ) : (
          <>
            <ReferenceRepos repos={repos} />
            <h3>Report</h3>
            {report ? <ReportView markdown={report} /> : <Loading label="awaiting report…" />}
          </>
        )}
      </div>

      <div className="accordions">
        <Accordion title="Subagent delegations" count={s.delegations.length || undefined}>
          <p className="muted small">
            What the Research Director actually asked each helper (generated live for this run).
          </p>
          <SubagentTree delegations={s.delegations} />
        </Accordion>

        <Accordion title="Fetch ledger & Event log">
          <div className="two-col">
            <div className="col">
              <h4>Fetch ledger</h4>
              <LedgerTable urls={s.urls} />
            </div>
            <div className="col">
              <h4>Event log</h4>
              <EventLog log={s.log} />
            </div>
          </div>
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

// Deliverables strip: ticks on as the run produces each artifact (driven by the phase event booleans).
function Deliverables({ phase }: { phase: ReturnType<typeof useEventStream>["phase"] }) {
  if (!phase) return null;
  const items: [string, boolean][] = [
    ["Scope", phase.scope],
    ["Comparison", phase.comparison],
    ["Report", phase.report],
  ];
  return (
    <span className="deliverables">
      {items.map(([label, done]) => (
        <span key={label} className={`deliverable${done ? " done" : ""}`}>
          {done ? "✅" : "▫"} {label}
        </span>
      ))}
    </span>
  );
}
