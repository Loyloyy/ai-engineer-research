import { useEffect, useRef, useState } from "react";
import { streamUrl } from "./api";
import type {
  CoverageEvent,
  DelegateEvent,
  DoneEvent,
  FilesEvent,
  LlmEvent,
  ToolEvent,
  UrlEvent,
} from "./types";

export interface LogEntry {
  t: number;
  kind: "tool" | "llm";
  text: string;
}

export interface RunState {
  connected: boolean;
  status: string;
  leanStage: string;
  running: string[]; // multi-agent subagents currently executing (blue) — between task start & end
  engaged: string[]; // multi-agent subagents that have been delegated to at some point (green once done)
  delegations: DelegateEvent[];
  log: LogEntry[];
  urls: UrlEvent[];
  coverage: CoverageEvent | null;
  report: string;
  files: FilesEvent | null;
  tokens: { prompt: number; completion: number };
  elapsed: number;
  done: DoneEvent | null;
  error: string | null;
}

const EMPTY: RunState = {
  connected: false,
  status: "",
  leanStage: "scope",
  running: [],
  engaged: [],
  delegations: [],
  log: [],
  urls: [],
  coverage: null,
  report: "",
  files: null,
  tokens: { prompt: 0, completion: 0 },
  elapsed: 0,
  done: null,
  error: null,
};

const LOG_CAP = 500;
const URL_CAP = 500;
// Subagents fire start→end fast, and the 0.4s SSE poll can coalesce both into one frame — so a node's
// "active" (blue) phase could render and vanish in a single tick (the "jump straight to maturity" flash).
// Keep each node visibly blue for at least this long after it activates before letting it drop to green.
const MIN_DWELL_MS = 800;

// Subscribe to a run's SSE stream and accumulate its events into a single RunState.
export function useEventStream(runId: string | null): RunState {
  const [state, setState] = useState<RunState>(EMPTY);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) {
      setState(EMPTY);
      return;
    }
    setState({ ...EMPTY });
    const es = new EventSource(streamUrl(runId));
    esRef.current = es;

    // Per-node dwell bookkeeping (see MIN_DWELL_MS): when a node went active, and any pending delayed
    // removal from the `running` set so a fast start→end pair still shows the blue phase.
    const activatedAt = new Map<string, number>();
    const removalTimers = new Map<string, ReturnType<typeof setTimeout>>();

    es.onopen = () => setState((s) => ({ ...s, connected: true }));
    es.onerror = () => setState((s) => ({ ...s, connected: false }));

    const on = (name: string, fn: (d: any) => void) =>
      es.addEventListener(name, (e) => {
        try {
          fn(JSON.parse((e as MessageEvent).data));
        } catch {
          /* ignore malformed frame */
        }
      });

    on("status", (d) => setState((s) => ({ ...s, status: d.text })));

    on("stage", (d) => {
      if (d.mode === "lean") {
        setState((s) => ({ ...s, leanStage: d.node }));
        return;
      }
      // "lead" highlight is derived from whether any subagent is running (see Diagram), so skip it here.
      if (d.node === "lead") return;
      const node = d.node as string;
      if (d.active) {
        const pending = removalTimers.get(node);
        if (pending) {
          clearTimeout(pending);
          removalTimers.delete(node);
        }
        activatedAt.set(node, Date.now());
        setState((s) => {
          const running = new Set(s.running).add(node);
          const engaged = new Set(s.engaged).add(node); // engaged accumulates; never cleared
          return { ...s, running: [...running], engaged: [...engaged] };
        });
        return;
      }
      // Deactivation: hold the blue phase for the remainder of MIN_DWELL_MS before dropping to green.
      const drop = () => {
        removalTimers.delete(node);
        setState((s) => {
          const running = new Set(s.running);
          running.delete(node);
          return { ...s, running: [...running] };
        });
      };
      const remaining = MIN_DWELL_MS - (Date.now() - (activatedAt.get(node) ?? 0));
      const existing = removalTimers.get(node);
      if (existing) clearTimeout(existing);
      if (remaining <= 0) drop();
      else removalTimers.set(node, setTimeout(drop, remaining));
    });

    on("delegate", (d: DelegateEvent) =>
      setState((s) => ({ ...s, delegations: [...s.delegations, d] }))
    );

    on("tool", (d: ToolEvent) =>
      setState((s) => {
        if (d.phase !== "start") return s;
        const text = d.args_summary ? `${d.name} — ${d.args_summary}` : d.name;
        return { ...s, log: cap([...s.log, { t: Date.now(), kind: "tool", text }], LOG_CAP) };
      })
    );

    on("llm", (d: LlmEvent) =>
      setState((s) => {
        if (d.phase === "end") {
          return {
            ...s,
            tokens: {
              prompt: s.tokens.prompt + (d.prompt_tokens || 0),
              completion: s.tokens.completion + (d.completion_tokens || 0),
            },
          };
        }
        const text = d.model ? `LLM call (${d.model})` : "LLM call";
        return { ...s, log: cap([...s.log, { t: Date.now(), kind: "llm", text }], LOG_CAP) };
      })
    );

    on("url", (d: UrlEvent) => setState((s) => ({ ...s, urls: cap([...s.urls, d], URL_CAP) })));
    on("coverage", (d: CoverageEvent) => setState((s) => ({ ...s, coverage: d })));
    on("report", (d) => setState((s) => ({ ...s, report: d.markdown })));
    on("files", (d: FilesEvent) => setState((s) => ({ ...s, files: d })));
    on("heartbeat", (d) => setState((s) => ({ ...s, elapsed: d.elapsed_s })));
    on("error", (d) => setState((s) => ({ ...s, error: d.message })));
    on("done", (d: DoneEvent) => {
      setState((s) => ({ ...s, done: d, connected: false }));
      es.close();
    });

    return () => {
      es.close();
      esRef.current = null;
      removalTimers.forEach((t) => clearTimeout(t));
    };
  }, [runId]);

  return state;
}

function cap<T>(arr: T[], n: number): T[] {
  return arr.length > n ? arr.slice(arr.length - n) : arr;
}
