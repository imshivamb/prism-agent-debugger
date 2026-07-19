"""Cached explanation generation.

This module is deliberately the only AI-provider boundary. The deterministic
fallback keeps the local demo useful and costs nothing; an OpenAI/OpenRouter
adapter can replace `generate` without changing routes, storage, or the UI.
"""
import json
import os
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import AnalysisRecord
from .schemas import AnalysisResponse, ExecutionEvent


def _explain(event: ExecutionEvent, kind: str) -> tuple[str, list[str], str]:
    if kind == "failure":
        return (
            "The checkout failure was caused by a country-code contract mismatch, not a traffic or payment-volume change.",
            ["EU desktop checkout completion fell while checkout starts stayed stable.", "87% of failed sessions contained VAT_COUNTRY_MISMATCH.", "A replay reproduced the error when UK was sent instead of the ISO alpha-2 code GB."],
            "high",
        )
    if event.phase == "Plan":
        return ("The agent set an investigation boundary before researching, which keeps later conclusions tied to the task instead of a generic answer.", ["The plan scopes what must be verified.", "No external action is proposed at this stage."], "medium")
    if event.phase in {"Research", "Tool"}:
        return ("This step gathers evidence. Its value depends on the recorded source set, not on a recommendation made yet.", [f"The step used {len(event.tool_calls)} recorded tool call(s).", f"Input considered: {event.input}"], "medium")
    if event.phase in {"Review", "Final answer"}:
        return ("The agent has turned the recorded work into a proposed next step. Review its evidence chain before approving an external action.", ["The recommendation is preserved as the raw final output.", "Prism’s Decision Proof limits confidence to the evidence captured in this run."], "medium")
    return (
        event.output,
        [f"The step used {len(event.tool_calls)} recorded tool call(s).", f"Input considered: {event.input}"],
        "high" if event.phase in {"Evidence", "Review"} else "medium",
    )


def _generate_with_openai(event: ExecutionEvent, kind: str) -> tuple[str, list[str], str] | None:
    """Generate a compact, structured explanation only when a local key exists."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        prompt = f"""You explain a recorded AI-agent execution step for a developer debugger.
Return only JSON with keys summary (string), evidence (array of up to 3 strings), and confidence (high, medium, or low).
Do not invent facts; use only the recorded event.

Analysis type: {kind}
Phase: {event.phase}
Title: {event.title}
Prompt: {event.prompt}
Input: {event.input}
Output: {event.output}
Tools: {[tool.model_dump() for tool in event.tool_calls]}
"""
        response = OpenAI().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            input=prompt,
            store=False,
        )
        result = json.loads(response.output_text)
        confidence = result.get("confidence", "medium")
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        return str(result["summary"]), [str(item) for item in result.get("evidence", [])[:3]], confidence
    except Exception:
        # A demo must stay usable if an optional provider is unavailable.
        return None


def get_or_generate(session: Session, run_id: str, event: ExecutionEvent, kind: str) -> AnalysisResponse:
    record = session.scalar(select(AnalysisRecord).where(AnalysisRecord.run_id == run_id, AnalysisRecord.event_id == event.id, AnalysisRecord.kind == kind))
    if record:
        return AnalysisResponse(event_id=event.id, kind=kind, summary=record.summary, evidence=record.evidence, confidence=record.confidence, source="cached")

    generated = _generate_with_openai(event, kind)
    summary, evidence, confidence = generated or _explain(event, kind)
    source = "ai" if generated else "deterministic"
    record = AnalysisRecord(run_id=run_id, event_id=event.id, kind=kind, summary=summary, evidence=evidence, confidence=confidence, source=source)
    session.add(record)
    session.commit()
    return AnalysisResponse(event_id=event.id, kind=kind, summary=summary, evidence=evidence, confidence=confidence, source=source)
