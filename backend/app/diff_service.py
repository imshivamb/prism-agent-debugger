"""Deterministic, provider-neutral comparison of two execution stories."""
from .schemas import ExecutionRun, TraceDiff, TraceDiffItem


def _excerpt(value: str) -> str:
    compact = " ".join(value.split())
    return compact[:180] + ("…" if len(compact) > 180 else "")


def compare_runs(baseline: ExecutionRun, candidate: ExecutionRun) -> TraceDiff:
    """Compare observable behavior without inferring an unrecorded cause.

    Sequence alignment is intentional for the protocol baseline: adapters may
    later supply semantic step IDs, but this produces an honest comparison for
    any imported or Prism-managed trace today.
    """
    changes: list[TraceDiffItem] = []
    if baseline.status != candidate.status:
        impact = "risk" if candidate.status == "failed" else "review"
        changes.append(TraceDiffItem(category="status", label="Run status", baseline=baseline.status, candidate=candidate.status, impact=impact))

    if len(baseline.events) != len(candidate.events):
        changes.append(TraceDiffItem(category="step", label="Execution length", baseline=f"{len(baseline.events)} steps", candidate=f"{len(candidate.events)} steps", impact="review"))

    for index, (before, after) in enumerate(zip(baseline.events, candidate.events), start=1):
        if before.status != after.status:
            changes.append(TraceDiffItem(category="status", label=f"Step {index}: {after.title}", baseline=before.status, candidate=after.status, impact="risk" if after.status == "failed" else "review"))
        if before.title != after.title or before.output != after.output:
            changes.append(TraceDiffItem(category="outcome", label=f"Step {index} outcome", baseline=_excerpt(before.output or before.title), candidate=_excerpt(after.output or after.title), impact="risk" if after.status == "failed" else "review"))
        before_tools = ", ".join(tool.name for tool in before.tool_calls) or "No tools"
        after_tools = ", ".join(tool.name for tool in after.tool_calls) or "No tools"
        if before_tools != after_tools:
            changes.append(TraceDiffItem(category="tools", label=f"Step {index} tool activity", baseline=before_tools, candidate=after_tools, impact="info"))

    if not changes:
        summary = "No observable execution differences were captured between these runs."
    elif candidate.status == "failed":
        summary = "The candidate run introduces a failed state; review the changed steps before relying on its output."
    else:
        summary = f"Prism found {len(changes)} observable difference(s). Review changed outcomes and tool use before treating the runs as equivalent."
    return TraceDiff(baseline_run_id=baseline.id, candidate_run_id=candidate.id, summary=summary, baseline_steps=len(baseline.events), candidate_steps=len(candidate.events), baseline_status=baseline.status, candidate_status=candidate.status, changes=changes)
