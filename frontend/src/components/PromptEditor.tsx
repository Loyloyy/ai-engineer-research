import { useEffect, useState } from "react";
import { api, type PromptDetail, type PromptInfo } from "../api";

// Edit the overridable BODY of any lead/subagent/clarify prompt (writes config/prompts/<name>.md).
// The code-kept "always appended" rules are shown READ-ONLY — an override only replaces the body.
export default function PromptEditor() {
  const [list, setList] = useState<PromptInfo[]>([]);
  const [sel, setSel] = useState<string>("");
  const [detail, setDetail] = useState<PromptDetail | null>(null);
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .listPrompts()
      .then((r) => {
        setList(r.prompts);
        if (r.prompts[0]) setSel(r.prompts[0].name);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!sel) return;
    setMsg("");
    api
      .getPrompt(sel)
      .then((d) => {
        setDetail(d);
        setBody(d.body);
      })
      .catch((e) => setErr(String(e)));
  }, [sel]);

  async function save() {
    setErr("");
    setMsg("");
    try {
      await api.putPrompt(sel, body);
      setMsg("Saved. Takes effect on the next run.");
      const d = await api.getPrompt(sel);
      setDetail(d);
    } catch (e) {
      setErr(String(e));
    }
  }

  if (err && list.length === 0)
    return <p className="muted">Prompt editing unavailable ({err}).</p>;

  return (
    <div className="card editor">
      <h2>Prompt editor</h2>
      <div className="row">
        <select value={sel} onChange={(e) => setSel(e.target.value)}>
          {list.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name} {p.has_override ? "•" : ""}
            </option>
          ))}
        </select>
        <button onClick={save} disabled={!sel}>
          Save body
        </button>
      </div>
      <label>Editable body</label>
      <textarea className="mono" rows={16} value={body} onChange={(e) => setBody(e.target.value)} />
      {detail?.appended_readonly && (
        <>
          <label>Always appended (read-only — grounding / mission / required outputs / injected knobs)</label>
          <pre className="readonly">{detail.appended_readonly}</pre>
        </>
      )}
      {msg && <p className="ok-msg">{msg}</p>}
      {err && <p className="error">{err}</p>}
    </div>
  );
}
