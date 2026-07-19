from typing import Protocol
from ..schemas import AgentRunRequest, ExecutionRun


class AgentProvider(Protocol):
    """A provider converts one task into a normalized, replayable Prism run."""

    async def run(self, request: AgentRunRequest, run_id: str) -> ExecutionRun: ...
