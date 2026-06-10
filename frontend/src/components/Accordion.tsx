import type { ReactNode } from "react";

// A native <details> collapsible — keeps secondary detail (fetch ledger, event log, run files) on the
// single run page without crowding it. Native element = no JS state, keyboard-accessible, animatable
// marker via CSS. `count` shows a small badge in the summary when provided.
export default function Accordion({
  title,
  count,
  defaultOpen = false,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="accordion" open={defaultOpen}>
      <summary>
        <span className="accordion-title">{title}</span>
        {count != null && <span className="accordion-count">{count}</span>}
      </summary>
      <div className="accordion-body">{children}</div>
    </details>
  );
}
