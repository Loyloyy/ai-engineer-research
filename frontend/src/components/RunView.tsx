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
import { agentName, friendlyAction } from "../agents";

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
  const [reportOpen, setReportOpen] = useState(true); // open while streaming; force-open on finish

  const finished = !live || s.done != null;
  useEffect(() => {
    if (finished) api.runDetail(runId).then(setDetail).catch(() => setDetail(null));
  }, [runId, finished]);
  useEffect(() => {
    if (finished) setReportOpen(true);
  }, [finished]);

  const report = s.report || detail?.artifact?.report_markdown || "";
  const repos = detail?.artifact?.reference_repos || [];
  const running = live && !s.done;
  const tokens = s.tokens.prompt + s.tokens.completion;
  const outcome = s.done?.status || (live ? "" : "finished");
  const noReport = finished && !report;

  // Friendly phase banner: live phase while running, "Complete" once a report exists at the end.
  const phaseLabel = report && finished ? "Complete" : s.phase?.label || (running ? "Starting" : "");

  // Live caption: WHO is doing WHAT. Actor mirrors the lit node (1 helper running → it; none → the
  // Director orchestrating; many → "Helpers"); lean mode has a single "Researcher".
  const actor =
    mode === "lean"
      ? "Researcher"
      : s.running.length === 1
      ? agentName(s.running[0])
      : s.running.length === 0
      ? "Research Director"
      : "Helpers";
  // Prefer the backend's specific status (carries the query/host); prettify only the generic fallbacks.
  const action =
    s.status && !/^Running /.test(s.status) ? s.status : s.lastTool ? friendlyAction(s.lastTool) : s.status || "Working…";

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

      <Diagram mode={mode} leanStage={s.leanStage} running={s.running} engaged={s.engaged} finished={finished} />

      {running && <div className="caption">{actor} — {action}</div>}

      <div className="panel overview">
        <div className="counters">
          <span className="ok">✓ {s.coverage?.fetched_ok ?? 0} sites read</span>
          <span className="bad">✗ {s.coverage?.blocked_or_failed ?? 0} blocked</span>
          <span className="muted small">~{tokens.toLocaleString()} tokens</span>
          <Deliverables phase={s.phase} />
        </div>
        <FetchSummary urls={s.urls} />
      </div>

      <section className="result-section">
        <div className="section-head">Results</div>
        <div className="accordions">
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
            <Accordion title="Report" open={reportOpen} onToggle={setReportOpen}>
              {report ? <ReportView markdown={report} /> : <Loading label="awaiting report…" />}
            </Accordion>
          )}

          {repos.length > 0 && (
            <Accordion title="Reference implementations" count={repos.length}>
              <ReferenceRepos repos={repos} />
            </Accordion>
          )}

          {s.files?.comparison && (
            <Accordion title="Comparison table">
              <ReportView markdown={s.files.comparison} />
            </Accordion>
          )}
        </div>
      </section>

      <section className="result-section">
        <div className="section-head">Behind the scenes</div>
        <div className="accordions">
          <Accordion title="Director's instructions to helpers" count={s.delegations.length || undefined}>
            <p className="muted small">The custom instruction the Research Director wrote for each helper this run.</p>
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
        </div>
      </section>
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
