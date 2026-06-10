// Backend↔frontend event + domain types. Mirrors webui/events.py + webui/runner.py + artifact/schema.py.

export type StageEvent = { type: "stage"; mode: "lean" | "multi-agent"; node: string; active: boolean };
export type PhaseEvent = {
  type: "phase";
  label: string; // friendly pipeline phase, e.g. "Researching"
  scope: boolean;
  reflection: boolean;
  comparison: boolean;
  report: boolean;
};
export type DelegateEvent = { type: "delegate"; subagent: string; instruction: string };
export type StatusEvent = { type: "status"; text: string };
export type ToolEvent = { type: "tool"; name: string; phase: "start" | "end"; args_summary?: string };
export type LlmEvent = {
  type: "llm";
  phase: "start" | "end";
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
};
export type UrlEvent = { type: "url"; url: string; host: string; outcome: string; ok: boolean };
export type CoverageEvent = {
  type: "coverage";
  fetched_ok: number;
  blocked_or_failed: number;
  fetch_attempts: number;
  elapsed_s?: number | null;
};
export type ReportEvent = { type: "report"; markdown: string };
export type FilesEvent = {
  type: "files";
  scope: string;
  reflection: string;
  comparison: string;
  notes: Record<string, string>;
};
export type HeartbeatEvent = { type: "heartbeat"; elapsed_s: number };
export type DoneEvent = {
  type: "done";
  run_id: string;
  status: string;
  error?: string | null;
  artifact_summary?: ArtifactSummary | null;
};
export type ErrorEvent = { type: "error"; message: string };

export type RunEvent =
  | StageEvent
  | PhaseEvent
  | DelegateEvent
  | StatusEvent
  | ToolEvent
  | LlmEvent
  | UrlEvent
  | CoverageEvent
  | ReportEvent
  | FilesEvent
  | HeartbeatEvent
  | DoneEvent
  | ErrorEvent;

export interface ArtifactSummary {
  id: string;
  version: number;
  findings: number;
  tech_stack: number;
  reference_repos: number;
  implementation_steps: number;
  sources: number;
  open_questions: number;
  coverage?: Record<string, unknown>;
}

export interface RunSummary {
  id: string;
  topic: string;
  latest_version: number | null;
  mode: "lean" | "multi-agent" | null;
  resumable: boolean;
}

export interface Source {
  id: string;
  url: string;
  title?: string | null;
  origin: string;
  fetched_at?: string | null;
}

export interface ReferenceRepo {
  name: string;
  url: string;
  license?: string | null;
  why_relevant: string;
  stars?: number | null;
  last_commit?: string | null;
  archived?: boolean | null;
  code_gathered: boolean;
  reproducibility?: string | null;
}

export interface Artifact {
  id: string;
  version: number;
  topic: string;
  brief: string;
  report_markdown: string;
  sources: Source[];
  reference_repos: ReferenceRepo[];
  tech_stack: { layer: string; choice: string; rationale: string; alternatives: string[] }[];
  open_questions: string[];
}

export interface RunDetail {
  id: string;
  mode: "lean" | "multi-agent" | null;
  artifact: Artifact | null;
  coverage: Record<string, unknown> | null;
  evidence: Record<string, unknown> | null;
  files: { name: string; bytes: number }[];
  langfuse_host: string | null;
  langfuse_session_id: string | null;
}

export interface ActiveRun {
  run_id: string;
  status: string;
  topic: string;
  multi_agent: boolean;
  thoroughness: string;
  elapsed_s: number;
}
