from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ActionApprovalRecord
from .proof_service import challenge, get_or_compile
from .schemas import ActionApproval, ApprovalDecisionRequest, ExecutionRun


def record_approval(session: Session, run: ExecutionRun, event_id: str, request: ApprovalDecisionRequest) -> ActionApproval:
    snapshot = challenge(get_or_compile(session, run, event_id), request.disabled_evidence)
    record = ActionApprovalRecord(
        run_id=run.id, action_event_id=event_id, decision=request.decision, note=request.note,
        challenge_snapshot=snapshot.model_dump(mode="json"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _to_schema(record)


def list_approvals(session: Session, run_id: str, event_id: str) -> list[ActionApproval]:
    records = session.scalars(select(ActionApprovalRecord).where(ActionApprovalRecord.run_id == run_id, ActionApprovalRecord.action_event_id == event_id).order_by(ActionApprovalRecord.created_at.desc())).all()
    return [_to_schema(record) for record in records]


def _to_schema(record: ActionApprovalRecord) -> ActionApproval:
    return ActionApproval(
        id=record.id, run_id=record.run_id, action_event_id=record.action_event_id,
        decision=record.decision, note=record.note, challenge_snapshot=record.challenge_snapshot,
        created_at=record.created_at,
    )
