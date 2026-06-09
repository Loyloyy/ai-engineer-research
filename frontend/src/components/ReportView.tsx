import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders the report markdown (incl. GFM tables for the comparison matrix + numbered [n] citations →
// the linked ## Sources list, which react-markdown turns into clickable links).
export default function ReportView({ markdown }: { markdown: string }) {
  if (!markdown) return <p className="muted">No report yet — it streams in as the lead writes it.</p>;
  return (
    <div className="report markdown">
      <Markdown remarkPlugins={[remarkGfm]}>{markdown}</Markdown>
    </div>
  );
}
