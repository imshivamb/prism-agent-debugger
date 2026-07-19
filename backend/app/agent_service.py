"""Lifecycle service for Prism-managed autonomous agent runs."""
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from .agents.openai_agents import OpenAIAgentProvider
from .agents.gemini import GeminiProvider
from .database import SessionLocal
from .repository import upsert_run
from .schemas import AgentRunRequest, EventMetadata, ExecutionEvent, ExecutionRun, RawArtifact


PROVIDERS = {"openai_agents": OpenAIAgentProvider(), "gemini": GeminiProvider()}


def create_pending_run(session: Session, request: AgentRunRequest) -> ExecutionRun:
    run_id = f"run_{uuid4().hex}"
    now = datetime.now(timezone.utc)
    artifacts = []
    if request.branch_from_run_id:
        artifacts.append(RawArtifact(kind="prism.branch.v1", payload=json.dumps({"baseline_run_id": request.branch_from_run_id, "instruction": request.branch_instruction or ""})))
    run = ExecutionRun(
        id=run_id, title=request.title or request.task[:80], task=request.task, status="running", started_at=now,
        provider=request.provider,
        raw_artifacts=artifacts, events=[ExecutionEvent(
            id=f"event_{uuid4().hex}", sequence=1, phase="Run", title="Agent queued", timestamp=now,
            duration_ms=0, status="active", prompt=request.task,
            input=f"provider={request.provider}; model={request.model}; tools={','.join(request.tools) or 'none'}",
            output="Prism accepted the run and is starting the agent.", tool_calls=[],
            metadata=EventMetadata(latency="—", tokens="—", model=request.model or ("gemini-3.5-flash" if request.provider == "gemini" else "gpt-5.6-terra")),
        )],
    )
    return upsert_run(session, run)


async def execute_run(request: AgentRunRequest, run_id: str) -> None:
    provider = PROVIDERS[request.provider]
    try:
        completed = await provider.run(request, run_id)
    except Exception as error:
        now = datetime.now(timezone.utc)
        completed = ExecutionRun(
            id=run_id, title=request.title or request.task[:80], task=request.task, status="failed", started_at=now,
            completed_at=now, provider=request.provider, events=[ExecutionEvent(
                id=f"event_{uuid4().hex}", sequence=1, phase="Run", title="Agent run failed", timestamp=now,
                duration_ms=0, status="failed", prompt=request.task, input="Prism agent runner", output=str(error), tool_calls=[],
                metadata=EventMetadata(latency="—", tokens="—", model=request.model or ("gemini-3.5-flash" if request.provider == "gemini" else "gpt-5.6-terra")),
            )], raw_artifacts=[RawArtifact(kind="prism.branch.v1", payload=json.dumps({"baseline_run_id": request.branch_from_run_id, "instruction": request.branch_instruction or ""}))] if request.branch_from_run_id else [],
        )
    session = SessionLocal()
    try:
        upsert_run(session, completed)
    finally:
        session.close()


def launch(request: AgentRunRequest, session: Session) -> ExecutionRun:
    run = create_pending_run(session, request)
    asyncio.create_task(execute_run(request, run.id))
    return run
