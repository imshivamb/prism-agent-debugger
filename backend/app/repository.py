from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from .models import EventRecord, RunArtifactRecord, RunRecord
from .schemas import ExecutionEvent, ExecutionRun, RawArtifact


def _to_schema(record: RunRecord) -> ExecutionRun:
    return ExecutionRun(
        id=record.id,
        title=record.title,
        task=record.task,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        trace_version=record.trace_version,
        provider=record.provider,
        events=[
            ExecutionEvent(
                id=event.id, sequence=event.sequence, phase=event.phase, title=event.title,
                timestamp=event.timestamp, duration_ms=event.duration_ms, status=event.status,
                prompt=event.prompt, input=event.input, output=event.output,
                tool_calls=event.tool_calls, metadata=event.metadata_json,
                parent_event_id=event.parent_event_id,
            )
            for event in record.events
        ],
        raw_artifacts=[RawArtifact(kind=artifact.kind, payload=artifact.payload) for artifact in record.artifacts],
    )


def list_runs(session: Session) -> list[ExecutionRun]:
    records = session.scalars(select(RunRecord).options(selectinload(RunRecord.events)).order_by(RunRecord.started_at.desc())).all()
    return [_to_schema(record) for record in records]


def get_run(session: Session, run_id: str) -> ExecutionRun | None:
    record = session.scalar(select(RunRecord).options(selectinload(RunRecord.events)).where(RunRecord.id == run_id))
    return _to_schema(record) if record else None


def upsert_run(session: Session, run: ExecutionRun) -> ExecutionRun:
    record = session.scalar(select(RunRecord).options(selectinload(RunRecord.events)).where(RunRecord.id == run.id))
    if record:
        session.delete(record)
        session.flush()

    record = RunRecord(id=run.id, title=run.title, task=run.task, status=run.status, trace_version=run.trace_version, provider=run.provider, started_at=run.started_at, completed_at=run.completed_at)
    record.events = [
        EventRecord(
            id=event.id, sequence=event.sequence, phase=event.phase, title=event.title,
            timestamp=event.timestamp, duration_ms=event.duration_ms, status=event.status,
            prompt=event.prompt, input=event.input, output=event.output,
            tool_calls=[tool.model_dump() for tool in event.tool_calls], metadata_json=event.metadata.model_dump(),
            parent_event_id=event.parent_event_id,
        ) for event in run.events
    ]
    record.artifacts = [RunArtifactRecord(kind=artifact.kind, payload=artifact.payload) for artifact in run.raw_artifacts]
    session.add(record)
    session.commit()
    session.refresh(record)
    return _to_schema(record)
