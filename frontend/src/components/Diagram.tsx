import { useEffect, useMemo, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose" });

const LEAN_STAGES = ["scope", "search", "fetch", "reflect", "report"];
const MULTI_NODES = ["lead", "code-scout", "landscape", "maturity", "focused-investigator"];

// Mermaid node ids can't contain hyphens; map names ↔ safe ids.
const safeId = (n: string) => n.replace(/-/g, "_");

interface Props {
  mode: "lean" | "multi-agent";
  leanStage: string;
  lastNode: string;
  engaged: string[];
}

function buildDef(p: Props): string {
  if (p.mode === "lean") {
    const edges = LEAN_STAGES.map((s) => safeId(s))
      .reduce<string[]>((acc, id, i, arr) => (i ? [...acc, `${arr[i - 1]} --> ${id}`] : acc), []);
    const labels = LEAN_STAGES.map((s) => `  ${safeId(s)}["${s}"]`);
    const active = LEAN_STAGES.indexOf(p.leanStage);
    const classes = LEAN_STAGES.map((s, i) => {
      if (i < active) return `class ${safeId(s)} done;`;
      if (i === active) return `class ${safeId(s)} active;`;
      return "";
    }).filter(Boolean);
    return [
      "flowchart LR",
      ...labels,
      ...edges.map((e) => "  " + e),
      "classDef active fill:#2563eb,stroke:#93c5fd,color:#fff,stroke-width:2px;",
      "classDef done fill:#1f3a2e,stroke:#3f6d54,color:#9fe3bf;",
      ...classes.map((c) => "  " + c),
    ].join("\n");
  }
  // multi-agent
  const subs = MULTI_NODES.slice(1);
  const lines = [
    "flowchart TD",
    `  ${safeId("lead")}["Lead"]`,
    ...subs.map((s) => `  ${safeId("lead")} --> ${safeId(s)}["${s}"]`),
    "classDef active fill:#2563eb,stroke:#93c5fd,color:#fff,stroke-width:2px;",
    "classDef engaged fill:#1f3a2e,stroke:#3f6d54,color:#9fe3bf;",
    "classDef idle fill:#1b2230,stroke:#33415c,color:#8aa0c0;",
  ];
  for (const n of MULTI_NODES) {
    const cls = p.lastNode === n ? "active" : p.engaged.includes(n) || n === "lead" ? "engaged" : "idle";
    lines.push(`  class ${safeId(n)} ${cls};`);
  }
  return lines.join("\n");
}

export default function Diagram(p: Props) {
  const def = useMemo(() => buildDef(p), [p.mode, p.leanStage, p.lastNode, p.engaged.join(",")]);
  const [svg, setSvg] = useState("");
  const idRef = useRef(`d${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    let alive = true;
    mermaid
      .render(idRef.current, def)
      .then(({ svg }) => alive && setSvg(svg))
      .catch(() => alive && setSvg(`<pre class="muted">${def}</pre>`));
    return () => {
      alive = false;
    };
  }, [def]);

  return <div className="diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}
