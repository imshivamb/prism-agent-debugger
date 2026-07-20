"use client";

import { Background, Edge, Handle, MarkerType, Node, Position, ReactFlow, ReactFlowProvider } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";
import { events as demoEvents, run as demoRun } from "@/lib/demo-run";
import { ChallengeResult, DecisionProof, ExecutionAnalysis, ProofStressTest, TraceDiff, type RunView, challengeDecisionProof, getAnalysis, getDecisionProof, getFeaturedRun, getProofStressTest, getRun, getTraceDiff, recordActionApproval, startAgentRun } from "@/lib/api-client";
import { ExecutionEvent } from "@/types/execution";

const colors: Record<string, string> = { Plan: "#a78bfa", Research: "#60a5fa", Analysis: "#22d3ee", Evidence: "#fb7185", Review: "#34d399" };

function StoryNode({ data }: { data: ExecutionEvent & { isSelected?: boolean; isOnPath?: boolean } }) {
  const color = colors[data.phase] ?? "#94a3b8";
  return <div className={`story-node ${data.isSelected ? "is-selected" : ""} ${data.isOnPath ? "is-on-path" : ""}`} style={{ "--accent": color } as React.CSSProperties}>
    <Handle className="story-handle" type="target" position={Position.Left} id="in" />
    <div className="node-topline"><span className="node-index">0{data.sequence}</span><span className="node-status">✓</span></div>
    <p className="node-phase">{data.phase}</p><h3>{data.title}</h3><p className="node-duration">{data.duration}</p>
    {data.toolCalls.length > 0 && <span className="node-evidence">{data.toolCalls.length} evidence {data.toolCalls.length === 1 ? "call" : "calls"}</span>}
    <Handle className="story-handle" type="source" position={Position.Right} id="out" />
  </div>;
}

const nodeTypes = { story: StoryNode };

function ReadableOutput({ value }: { value: string }) {
  const lines = value.split("\n").map((line) => line.trim()).filter(Boolean);
  const clean = (line: string) => line
    .replace(/!?(\[([^\]]+)\])\([^\s)]+\)/g, "$2")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1");
  return <div className="readable-output">{lines.map((line, index) => {
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    if (heading) return <h4 key={`${line}-${index}`}>{clean(heading[1])}</h4>;
    if (/^[A-Z][A-Z\s&-]{3,}$/.test(line)) return <h4 key={`${line}-${index}`}>{line}</h4>;
    if (/^\|[\s:|-]+\|$/.test(line)) return null;
    if (line.startsWith("|")) {
      const cells = line.replace(/^\||\|$/g, "").split("|").map((cell) => clean(cell.trim()));
      return <div className="output-table-row" key={`${line}-${index}`}>{cells.map((cell, cellIndex) => <span key={`${cell}-${cellIndex}`}>{cell}</span>)}</div>;
    }
    const numbered = line.match(/^(\d+)\.\s+(.+)$/);
    if (numbered) return <div className="output-number" key={`${line}-${index}`}><i>{numbered[1]}</i><span>{clean(numbered[2])}</span></div>;
    if (/^[-*]\s+/.test(line)) return <div className="output-bullet" key={`${line}-${index}`}><i>•</i><span>{clean(line.replace(/^[-*]\s+/, ""))}</span></div>;
    return <p key={`${line}-${index}`}>{clean(line)}</p>;
  })}</div>;
}

