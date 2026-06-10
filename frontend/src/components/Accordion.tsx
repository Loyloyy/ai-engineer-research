import type { ReactNode } from "react";

// A native <details> collapsible — keeps secondary detail on the single run page without crowding it.
// Uncontrolled by default (defaultOpen sets the initial state, user toggles freely). Pass `open` +
// `onToggle` for a controlled accordion (e.g. the Report, which auto-opens when the run finishes but
// stays user-collapsible). `count` shows a small badge in the summary when provided.
export default function Accordion({
  title,
  count,
  defaultOpen = false,
  open,
  onToggle,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (open: boolean) => void;
  children: ReactNode;
}) {
  const controlled = open !== undefined;
  return (
    <details
      className="accordion"
      open={controlled ? open : defaultOpen}
      onToggle={onToggle ? (e) => onToggle(e.currentTarget.open) : undefined}
    >
      <summary>
        <span className="accordion-title">{title}</span>
        {count != null && <span className="accordion-count">{count}</span>}
      </summary>
      <div className="accordion-body">{children}</div>
    </details>
  );
}
