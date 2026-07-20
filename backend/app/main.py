"""Local-first API for importing and serving Prism execution traces.

The first frontend slice uses a bundled demo trace. These endpoints define the
stable contract for replacing that fixture with SQLite-backed run data.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from .database import SessionLocal, create_database, get_session
from .repository import get_run as find_run, list_runs as find_runs, upsert_run
from .schemas import ActionApproval, AgentRunRequest, AgentRunStartResponse, AnalysisRequest, AnalysisResponse, ApprovalDecisionRequest, ChallengeRequest, ChallengeResult, DecisionProof, ExecutionRun, ProofStressTest, TraceDiff, TraceImportRequest
from .analysis_service import get_or_generate
from .proof_service import challenge, get_or_compile, stress_test
from .agent_service import launch
from .trace_ingest import import_trace
from .approval_service import list_approvals, record_approval
from .diff_service import compare_runs
from .seed import seed_demo_run

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

@asynccontextmanager
async def lifespan(_: FastAPI):
    create_database()
    session = SessionLocal()
    try:
        seed_demo_run(session)
    finally:
        session.close()
    yield


app = FastAPI(title="Prism API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
DbSession = Annotated[Session, Depends(get_session)]


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Prism API",
        "status": "ready",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs", response_model=list[ExecutionRun])
def list_runs(session: DbSession) -> list[ExecutionRun]:
    return find_runs(session)


@app.post("/api/runs/import", response_model=ExecutionRun, status_code=201)
def import_run(run: ExecutionRun, session: DbSession) -> ExecutionRun:
    """Create or replace a normalized execution trace in local SQLite."""
    return upsert_run(session, run)


@app.post("/api/traces/import", response_model=ExecutionRun, status_code=201)
def import_external_trace(request: TraceImportRequest, session: DbSession) -> ExecutionRun:
    """Normalize a versioned external trace through a registered adapter."""
    return upsert_run(session, import_trace(request))


@app.post("/api/agent-runs", response_model=AgentRunStartResponse, status_code=202)
async def start_agent_run(request: AgentRunRequest, session: DbSession) -> AgentRunStartResponse:
    """Start a Prism-managed autonomous agent and return a pollable run immediately."""
    run = launch(request, session)
    return AgentRunStartResponse(run=run, poll_url=f"/api/runs/{run.id}")


@app.get("/api/runs/{run_id}", response_model=ExecutionRun)
def get_run(run_id: str, session: DbSession) -> ExecutionRun:
    run = find_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    return run


@app.get("/api/runs/{run_id}/diff/{baseline_run_id}", response_model=TraceDiff)
def diff_run(run_id: str, baseline_run_id: str, session: DbSession) -> TraceDiff:
    """Compare a candidate execution against a prior recorded run."""
    candidate, baseline = find_run(session, run_id), find_run(session, baseline_run_id)
    if not candidate or not baseline:
        raise HTTPException(status_code=404, detail="Execution run not found")
    return compare_runs(baseline, candidate)


@app.post("/api/runs/{run_id}/analysis", response_model=AnalysisResponse)
def generate_analysis(run_id: str, request: AnalysisRequest, session: DbSession) -> AnalysisResponse:
    """Return a cached explanation, generating it only when no record exists."""
    run = find_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    event = next((item for item in run.events if item.id == request.event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Execution event not found")
    return get_or_generate(session, run_id, event, request.kind)


@app.post("/api/runs/{run_id}/proof/{event_id}", response_model=DecisionProof)
def compile_proof(run_id: str, event_id: str, session: DbSession) -> DecisionProof:
    """Compile a recommendation into a reviewable claim-and-evidence chain."""
    run = find_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if not any(item.id == event_id for item in run.events):
        raise HTTPException(status_code=404, detail="Execution event not found")
    return get_or_compile(session, run, event_id)


@app.post("/api/runs/{run_id}/proof/{event_id}/challenge", response_model=ChallengeResult)
def challenge_proof(run_id: str, event_id: str, request: ChallengeRequest, session: DbSession) -> ChallengeResult:
    """Stress-test a decision by disputing selected evidence links."""
    run = find_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if not any(item.id == event_id for item in run.events):
        raise HTTPException(status_code=404, detail="Execution event not found")
    return challenge(get_or_compile(session, run, event_id), request.disabled_evidence)


@app.post("/api/runs/{run_id}/proof/{event_id}/stress-test", response_model=ProofStressTest)
def stress_test_proof(run_id: str, event_id: str, session: DbSession) -> ProofStressTest:
    """Show which individual evidence links the current action gate depends on."""
    run = find_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if not any(item.id == event_id for item in run.events):
        raise HTTPException(status_code=404, detail="Execution event not found")
    return stress_test(get_or_compile(session, run, event_id))


@app.post("/api/runs/{run_id}/actions/{event_id}/approvals", response_model=ActionApproval, status_code=201)
def approve_action(run_id: str, event_id: str, request: ApprovalDecisionRequest, session: DbSession) -> ActionApproval:
    run = find_run(session, run_id)
    if not run or not any(item.id == event_id for item in run.events):
        raise HTTPException(status_code=404, detail="Action event not found")
    return record_approval(session, run, event_id, request)


@app.get("/api/runs/{run_id}/actions/{event_id}/approvals", response_model=list[ActionApproval])
def action_approval_history(run_id: str, event_id: str, session: DbSession) -> list[ActionApproval]:
    return list_approvals(session, run_id, event_id)