function Inspector({ event, analysis, proof, challenge, stressTest, diff, disabledEvidence, approvalMessage, onSelectEvidence, onToggleEvidence, onApproval, onBranch }: { event: ExecutionEvent; analysis: ExecutionAnalysis | null; proof: DecisionProof | null; challenge: ChallengeResult | null; stressTest: ProofStressTest | null; diff: TraceDiff | null; disabledEvidence: string[]; approvalMessage: string; onSelectEvidence: (id: string) => void; onToggleEvidence: (key: string) => void; onApproval: (decision: "approved" | "rejected") => void; onBranch: (instruction: string) => void }) {
  const [branchInstruction, setBranchInstruction] = useState("");
  return <aside className="inspector">
    <div className="inspector-header"><div><span className="eyebrow">Selected step</span><h2>{event.title}</h2></div><span className="success-pill">Complete</span></div>
    <p className="inspector-summary">{event.insight}</p>
    {diff && <section className="trace-diff-card"><div className="analysis-heading"><span className="detail-label">Branch comparison</span><span>{diff.changes.length} changes</span></div><p>{diff.summary}</p><div className="diff-change-list">{diff.changes.slice(0, 4).map((change) => <div className={`diff-change ${change.impact}`} key={`${change.category}-${change.label}`}><span>{change.category}</span><b>{change.label}</b><em>{change.baseline} → {change.candidate}</em></div>)}</div>{diff.changes.length > 4 && <small>+ {diff.changes.length - 4} more recorded differences</small>}</section>}
    <section className="analysis-card"><div className="analysis-heading"><span className="detail-label">Why this mattered</span>{analysis && <span>{analysis.confidence} confidence</span>}</div><p>{analysis?.summary ?? event.insight}</p>{analysis?.evidence.map((item) => <div className="evidence-row" key={item}><i>↳</i>{item}</div>)}</section>
    {proof && <section className="proof-card"><div className="proof-heading"><span className="detail-label">Decision proof</span><span className="verification">✓ {challenge?.challenged_verification ?? proof.verification}</span></div><strong>{proof.claim}</strong><p className="challenge-intro">Challenge an evidence link to test whether this action is still justified.</p><div className="proof-chain">{proof.evidence.map((item) => { const key = `${item.event_id}:${item.kind}`; const disabled = disabledEvidence.includes(key); return <div className="proof-row" key={key}><button className={disabled ? "is-disputed" : ""} onClick={() => onSelectEvidence(item.event_id)}><span>{item.kind}</span><b>{item.label}</b><em>{item.excerpt}</em></button><button className={`challenge-button ${disabled ? "is-active" : ""}`} onClick={() => onToggleEvidence(key)} aria-pressed={disabled}>{disabled ? "Restore" : "Challenge"}</button></div>; })}</div>{stressTest && <section className="stress-test"><div className="stress-heading"><span className="detail-label">Proof stress test</span><span>{stressTest.results.filter((item) => item.classification === "critical").length} critical link{stressTest.results.filter((item) => item.classification === "critical").length === 1 ? "" : "s"}</span></div><p>Remove each evidence link in isolation to see whether this action remains safe.</p><div className="stress-results">{stressTest.results.map((item) => <button className={`stress-result ${item.classification}`} key={`${item.evidence.event_id}:${item.evidence.kind}`} onClick={() => onSelectEvidence(item.evidence.event_id)}><span>{item.classification}</span><b>{item.evidence.label}</b><em>{item.action_gate.label} · {item.reason}</em></button>)}</div></section>}{challenge && <div className={`action-gate ${challenge.action_gate.status}`}><span className="detail-label">Action gate</span><strong>{challenge.action_gate.label}</strong><p>{challenge.action_gate.reason}</p><div className="approval-actions"><button onClick={() => onApproval("approved")}>Approve action</button><button onClick={() => onApproval("rejected")}>Reject</button></div>{approvalMessage && <small>{approvalMessage}</small>}</div>}<div className="alternatives"><span className="detail-label">Alternatives ruled out</span>{proof.rejected_alternatives.map((item) => <p key={item.label}><b>{item.label}</b> — {item.reason}</p>)}</div></section>}
    <section className="detail-section"><span className="detail-label">Agent prompt</span><p>{event.prompt}</p></section>
    <section className="detail-section"><span className="detail-label">Output</span><ReadableOutput value={event.output} /></section>
    <section className="detail-section"><span className="detail-label">Tool activity</span>{event.toolCalls.map((tool) => <div className="tool-row" key={tool.name}><span className="tool-check">✓</span><div><code>{tool.name}</code><p>{tool.summary}</p></div></div>)}</section>
    <section className="branch-panel"><span className="detail-label">Branch re-run</span><p>Re-run this task with one changed assumption, then compare the resulting execution story.</p><textarea value={branchInstruction} onChange={(input) => setBranchInstruction(input.target.value)} placeholder="e.g. Do not use web search; state uncertainty instead." rows={3} /><button disabled={!branchInstruction.trim()} onClick={() => onBranch(branchInstruction.trim())}>Launch branch →</button></section>
    <div className="metadata"><div><span>Latency</span><strong>{event.metadata.latency}</strong></div><div><span>Tokens</span><strong>{event.metadata.tokens}</strong></div><div><span>Model</span><strong>{event.metadata.model}</strong></div></div>
  </aside>;
}

