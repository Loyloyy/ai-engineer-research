// Thin fetch helpers over the FastAPI surface (all under /api).
import type { ActiveRun, RunDetail, RunSummary } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export interface StartRunBody {
  topic: string;
  brief?: string;
  seed_pages?: string[] | null;
  multi_agent?: boolean | null;
  thoroughness?: string | null;
  clarifications?: [string, string][] | null;
}

export const api = {
  clarify: (topic: string, brief: string) =>
    fetch("/api/clarify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, brief }),
    }).then((r) => json<{ questions: string[] }>(r)),

  startRun: (body: StartRunBody) =>
    fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<{ run_id: string }>(r)),

  activeRun: () => fetch("/api/runs/active").then((r) => json<{ active: ActiveRun | null }>(r)),

  stopRun: (id: string) =>
    fetch(`/api/runs/${encodeURIComponent(id)}/stop`, { method: "POST" }).then((r) => json<{ ok: boolean }>(r)),

  resumeRun: (id: string) =>
    fetch(`/api/runs/${encodeURIComponent(id)}/resume`, { method: "POST" }).then((r) => json<{ run_id: string }>(r)),

  listRuns: () => fetch("/api/runs").then((r) => json<{ runs: RunSummary[] }>(r)),

  runDetail: (id: string) => fetch(`/api/runs/${encodeURIComponent(id)}`).then((r) => json<RunDetail>(r)),

  fileUrl: (id: string, name: string) =>
    `/api/runs/${encodeURIComponent(id)}/files/${name.split("/").map(encodeURIComponent).join("/")}`,

  // Phase 2 (present once config_api is wired); UI degrades gracefully if 404.
  listPrompts: () => fetch("/api/prompts").then((r) => json<{ prompts: PromptInfo[] }>(r)),
  getPrompt: (name: string) => fetch(`/api/prompts/${name}`).then((r) => json<PromptDetail>(r)),
  putPrompt: (name: string, body: string) =>
    fetch(`/api/prompts/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    }).then((r) => json<{ ok: boolean }>(r)),
  getEgress: () => fetch("/api/egress").then((r) => json<{ domains: string[] }>(r)),
  getParams: () => fetch("/api/params").then((r) => json<{ params: Record<string, any> }>(r)),
  putParams: (params: Record<string, any>) =>
    fetch("/api/params", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params }),
    }).then((r) => json<{ ok: boolean; params: Record<string, any> }>(r)),
};

export interface PromptInfo {
  name: string;
  has_override: boolean;
}
export interface PromptDetail {
  name: string;
  body: string;
  has_override: boolean;
  appended_readonly: string;
}

export function streamUrl(runId: string): string {
  return `/api/runs/${encodeURIComponent(runId)}/stream`;
}
