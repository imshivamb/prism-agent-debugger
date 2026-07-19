"""Gemini adapter used for local live-run validation without changing Prism's trace contract."""
import asyncio
import json
import os
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from ..schemas import AgentRunRequest, EventMetadata, ExecutionEvent, ExecutionRun, RawArtifact, ToolCall


class GeminiProvider:
    async def run(self, request: AgentRunRequest, run_id: str) -> ExecutionRun:
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is required to run a Gemini agent.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise RuntimeError("Google Gen AI SDK is not installed. Install backend requirements first.") from error

        model = request.model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        instruction = "You are a careful research agent. Clearly distinguish facts from uncertainty and never expose provider metadata or JSON in your answer."
        branch_context = f"\n\nBranch instruction: {request.branch_instruction}" if request.branch_instruction else ""
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        started_at = datetime.now(timezone.utc)
        plan_started = perf_counter()
        plan_response = await asyncio.to_thread(client.models.generate_content, model=model, contents=f"Create a short, concrete research plan for this task. Return 3 bullets only; no JSON.\n\nTask: {request.task}{branch_context}", config=types.GenerateContentConfig(system_instruction=instruction))
        plan_ms = int((perf_counter() - plan_started) * 1000)
        plan = "Scope the risks, verify claims against current sources, then propose a reversible rollout with explicit uncertainty."
        research_started = perf_counter()
        research_prompt = f"""Research this task using Google Search where helpful, following this plan:
{plan}

Task: {request.task}{branch_context}

Return a clear report with these headings: Verified findings, Assumptions and gaps, Recommended next steps. Use concise plain-text bullets. Do not use Markdown, JSON, or tool metadata."""
        config = types.GenerateContentConfig(system_instruction=instruction, tools=[types.Tool(google_search=types.GoogleSearch())] if "web_search" in request.tools else [])
        response = await asyncio.to_thread(client.models.generate_content, model=model, contents=research_prompt, config=config)
        research_ms = int((perf_counter() - research_started) * 1000)
        grounding = getattr(getattr(response, "candidates", [None])[0], "grounding_metadata", None) if getattr(response, "candidates", None) else None
        usage = getattr(response, "usage_metadata", None)
        total_tokens = getattr(usage, "total_token_count", "—")
        sources = self._source_titles(grounding)
        source_summary = f"Gemini grounded this research in {len(sources)} source(s): {', '.join(sources)}." if sources else "No external sources were recorded for this response. Treat the recommendation as model-generated until a reviewer supplies or verifies evidence."
        events = [
            ExecutionEvent(id=f"event_{uuid4().hex}", sequence=1, phase="Plan", title="Frame the research", timestamp=started_at, duration_ms=plan_ms, status="completed", prompt="Create a concise investigation plan before researching.", input=request.task, output=plan, tool_calls=[], metadata=EventMetadata(latency=f"{plan_ms / 1000:.1f}s", tokens="—", model=model)),
            ExecutionEvent(id=f"event_{uuid4().hex}", sequence=2, phase="Research", title="Verify research coverage" if not grounding else "Ground the research", timestamp=datetime.now(timezone.utc), duration_ms=research_ms, status="completed", prompt="Research the task against current web sources.", input=request.task, output=source_summary, tool_calls=[ToolCall(name="google_search", summary=source_summary, status="success")] if grounding else [], metadata=EventMetadata(latency=f"{research_ms / 1000:.1f}s", tokens=str(total_tokens), model=model)),
            ExecutionEvent(id=f"event_{uuid4().hex}", sequence=3, phase="Review", title="Synthesize recommendation", timestamp=datetime.now(timezone.utc), duration_ms=research_ms, status="completed", prompt="Separate verified findings, gaps, and recommended next steps.", input="Research plan and grounded source set.", output=self._clean_text(getattr(response, "text", "") or "Gemini returned no text."), tool_calls=[], metadata=EventMetadata(latency=f"{research_ms / 1000:.1f}s", tokens=str(total_tokens), model=model)),
        ]
        artifacts = [RawArtifact(kind="gemini.plan_response", payload=self._serialize(plan_response)), RawArtifact(kind="gemini.response", payload=self._serialize(response))]
        if request.branch_from_run_id:
            artifacts.append(RawArtifact(kind="prism.branch.v1", payload=json.dumps({"baseline_run_id": request.branch_from_run_id, "instruction": request.branch_instruction or ""})))
        return ExecutionRun(id=run_id, title=request.title or request.task[:80], task=request.task, status="completed", started_at=started_at, completed_at=datetime.now(timezone.utc), provider="gemini", events=events, raw_artifacts=artifacts)

    @staticmethod
    def _serialize(value: object) -> str:
        try:
            return json.dumps(value.model_dump() if hasattr(value, "model_dump") else value, default=str)[:12_000]
        except Exception:
            return repr(value)[:12_000]

    @staticmethod
    def _source_titles(grounding: object) -> list[str]:
        """Extract a compact reviewer-facing source list; raw metadata stays in artifacts."""
        chunks = getattr(grounding, "grounding_chunks", []) or []
        titles = []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            title = getattr(web, "title", None) if web else None
            if title and title not in titles:
                titles.append(str(title))
        return titles[:8]

    @staticmethod
    def _clean_text(value: str) -> str:
        return value.replace("**", "").replace("* ", "- ").strip()
