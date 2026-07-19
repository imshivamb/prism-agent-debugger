import { events as fallbackEvents, run as fallbackRun } from "@/lib/demo-run";
import { ExecutionEvent } from "@/types/execution";

export type ExecutionAnalysis = {
  event_id: string;
  kind: "decision" | "failure";
  summary: string;
  evidence: string[];
  confidence: "high" | "medium" | "low";
  source: "cached" | "deterministic" | "ai";
};

export type DecisionProof = {
  target_event_id: string;
  claim: string;
  evidence: { event_id: string; kind: "signal" | "correlation" | "log" | "reproduction"; label: string; excerpt: string }[];
  rejected_alternatives: { label: string; reason: string }[];
  verification: "signal" | "correlated" | "reproduced";
  recommended_action: string;
  source: "cached" | "compiler" | "ai";
};

export type ChallengeResult = {
  target_event_id: string;
  original_verification: "signal" | "correlated" | "reproduced";
  challenged_verification: "signal" | "correlated" | "reproduced";
  active_evidence: DecisionProof["evidence"];
  disabled_evidence: string[];
  action_gate: { status: "auto_safe" | "human_review" | "blocked"; label: string; reason: string };
};

export type ActionApproval = { id: number; decision: "approved" | "rejected"; note: string; created_at: string };
export type TraceDiff = { baseline_run_id: string; candidate_run_id: string; summary: string; baseline_steps: number; candidate_steps: number; baseline_status: string; candidate_status: string; changes: { category: "outcome" | "step" | "tools" | "status"; label: string; baseline: string; candidate: string; impact: "info" | "review" | "risk" }[] };

type ApiEvent = Omit<ExecutionEvent, "duration" | "position" | "insight" | "toolCalls"> & {
  duration_ms: number;
  timestamp: string;
  tool_calls: ExecutionEvent["toolCalls"];
  parent_event_id?: string | null;
};
type ApiRun = { id: string; title: string; task: string; provider: "openai_agents" | "gemini" | "import" | "curated"; status: "running" | "completed" | "failed"; started_at: string; completed_at: string | null; events: ApiEvent[] };
export type RunView = { run: { id: string; title: string; task: string; startedAt: string; duration: string; status: ApiRun["status"]; provider: ApiRun["provider"] }; events: ExecutionEvent[]; source: "api" | "demo" };

const presentation = new Map(fallbackEvents.map((event) => [event.id, event]));

function duration(durationMs: number) {
  if (durationMs <= 0) return "—";
  return durationMs >= 60_000 ? `${Math.floor(durationMs / 60_000)}m ${Math.round((durationMs % 60_000) / 1_000)}s` : `${Math.round(durationMs / 1_000)}s`;
}

function providerPosition(event: ApiEvent) {
  if (event.phase === "Research") return { x: event.sequence * 230, y: event.sequence % 2 === 0 ? 40 : 210 };
  return { x: event.sequence * 230, y: 125 };
}

function runDuration(startedAt: string, completedAt: string | null) {
  if (!completedAt) return "Running";
  return duration(Math.max(0, new Date(completedAt).getTime() - new Date(startedAt).getTime()));
}

export async function getRun(runId: string): Promise<RunView> {
  const response = await fetch(`/prism-api/api/runs/${runId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Run unavailable");
  const apiRun = (await response.json()) as ApiRun;
  return {
    run: { id: apiRun.id, title: apiRun.title, task: apiRun.task, provider: apiRun.provider, startedAt: new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit" }).format(new Date(apiRun.started_at)), duration: runDuration(apiRun.started_at, apiRun.completed_at), status: apiRun.status },
    events: apiRun.events.map((event) => {
      const display = presentation.get(event.id);
      const providerMetadata = event.title === "Ground with Google Search" && event.output.trim().startsWith("{");
      const verboseGeminiPlan = apiRun.provider === "gemini" && event.phase === "Plan";
      const phaseInsight = event.phase === "Plan" ? "The agent defined what it needed to verify before making a recommendation." : event.phase === "Research" || event.phase === "Tool" ? "The agent gathered evidence before it synthesized a recommendation." : event.phase === "Review" || event.phase === "Final answer" ? "This is the agent’s recommendation, ready to be checked against recorded evidence." : "Recorded execution step.";
      return { ...event, parentEventId: event.parent_event_id, output: providerMetadata ? "Gemini grounded this response with Google Search. The original provider payload is retained as a raw artifact, not shown in the inspector." : verboseGeminiPlan ? "Scope the risks, verify claims against current sources, then propose a reversible rollout with explicit uncertainty." : event.output, toolCalls: event.tool_calls ?? [], timestamp: new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(event.timestamp)), duration: duration(event.duration_ms), position: display?.position ?? providerPosition(event), insight: display?.insight ?? (providerMetadata ? "Prism captured source grounding without exposing provider metadata to the reviewer." : phaseInsight) };
    }),
    source: "api",
  };
}

export async function getFeaturedRun(): Promise<RunView> {
  try { return await getRun("run_checkout_042"); }
  catch { return { run: { ...fallbackRun, status: "completed" }, events: fallbackEvents, source: "demo" }; }
}

export async function startAgentRun(task: string, options: { title?: string; branchFromRunId?: string; branchInstruction?: string; provider?: "openai_agents" | "gemini" } = {}): Promise<{ id: string }> {
  const response = await fetch("/prism-api/api/agent-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task, title: options.title, provider: options.provider, branch_from_run_id: options.branchFromRunId, branch_instruction: options.branchInstruction, tools: ["web_search"] }) });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Could not start agent run.");
  const body = await response.json() as { run: { id: string } };
  return body.run;
}

export async function getTraceDiff(candidateRunId: string, baselineRunId: string): Promise<TraceDiff | null> {
  try { const response = await fetch(`/prism-api/api/runs/${candidateRunId}/diff/${baselineRunId}`, { cache: "no-store" }); return response.ok ? response.json() as Promise<TraceDiff> : null; } catch { return null; }
}

export async function getAnalysis(runId: string, eventId: string, kind: "decision" | "failure" = eventId === "inspect" ? "failure" : "decision"): Promise<ExecutionAnalysis | null> {
  try {
    const response = await fetch(`/prism-api/api/runs/${runId}/analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: eventId, kind }),
    });
    return response.ok ? (response.json() as Promise<ExecutionAnalysis>) : null;
  } catch {
    return null;
  }
}

export async function getDecisionProof(runId: string, eventId: string): Promise<DecisionProof | null> {
  try {
    const response = await fetch(`/prism-api/api/runs/${runId}/proof/${eventId}`, { method: "POST" });
    return response.ok ? (response.json() as Promise<DecisionProof>) : null;
  } catch {
    return null;
  }
}

export async function challengeDecisionProof(runId: string, eventId: string, disabledEvidence: string[]): Promise<ChallengeResult | null> {
  try {
    const response = await fetch(`/prism-api/api/runs/${runId}/proof/${eventId}/challenge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disabled_evidence: disabledEvidence }),
    });
    return response.ok ? (response.json() as Promise<ChallengeResult>) : null;
  } catch {
    return null;
  }
}

export async function recordActionApproval(runId: string, eventId: string, decision: "approved" | "rejected", disabledEvidence: string[]): Promise<ActionApproval | null> {
  try {
    const response = await fetch(`/prism-api/api/runs/${runId}/actions/${eventId}/approvals`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, disabled_evidence: disabledEvidence }) });
    return response.ok ? (response.json() as Promise<ActionApproval>) : null;
  } catch { return null; }
}
