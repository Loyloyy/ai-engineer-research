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
  lastNode: string; // most recently activated node (lean or multi)
  engaged: string[]; // multi-agent nodes that have been delegated to
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
  lastNode: "",
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

    on("stage", (d) =>
      setState((s) => {
        if (d.mode === "lean") return { ...s, leanStage: d.node, lastNode: d.node };
        const engaged = s.engaged.includes(d.node) ? s.engaged : [...s.engaged, d.node];
        return { ...s, engaged, lastNode: d.node };
      })
    );

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
    };
  }, [runId]);

  return state;
}

function cap<T>(arr: T[], n: number): T[] {
  return arr.length > n ? arr.slice(arr.length - n) : arr;
}
