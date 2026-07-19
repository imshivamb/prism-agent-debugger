"""OpenAI Agents SDK adapter.

The adapter intentionally records Prism's own normalized trace instead of
coupling the UI to an SDK-specific response object. New providers only need to
implement the same `AgentProvider` protocol.
"""
import json
import os
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from ..schemas import AgentRunRequest, EventMetadata, ExecutionEvent, ExecutionRun, RawArtifact, ToolCall


class OpenAIAgentProvider:
    async def run(self, request: AgentRunRequest, run_id: str) -> ExecutionRun:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required to run an OpenAI agent.")
        try:
            from agents import Agent, Runner, WebSearchTool
        except ImportError as error:
            raise RuntimeError("OpenAI Agents SDK is not installed. Install backend requirements first.") from error

        model = request.model or os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
        tools = [WebSearchTool()] if "web_search" in request.tools else []
        agent = Agent(
            name="Prism Research Agent",
            model=model,
            instructions=(
                "You are a careful autonomous research agent. Break the task into verifiable steps, "
                "use tools when they improve confidence, cite uncertainty, and finish with a concise answer."
            ),
            tools=tools,
        )
        started_at = datetime.now(timezone.utc)
        started = perf_counter()
        branch_context = f"\n\nBranch instruction: {request.branch_instruction}" if request.branch_instruction else ""
        result = await Runner.run(agent, request.task + branch_context, max_turns=request.max_turns)
        elapsed_ms = int((perf_counter() - started) * 1000)
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        total_tokens = getattr(usage, "total_tokens", "—")
        events = [ExecutionEvent(
            id=f"event_{uuid4().hex}", sequence=1, phase="Plan", title="Frame the research",
            timestamp=started_at, duration_ms=0, status="completed", prompt="Define the task boundary before researching.",
            input=request.task, output="Scope the question, gather evidence with recorded tools, then produce a recommendation constrained by that evidence.", tool_calls=[],
            metadata=EventMetadata(latency="—", tokens="—", model=model),
        )]
        tool_ordinal = 0
        for item in result.new_items:
            is_tool = self._is_tool(item)
            if is_tool:
                tool_ordinal += 1
            events.append(self._to_event(item, len(events) + 1, model, tool_ordinal if is_tool else None, events[-1].id))
        events.append(ExecutionEvent(
            id=f"event_{uuid4().hex}", sequence=len(events) + 1, phase="Final answer", title="Complete task",
            timestamp=datetime.now(timezone.utc), duration_ms=elapsed_ms, status="completed", prompt=request.task,
            input="Normalized outputs from the autonomous agent loop.", output=str(result.final_output), tool_calls=[], parent_event_id=events[-1].id,
            metadata=EventMetadata(latency=f"{elapsed_ms / 1000:.1f}s", tokens=str(total_tokens), model=model),
        ))
        return ExecutionRun(
            id=run_id, title=request.title or request.task[:80], task=request.task, status="completed",
            started_at=started_at, completed_at=datetime.now(timezone.utc), provider="openai_agents", events=events,
            raw_artifacts=[RawArtifact(kind="agents_sdk.new_items", payload=self._serialize(result.new_items))] + ([RawArtifact(kind="prism.branch.v1", payload=json.dumps({"baseline_run_id": request.branch_from_run_id, "instruction": request.branch_instruction or ""}))] if request.branch_from_run_id else []),
        )

    def _to_event(self, item: object, sequence: int, model: str, tool_ordinal: int | None = None, parent_event_id: str | None = None) -> ExecutionEvent:
        item_type = type(item).__name__
        raw_item = getattr(item, "raw_item", item)
        raw_type = getattr(raw_item, "type", item_type)
        agent = getattr(item, "agent", None)
        agent_name = getattr(agent, "name", "OpenAI agent")
        is_tool = self._is_tool(item)
        tool_name = getattr(raw_item, "name", None) or getattr(raw_item, "tool_name", None) or str(raw_type)
        return ExecutionEvent(
            id=f"event_{uuid4().hex}", sequence=sequence,
            phase="Research" if is_tool else "Reasoning", title=f"Search web evidence {tool_ordinal}" if is_tool else "Evaluate collected evidence",
            timestamp=datetime.now(timezone.utc), duration_ms=0, status="completed",
            prompt=f"{agent_name} emitted {item_type}.", input=f"OpenAI Agents SDK item: {item_type}.", output="The agent completed a recorded web research action. Provider payload is preserved as a raw artifact." if is_tool else "The agent produced an internal reasoning item. Provider payload is preserved as a raw artifact.",
            tool_calls=[ToolCall(name=str(tool_name), summary=f"Recorded web research action {tool_ordinal} from the OpenAI agent loop.", status="success")] if is_tool else [],
            metadata=EventMetadata(latency="—", tokens="—", model=model), parent_event_id=parent_event_id,
        )

    @staticmethod
    def _is_tool(item: object) -> bool:
        raw_item = getattr(item, "raw_item", item)
        raw_type = getattr(raw_item, "type", type(item).__name__)
        return "Tool" in type(item).__name__ or "tool" in str(raw_type).lower()

    @staticmethod
    def _serialize(value: object) -> str:
        try:
            if hasattr(value, "model_dump"):
                return json.dumps(value.model_dump(), default=str)[:12_000]
            if hasattr(value, "__dict__"):
                return json.dumps(value.__dict__, default=str)[:12_000]
            return str(value)[:12_000]
        except Exception:
            return repr(value)[:12_000]
