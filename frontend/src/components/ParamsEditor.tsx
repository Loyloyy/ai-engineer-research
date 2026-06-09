import { useEffect, useState } from "react";
import { api } from "../api";

// Edit the non-secret pipeline knobs (config/pipeline.yaml). NEVER .env (model endpoints/keys stay
// server-side). The backend validates against an allow-list.
export default function ParamsEditor() {
  const [params, setParams] = useState<Record<string, any> | null>(null);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .getParams()
      .then((r) => {
        setParams(r.params);
        setText(JSON.stringify(r.params, null, 2));
      })
      .catch((e) => setErr(String(e)));
  }, []);

  async function save() {
    setErr("");
    setMsg("");
    let parsed: Record<string, any>;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setErr("Invalid JSON: " + e);
      return;
    }
    try {
      const r = await api.putParams(parsed);
      setParams(r.params);
      setText(JSON.stringify(r.params, null, 2));
      setMsg("Saved to config/pipeline.yaml.");
    } catch (e) {
      setErr(String(e));
    }
  }

  if (err && params === null) return <p className="muted">Param editing unavailable ({err}).</p>;

  return (
    <div className="card editor">
      <h2>Pipeline parameters</h2>
      <p className="muted">
        Non-secret knobs from <code>config/pipeline.yaml</code>. Model endpoints/keys live in <code>.env</code>{" "}
        and are not editable here.
      </p>
      <textarea className="mono" rows={16} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="actions">
        <button onClick={save}>Save</button>
      </div>
      {msg && <p className="ok-msg">{msg}</p>}
      {err && <p className="error">{err}</p>}
    </div>
  );
}
