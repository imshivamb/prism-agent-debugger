"use client";

import { FormEvent, useState } from "react";
import { startAgentRun } from "@/lib/api-client";

export function RunLauncher() {
  const [task, setTask] = useState("");
  const [state, setState] = useState<"idle" | "starting" | "error">("idle");
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!task.trim()) return;
    setState("starting"); setError("");
    try { const run = await startAgentRun(task.trim()); window.location.assign(`/runs/${run.id}`); }
    catch (reason) { setState("error"); setError(reason instanceof Error ? reason.message : "Could not start agent run."); }
  };
  return <main className="launcher-shell"><header className="launcher-nav"><div className="brand"><div className="brand-mark"><i /><i /><i /></div><span>prism</span></div><span>Agent execution and trust layer</span></header><section className="launcher-hero"><span className="eyebrow">Run a real agent</span><h1>See the work.<br /><em>Inspect the proof.</em></h1><p>Prism runs an OpenAI research agent, captures every meaningful step, and gives you the evidence needed to decide whether its recommendation is safe.</p><form onSubmit={submit}><textarea value={task} onChange={(event) => setTask(event.target.value)} placeholder="Research the risks of adopting a new payments provider and recommend a safe rollout plan." rows={4} /><div><span>OpenAI · GPT-5.6 Terra · web research</span><button disabled={state === "starting"}>{state === "starting" ? "Starting agent…" : "Run agent →"}</button></div>{state === "error" && <p className="launcher-error">{error} Set `OPENAI_API_KEY` in the backend environment, then retry.</p>}</form><div className="curated-links"><a href="/runs/run_checkout_042">Explore the verified checkout investigation →</a><a href="/runs/run_insufficient_evidence_043">See Prism block a weak-evidence action →</a></div></section></main>;
}
