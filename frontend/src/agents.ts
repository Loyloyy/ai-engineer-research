// Friendly identities for the multi-agent roster + plain-English tool actions. Shared by the diagram,
// the delegations list, and the live caption so a non-technical viewer can follow what each part does.

export const AGENTS: Record<string, { name: string; role: string }> = {
  lead: { name: "Research Director", role: "Plans the work, hands out jobs, then reconciles findings and writes the report" },
  "code-scout": { name: "Code Finder", role: "Hunts down real, working code on GitHub & Hugging Face" },
  landscape: { name: "Market Mapper", role: "Finds the competing tools and compares them" },
  maturity: { name: "Reality Checker", role: "Digs into bugs, limits and production-readiness" },
  "focused-investigator": { name: "Specialist", role: "Called in on demand for one specific deep-dive" },
};

export const ON_DEMAND = new Set(["focused-investigator"]);

export function agentName(id: string): string {
  return AGENTS[id]?.name ?? id;
}

// Raw tool name → plain-English action for the live caption.
export function friendlyAction(tool: string): string {
  const t = tool.toLowerCase();
  if (t.startsWith("write_todo")) return "Planning the to-do list";
  if (t === "ls") return "Listing files";
  if (t === "read_file") return "Reading its notes";
  if (t === "write_file" || t === "edit_file") return "Writing notes";
  if (t === "web_search") return "Searching the web";
  if (t === "fetch_url") return "Reading a page";
  if (t.startsWith("github")) return "Searching GitHub";
  if (t.startsWith("hf_")) return "Searching Hugging Face";
  if (t.startsWith("pypi")) return "Checking a package";
  if (t === "task") return "Handing off a job";
  return `Running ${tool}`;
}
