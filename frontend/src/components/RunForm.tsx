import { useState } from "react";
import { api, ApiError } from "../api";
import Stepper from "./Stepper";
import Loading from "./Loading";

interface Props {
  onStarted: (runId: string, multiAgent: boolean) => void;
}

// The pre-run scoping form: topic + brief + per-run overrides (multi-agent, thoroughness, seed pages),
// with an optional clarify step (clarify_questions → answers folded into the brief before POST /runs).
export default function RunForm({ onStarted }: Props) {
  const [topic, setTopic] = useState("");
  const [brief, setBrief] = useState("");
  const [seedPages, setSeedPages] = useState("");
  const [multiAgent, setMultiAgent] = useState(false);
  const [thoroughness, setThoroughness] = useState("standard");
  const [questions, setQuestions] = useState<string[] | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const seeds = () =>
    seedPages
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);

  async function doClarify() {
    setErr("");
    setBusy(true);
    try {
      const { questions } = await api.clarify(topic, brief);
      setQuestions(questions);
      setAnswers(questions.map(() => ""));
      if (questions.length === 0) await doStart([]);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doStart(clar: [string, string][]) {
    setErr("");
    setBusy(true);
    try {
      const { run_id } = await api.startRun({
        topic,
        brief,
        seed_pages: seeds().length ? seeds() : null,
        multi_agent: multiAgent,
        thoroughness,
        clarifications: clar.length ? clar : null,
      });
      onStarted(run_id, multiAgent);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409)
        setErr("A run is already active. Only one run can run at a time — view it from history.");
      else setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (questions && questions.length > 0) {
    return (
      <div className="runform-wrap step-enter">
        <Stepper step={1} />
        <div className="card runform">
        <h2>Clarify the scope</h2>
        <p className="muted">Optional — press Enter to skip any. Answers sharpen the brief.</p>
        {questions.map((q, i) => (
          <div className="field" key={i}>
            <label>{q}</label>
            <input
              value={answers[i]}
              onChange={(e) => setAnswers((a) => a.map((v, j) => (j === i ? e.target.value : v)))}
            />
          </div>
        ))}
        <div className="actions">
          <button
            disabled={busy}
            onClick={() => doStart(questions.map((q, i) => [q, answers[i]] as [string, string]))}
          >
            {busy ? <Loading label="Preparing run…" /> : "Start research"}
          </button>
          <button className="ghost" disabled={busy} onClick={() => setQuestions(null)}>
            Back
          </button>
        </div>
        {err && <p className="error">{err}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="runform-wrap step-enter">
      <Stepper step={0} />
      <div className="card runform">
      <h2>New research run</h2>
      <div className="field">
        <label>Topic</label>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. self-hosted RAG over a private wiki" />
      </div>
      <div className="field">
        <label>Brief / context (optional)</label>
        <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={4} />
      </div>
      <div className="field">
        <label>Seed pages (optional — comma/newline separated wiki page ids)</label>
        <textarea value={seedPages} onChange={(e) => setSeedPages(e.target.value)} rows={2} />
      </div>
      <div className="row">
        <label className="checkbox">
          <input type="checkbox" checked={multiAgent} onChange={(e) => setMultiAgent(e.target.checked)} />
          Multi-agent (lead + code-scout / landscape / maturity)
        </label>
        <label className="select">
          Thoroughness
          <select value={thoroughness} onChange={(e) => setThoroughness(e.target.value)}>
            <option value="light">light</option>
            <option value="standard">standard</option>
            <option value="deep">deep</option>
          </select>
        </label>
      </div>
      <div className="actions">
        <button disabled={!topic.trim() || busy} onClick={doClarify}>
          {busy ? <Loading /> : "Clarify & start"}
        </button>
        <button className="ghost" disabled={!topic.trim() || busy} onClick={() => doStart([])}>
          Skip clarify → start
        </button>
      </div>
      {err && <p className="error">{err}</p>}
      </div>
    </div>
  );
}
