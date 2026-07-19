from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    task: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    trace_version: Mapped[str] = mapped_column(String(16), default="1.0")
    provider: Mapped[str] = mapped_column(String(64), default="import")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    events: Mapped[list["EventRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="EventRecord.sequence"
    )
    artifacts: Mapped[list["RunArtifactRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class EventRecord(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(255))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str] = mapped_column(Text)
    input: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[list[dict]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    parent_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run: Mapped[RunRecord] = relationship(back_populates="events")


class RunArtifactRecord(Base):
    __tablename__ = "run_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    run: Mapped[RunRecord] = relationship(back_populates="artifacts")


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"
    __table_args__ = (UniqueConstraint("run_id", "event_id", "kind", name="uq_analysis_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DecisionProofRecord(Base):
    __tablename__ = "decision_proofs"
    __table_args__ = (UniqueConstraint("run_id", "target_event_id", name="uq_proof_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    target_event_id: Mapped[str] = mapped_column(String(128), index=True)
    claim: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict]] = mapped_column(JSON, default=list)
    rejected_alternatives: Mapped[list[dict]] = mapped_column(JSON, default=list)
    verification: Mapped[str] = mapped_column(String(32))
    recommended_action: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ActionApprovalRecord(Base):
    __tablename__ = "action_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    action_event_id: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    challenge_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
