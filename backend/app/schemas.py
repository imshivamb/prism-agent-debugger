from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    summary: str
    status: Literal["success", "error"]


class EventMetadata(BaseModel):
    latency: str
    tokens: str
    model: str


class ExecutionEvent(BaseModel):
    id: str
    sequence: int = Field(gt=0)
    phase: str
    title: str
    timestamp: datetime
    duration_ms: int = Field(ge=0)
    status: Literal["completed", "failed", "active"]
    prompt: str
    input: str
    output: str
    tool_calls: list[ToolCall] = []
    metadata: EventMetadata
    parent_event_id: str | None = None


class RawArtifact(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    payload: str


class ExecutionRun(BaseModel):
    id: str
    title: str
    task: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    trace_version: Literal["1.0"] = "1.0"
    provider: str = "import"
    events: list[ExecutionEvent] = []
    raw_artifacts: list[RawArtifact] = []


class AgentRunRequest(BaseModel):
    """Provider-neutral request for a Prism-managed autonomous run."""
    task: str = Field(min_length=3, max_length=12_000)
    title: str | None = Field(default=None, max_length=255)
    provider: Literal["openai_agents", "gemini"] = "openai_agents"
    model: str | None = None
    tools: list[Literal["web_search"]] = Field(default_factory=lambda: ["web_search"])
    max_turns: int = Field(default=8, ge=1, le=20)
    branch_from_run_id: str | None = Field(default=None, max_length=128)
    branch_instruction: str | None = Field(default=None, max_length=4_000)


class AgentRunStartResponse(BaseModel):
    run: ExecutionRun
    poll_url: str


class TraceImportRequest(BaseModel):
    adapter: Literal["prism.v1", "generic.events.v1"] = "prism.v1"
    payload: dict


class AnalysisRequest(BaseModel):
    event_id: str
    kind: Literal["decision", "failure"]


class AnalysisResponse(BaseModel):
    event_id: str
    kind: Literal["decision", "failure"]
    summary: str
    evidence: list[str]
    confidence: Literal["high", "medium", "low"]
    source: Literal["cached", "deterministic", "ai"]


class EvidenceRef(BaseModel):
    event_id: str
    kind: Literal["signal", "correlation", "log", "reproduction"]
    label: str
    excerpt: str


class RejectedAlternative(BaseModel):
    label: str
    reason: str


class DecisionProof(BaseModel):
    target_event_id: str
    claim: str
    evidence: list[EvidenceRef]
    rejected_alternatives: list[RejectedAlternative]
    verification: Literal["signal", "correlated", "reproduced"]
    recommended_action: str
    source: Literal["cached", "compiler", "ai"]


class ChallengeRequest(BaseModel):
    disabled_evidence: list[str] = Field(default_factory=list)


class ActionGate(BaseModel):
    status: Literal["auto_safe", "human_review", "blocked"]
    label: str
    reason: str


class ChallengeResult(BaseModel):
    target_event_id: str
    original_verification: Literal["signal", "correlated", "reproduced"]
    challenged_verification: Literal["signal", "correlated", "reproduced"]
    active_evidence: list[EvidenceRef]
    disabled_evidence: list[str]
    action_gate: ActionGate


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=2_000)
    disabled_evidence: list[str] = Field(default_factory=list)


class ActionApproval(BaseModel):
    id: int
    run_id: str
    action_event_id: str
    decision: Literal["approved", "rejected"]
    note: str
    challenge_snapshot: ChallengeResult
    created_at: datetime


class TraceDiffItem(BaseModel):
    category: Literal["outcome", "step", "tools", "status"]
    label: str
    baseline: str
    candidate: str
    impact: Literal["info", "review", "risk"]


class TraceDiff(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    summary: str
    baseline_steps: int
    candidate_steps: int
    baseline_status: str
    candidate_status: str
    changes: list[TraceDiffItem]