function Workspace({ initialRunId, baselineRunId }: { initialRunId: string; baselineRunId?: string }) {
  const [executionEvents, setExecutionEvents] = useState(demoEvents);
  const [executionRun, setExecutionRun] = useState<RunView["run"]>({ ...demoRun, status: "completed" });
  const [dataSource, setDataSource] = useState<"api" | "demo">("demo");
  const [selectedId, setSelectedId] = useState(demoEvents[0].id);
  const [isPlaying, setIsPlaying] = useState(false);
  const [analysesByEvent, setAnalysesByEvent] = useState<Record<string, ExecutionAnalysis>>({});
  const [proofsByEvent, setProofsByEvent] = useState<Record<string, DecisionProof>>({});
  const [stressTestsByEvent, setStressTestsByEvent] = useState<Record<string, ProofStressTest>>({});
  const [disabledEvidence, setDisabledEvidence] = useState<string[]>([]);
  const [challenge, setChallenge] = useState<ChallengeResult | null>(null);
  const [approvalMessage, setApprovalMessage] = useState("");
  const [diff, setDiff] = useState<TraceDiff | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      const loader = initialRunId === "run_checkout_042" ? getFeaturedRun() : getRun(initialRunId);
      loader.then(({ run, events, source }) => { if (!cancelled) { setExecutionRun(run); setExecutionEvents(events); setDataSource(source); setSelectedId(events[0]?.id ?? ""); } }).catch(() => { if (!cancelled) { setExecutionRun({ ...demoRun, title: "Run unavailable", task: "This run could not be loaded.", status: "failed" }); setExecutionEvents(demoEvents); setSelectedId(demoEvents[0].id); } });
    };
    load();
    const poll = initialRunId !== "run_checkout_042" && executionRun.status === "running" ? window.setInterval(load, 2_000) : undefined;
    return () => { cancelled = true; if (poll) window.clearInterval(poll); };
  }, [initialRunId, executionRun.status]);
  useEffect(() => { if (!baselineRunId || executionRun.status === "running") { setDiff(null); return; } getTraceDiff(executionRun.id, baselineRunId).then(setDiff); }, [baselineRunId, executionRun.id, executionRun.status]);
  const selected = executionEvents.find((event) => event.id === selectedId) ?? executionEvents[0];
  const isCuratedCheckout = executionRun.id === "run_checkout_042";
  const analysis = ["Review", "Final answer"].includes(selected.phase) ? null : analysesByEvent[selected.id] ?? null;
  const proof = proofsByEvent[selected.id] ?? null;
  const stressTest = stressTestsByEvent[selected.id] ?? null;
  const shouldShowProof = isCuratedCheckout ? ["inspect", "recommend"].includes(selected.id) : (selected.sequence === executionEvents.length || selected.status === "failed");
  useEffect(() => { setDisabledEvidence([]); setChallenge(null); setApprovalMessage(""); }, [selected.id]);
  useEffect(() => {
    if (analysesByEvent[selected.id]) return;
    let cancelled = false;
    getAnalysis(executionRun.id, selected.id, selected.status === "failed" ? "failure" : "decision").then((result) => { if (result && !cancelled) setAnalysesByEvent((current) => ({ ...current, [selected.id]: result })); });
    return () => { cancelled = true; };
  }, [executionRun.id, selected.id, analysesByEvent]);
  useEffect(() => {
    if (!selected || !shouldShowProof || selected.status === "active" || proofsByEvent[selected.id]) return;
    let cancelled = false;
    getDecisionProof(executionRun.id, selected.id).then((result) => { if (result && !cancelled) setProofsByEvent((current) => ({ ...current, [selected.id]: result })); });
    return () => { cancelled = true; };
  }, [executionRun.id, selected.id, proofsByEvent, shouldShowProof]);
  useEffect(() => {
    if (!proof || stressTestsByEvent[selected.id]) return;
    let cancelled = false;
    getProofStressTest(executionRun.id, selected.id).then((result) => { if (result && !cancelled) setStressTestsByEvent((current) => ({ ...current, [selected.id]: result })); });
    return () => { cancelled = true; };
  }, [executionRun.id, selected.id, proof, stressTestsByEvent]);
  useEffect(() => {
    if (!proof) return;
    let cancelled = false;
    challengeDecisionProof(executionRun.id, selected.id, disabledEvidence).then((result) => { if (result && !cancelled) setChallenge(result); });
    return () => { cancelled = true; };
  }, [executionRun.id, selected.id, proof, disabledEvidence]);
  useEffect(() => {
    if (!isPlaying) return;
    const timer = window.setInterval(() => {
      setSelectedId((currentId) => {
        const index = executionEvents.findIndex((event) => event.id === currentId);
        if (index >= executionEvents.length - 1) { setIsPlaying(false); return currentId; }
        return executionEvents[index + 1].id;
      });
    }, 1800);
    return () => window.clearInterval(timer);
  }, [isPlaying, executionEvents]);
  const graph = useMemo(() => {
    const parentFor = (event: ExecutionEvent, index: number) => executionEvents.find((candidate) => candidate.id === event.parentEventId) ?? executionEvents[index - 1];
    const selectedIndex = executionEvents.findIndex((event) => event.id === selectedId);
    const focused = new Set(executionEvents.slice(0, selectedIndex + 1).map((event) => event.id));
    const nodes: Node[] = executionEvents.map((event) => ({ id: event.id, type: "story", position: event.position, data: { ...event, isSelected: event.id === selectedId, isOnPath: focused.has(event.id) } }));
    const finalEvent = executionEvents.at(-1);
    const sequenceEdges: Edge[] = executionEvents.slice(1).map((event, index) => {
      const parent = parentFor(event, index + 1);
      const evidence = event.toolCalls.length > 0;
      const active = focused.has(parent.id) && focused.has(event.id);
      const color = evidence ? "#fb7185" : event.phase === "Final answer" || event.phase === "Review" ? "#34d399" : "#a78bfa";
      return { id: `causal-${parent.id}-${event.id}`, source: parent.id, sourceHandle: "out", target: event.id, targetHandle: "in", type: "smoothstep", label: evidence ? "evidence" : event.phase === "Final answer" || event.phase === "Review" ? "conclusion" : "reasoning", labelStyle: { fill: active ? color : "#64748b", fontSize: 9, fontFamily: "DM Mono" }, labelBgStyle: { fill: "#0b1220", fillOpacity: .88 }, labelBgPadding: [4, 3], style: { stroke: active ? color : "#334155", strokeWidth: active ? 2.1 : 1.2, opacity: active ? 1 : .42 }, markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 } };
    });
    const proofEdges: Edge[] = finalEvent ? executionEvents.filter((event) => event.toolCalls.length > 0 && event.id !== finalEvent.id && !sequenceEdges.some((edge) => edge.source === event.id && edge.target === finalEvent.id)).map((event) => ({ id: `proof-${event.id}-${finalEvent.id}`, source: event.id, sourceHandle: "out", target: finalEvent.id, targetHandle: "in", type: "smoothstep", label: "supports", labelStyle: { fill: "#fb7185", fontSize: 9, fontFamily: "DM Mono" }, labelBgStyle: { fill: "#0b1220", fillOpacity: .82 }, labelBgPadding: [4, 3], style: { stroke: "#fb7185", strokeWidth: selectedId === finalEvent.id || selectedId === event.id ? 1.8 : 1.1, strokeDasharray: "5 5", opacity: selectedId === finalEvent.id || selectedId === event.id ? .95 : .38 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#fb7185", width: 12, height: 12 } })) : [];
    return { nodes, edges: [...sequenceEdges, ...proofEdges], evidenceLinks: proofEdges.length };
  }, [executionEvents, selectedId]);
  const next = () => setSelectedId(executionEvents[(selected.sequence % executionEvents.length)].id);
  const previous = () => setSelectedId(executionEvents[(selected.sequence + executionEvents.length - 2) % executionEvents.length].id);

  const toggleReplay = () => {
    if (selected.sequence === executionEvents.length) setSelectedId(executionEvents[0].id);
    setIsPlaying((playing) => !playing);
  };
  const exportStory = () => {
    const report = {
      exportedAt: new Date().toISOString(),
      run: executionRun,
      rootCause: isCuratedCheckout ? "GB VAT country code used UK instead of the ISO alpha-2 code GB." : undefined,
      events: executionEvents,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${executionRun.id}-execution-story.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || (event.target instanceof HTMLElement && ["INPUT", "TEXTAREA", "BUTTON", "A"].includes(event.target.tagName))) return;
      if (event.key === "ArrowRight") { event.preventDefault(); setIsPlaying(false); next(); }
      if (event.key === "ArrowLeft") { event.preventDefault(); setIsPlaying(false); previous(); }
      if (event.key === " ") { event.preventDefault(); toggleReplay(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selected.sequence, executionEvents]);

  return <main className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-mark"><i /><i /><i /></div><span>prism</span></div><div className="run-state"><span className={`live-dot ${executionRun.status === "running" ? "is-running" : ""}`} /> {executionRun.status === "running" ? "Agent running" : executionRun.status === "failed" ? "Run failed" : "Execution complete"} <span className="state-separator" /> {executionRun.duration}</div><button className="export-button" onClick={exportStory}>Export story <span>↗</span></button></header>
    <section className="run-hero"><div><div className="eyebrow">Execution story <span className="slash">/</span> {executionRun.id.toUpperCase()} {dataSource === "api" && <span className="api-badge">Local trace</span>}</div><h1>{executionRun.title}</h1><p>{executionRun.task}</p></div><div className="hero-meta"><span>Started {executionRun.startedAt}</span><span>{executionEvents.length} steps <b>·</b> {executionEvents.reduce((total, event) => total + event.toolCalls.length, 0)} tool calls</span></div></section>
    <section className="workspace-grid">
      <nav className="timeline" aria-label="Execution timeline"><div className="panel-heading"><span>Timeline</span><span className="count">{String(executionEvents.length).padStart(2, "0")}</span></div><div className="timeline-list">{executionEvents.map((event) => <button key={event.id} className={`timeline-item ${event.id === selectedId ? "is-selected" : ""}`} aria-current={event.id === selectedId ? "step" : undefined} onClick={() => { setIsPlaying(false); setSelectedId(event.id); }}><span className="timeline-track"><i /></span><span className="timeline-copy"><small>{event.timestamp}</small><strong>{event.title}</strong><em>{event.phase}</em></span><span className="timeline-time">{event.duration}</span></button>)}</div>{isCuratedCheckout ? <div className="root-cause"><span className="root-kicker">Root cause confirmed</span><strong>GB VAT country code used <code>UK</code>, not <code>GB</code>.</strong><button onClick={() => { setIsPlaying(false); setSelectedId("inspect"); }}>View evidence →</button></div> : <div className="root-cause"><span className="root-kicker">Trace assessment</span><strong>{executionRun.status === "failed" ? "The run ended with a visible failure. Inspect the failed step and its captured evidence." : "Select any completed step to inspect its evidence and challenge its recommendation."}</strong></div>}</nav>
      <section className="canvas-panel"><div className="canvas-heading"><div><span className="eyebrow">How the work unfolded</span><h2>From signal to safe fix</h2></div><div className="canvas-context"><div className="causal-map-badge">Causal map <b>{graph.edges.length} links</b>{graph.evidenceLinks > 0 && <em>{graph.evidenceLinks} evidence paths</em>}</div><div className="legend"><span><i className="lavender" /> Reasoning</span><span><i className="coral" /> Evidence</span><span><i className="green" /> Action</span></div>{diff && <div className="diff-summary"><span>Trace diff</span><b>{diff.changes.length} changes</b></div>}</div></div><div className="flow-wrap"><ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} onNodeClick={(_, node) => { setIsPlaying(false); setSelectedId(node.id); }} onInit={(instance) => instance.fitView({ padding: 0.18 })} nodesDraggable={false} nodesConnectable={false} panOnDrag={true} zoomOnScroll={false} proOptions={{ hideAttribution: true }}><Background color="#1e293b" gap={20} size={1} /></ReactFlow></div><div className="replay-bar"><button className="icon-button" onClick={() => { setIsPlaying(false); previous(); }} aria-label="Previous step" aria-keyshortcuts="ArrowLeft">←</button><button className={`play-button ${isPlaying ? "playing" : ""}`} onClick={toggleReplay} aria-pressed={isPlaying} aria-keyshortcuts="Space">{isPlaying ? "Ⅱ Pause replay" : "▶ Replay execution"}</button><button className="icon-button" onClick={() => { setIsPlaying(false); next(); }} aria-label="Next step" aria-keyshortcuts="ArrowRight">→</button><span className="replay-progress"><i style={{ width: `${selected.sequence * (100 / executionEvents.length)}%` }} /> <b>Step {selected.sequence} of {executionEvents.length}</b></span></div></section>
      <Inspector event={selected} analysis={analysis} proof={proof} challenge={challenge} stressTest={stressTest} diff={diff} disabledEvidence={disabledEvidence} approvalMessage={approvalMessage} onSelectEvidence={(id) => { setIsPlaying(false); setSelectedId(id); }} onToggleEvidence={(key) => setDisabledEvidence((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])} onApproval={(decision) => { recordActionApproval(executionRun.id, selected.id, decision, disabledEvidence).then((approval) => setApprovalMessage(approval ? `Decision recorded: ${approval.decision}.` : "Could not record decision.")); }} onBranch={(instruction) => { startAgentRun(executionRun.task, { title: `${executionRun.title} — branch`, branchFromRunId: executionRun.id, branchInstruction: instruction }).then((branch) => window.location.assign(`/runs/${branch.id}?compare=${executionRun.id}`)); }} />
    </section>
  </main>;
}

export function ExecutionWorkspace({ runId = "run_checkout_042", baselineRunId }: { runId?: string; baselineRunId?: string }) { return <ReactFlowProvider><Workspace initialRunId={runId} baselineRunId={baselineRunId} /></ReactFlowProvider>; }
