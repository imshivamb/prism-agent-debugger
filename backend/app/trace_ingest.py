"""Versioned trace adapters for provider-neutral Prism ingestion."""
import json
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .schemas import EventMetadata, ExecutionEvent, ExecutionRun, RawArtifact, ToolCall, TraceImportRequest


class TraceAdapter(Protocol):
    def normalize(self, payload: dict) -> ExecutionRun: ...


class PrismV1Adapter:
    def normalize(self, payload: dict) -> ExecutionRun:
        run = ExecutionRun.model_validate(payload)
        return run.model_copy(update={"raw_artifacts": [*run.raw_artifacts, RawArtifact(kind="source.prism.v1", payload=json.dumps(payload, default=str))]})


class GenericEventsV1Adapter:
    """Small permissive adapter for traces with an ordered list of events.

    This intentionally supports only stable, transparent fields. A provider-
    specific adapter can later retain richer semantics without changing Prism's
    core persistence or UI contract.
    """
    def normalize(self, payload: dict) -> ExecutionRun:
        now = datetime.now(timezone.utc)
        raw_events = payload.get("events", [])
        events = [self._event(item, index + 1, now) for index, item in enumerate(raw_events)]
        if not events:
            events = [self._event({"title": "Imported trace", "output": "No discrete events were supplied."}, 1, now)]
        return ExecutionRun(
            id=str(payload.get("id") or f"run_{uuid4().hex}"),
            title=str(payload.get("title") or "Imported agent run"),
            task=str(payload.get("task") or payload.get("input") or "Imported workflow"),
            status="failed" if payload.get("status") == "failed" else "completed",
            started_at=now, completed_at=now, provider=str(payload.get("provider") or "generic_events"), events=events,
            raw_artifacts=[RawArtifact(kind="source.generic.events.v1", payload=json.dumps(payload, default=str))],
        )

    @staticmethod
    def _event(item: dict, sequence: int, now: datetime) -> ExecutionEvent:
        calls = item.get("tool_calls") or item.get("tools") or []
        tools = [ToolCall(name=str(call.get("name", "tool")), summary=str(call.get("summary") or call.get("output") or "Imported tool call."), status="error" if call.get("status") == "error" else "success") for call in calls if isinstance(call, dict)]
        return ExecutionEvent(
            id=str(item.get("id") or f"event_{uuid4().hex}"), sequence=sequence,
            phase=str(item.get("phase") or item.get("type") or "Execution"), title=str(item.get("title") or item.get("name") or f"Step {sequence}"),
            timestamp=now, duration_ms=int(item.get("duration_ms") or 0), status="failed" if item.get("status") == "failed" else "completed",
            prompt=str(item.get("prompt") or "Imported agent event."), input=str(item.get("input") or ""), output=str(item.get("output") or item.get("result") or ""),
            tool_calls=tools, metadata=EventMetadata(latency=str(item.get("latency") or "—"), tokens=str(item.get("tokens") or "—"), model=str(item.get("model") or "unknown")),
        )


ADAPTERS: dict[str, TraceAdapter] = {"prism.v1": PrismV1Adapter(), "generic.events.v1": GenericEventsV1Adapter()}


def import_trace(request: TraceImportRequest) -> ExecutionRun:
    return ADAPTERS[request.adapter].normalize(request.payload)
