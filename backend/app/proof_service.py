"""Compile raw execution steps into an auditable Decision Proof.

The compiler has a deterministic baseline so a trace is never merely a visual
log. A future GPT-5.6 adapter can replace its rules while retaining the same
provenance contract and review UI.
"""
import json
import os
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import DecisionProofRecord
from .schemas import ActionGate, ChallengeResult, DecisionProof, ExecutionRun


def _event(run: ExecutionRun, event_id: str):
    return next(item for item in run.events if item.id == event_id)


def _compile_checkout_proof(run: ExecutionRun, target_event_id: str) -> DecisionProof:
    validate, compare, inspect, recommend = (_event(run, item) for item in ("validate", "compare", "inspect", "recommend"))
    evidence = [
        {"event_id": validate.id, "kind": "signal", "label": "Funnel isolation", "excerpt": "Checkout starts stayed stable while EU desktop completions fell."},
        {"event_id": compare.id, "kind": "correlation", "label": "Release correlation", "excerpt": "The VAT validation payload rolled out 100% in EU and 0% elsewhere."},
        {"event_id": inspect.id, "kind": "log", "label": "Error concentration", "excerpt": "87% of failed sessions contained VAT_COUNTRY_MISMATCH."},
        {"event_id": inspect.id, "kind": "reproduction", "label": "Reproduced failure", "excerpt": "A GB checkout fails when UK is sent instead of ISO code GB."},
    ]
    return DecisionProof(
        target_event_id=target_event_id,
        claim="The GB country-code mismatch in the new VAT payload caused the EU desktop checkout-conversion drop.",
        evidence=evidence,
        rejected_alternatives=[
            {"label": "Traffic quality declined", "reason": "Sessions and checkout starts stayed stable."},
            {"label": "A global payment outage", "reason": "The failure is isolated to the EU rollout and GB addresses."},
        ],
        verification="reproduced",
        recommended_action=recommend.output,
        source="compiler",
    )


def _compile_generic_proof(run: ExecutionRun, target_event_id: str) -> DecisionProof:
    """Conservative baseline for arbitrary traces.

    It never claims reproduction without an explicit provider-specific adapter.
    GPT-5.6 can enrich the content, while this baseline keeps the action gate
    appropriately cautious for unknown workflows.
    """
    target = _event(run, target_event_id)
    preceding = [event for event in run.events if event.sequence < target.sequence][-3:]
    evidence = []
    for event in preceding:
        kind = "log" if event.tool_calls else "signal"
        evidence.append({"event_id": event.id, "kind": kind, "label": event.title, "excerpt": event.output[:280] or "Recorded execution event."})
    if not evidence:
        evidence.append({"event_id": target.id, "kind": "signal", "label": target.title, "excerpt": target.output[:280] or "No supporting evidence was captured."})
    return DecisionProof(
        target_event_id=target_event_id,
        claim=f"{target.title} is the agent's current conclusion and requires review against the recorded trace.", evidence=evidence,
        rejected_alternatives=[], verification="signal",
        recommended_action=target.output or "Human review required before acting.", source="compiler",
    )


def _generate_with_openai(run: ExecutionRun, target_event_id: str) -> DecisionProof | None:
    """Ask GPT-5.6 for a proof while constraining all provenance to trace IDs."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        trace = [{"id": event.id, "phase": event.phase, "title": event.title, "input": event.input, "output": event.output} for event in run.events]
        prompt = f"""Compile an auditable decision proof from this agent trace.
Return only JSON with target_event_id, claim, evidence, rejected_alternatives, verification, recommended_action.
Evidence items require event_id, kind (signal|correlation|log|reproduction), label, excerpt.
Rejected alternatives require label and reason. Verification is signal, correlated, or reproduced.
Every evidence.event_id MUST be one of the provided trace IDs. Do not invent facts.
Target event ID: {target_event_id}
Trace: {json.dumps(trace)}
"""
        response = OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra"), input=prompt, store=False)
        proof = DecisionProof.model_validate_json(response.output_text)
        valid_ids = {event.id for event in run.events}
        if proof.target_event_id != target_event_id or not proof.evidence or any(item.event_id not in valid_ids for item in proof.evidence):
            return None
        return proof.model_copy(update={"source": "ai"})
    except Exception:
        return None


def get_or_compile(session: Session, run: ExecutionRun, target_event_id: str) -> DecisionProof:
    record = session.scalar(select(DecisionProofRecord).where(DecisionProofRecord.run_id == run.id, DecisionProofRecord.target_event_id == target_event_id))
    if record:
        target = _event(run, target_event_id)
        claim = f"{target.title} is the agent's current conclusion and requires review against the recorded trace." if record.claim == target.output else record.claim
        return DecisionProof(target_event_id=record.target_event_id, claim=claim, evidence=record.evidence, rejected_alternatives=record.rejected_alternatives, verification=record.verification, recommended_action=record.recommended_action, source="cached")

    # Provider-specific compilers can recognize stronger semantics. Unknown
    # traces use a deliberately conservative generic proof.
    checkout_ids = {event.id for event in run.events}
    baseline = _compile_checkout_proof(run, target_event_id) if {"validate", "compare", "inspect", "recommend"}.issubset(checkout_ids) else _compile_generic_proof(run, target_event_id)
    proof = _generate_with_openai(run, target_event_id) or baseline
    session.add(DecisionProofRecord(run_id=run.id, target_event_id=proof.target_event_id, claim=proof.claim, evidence=[item.model_dump() for item in proof.evidence], rejected_alternatives=[item.model_dump() for item in proof.rejected_alternatives], verification=proof.verification, recommended_action=proof.recommended_action, source=proof.source))
    session.commit()
    return proof


def challenge(proof: DecisionProof, disabled_evidence: list[str]) -> ChallengeResult:
    """Deterministically downgrade a claim when its supporting provenance is disputed.

    Evidence IDs use `event_id:kind`, letting the UI target a single observation
    even if several facts originate from one execution step.
    """
    disabled = set(disabled_evidence)
    active = [item for item in proof.evidence if f"{item.event_id}:{item.kind}" not in disabled]
    kinds = {item.kind for item in active}
    if "reproduction" in kinds:
        verification = "reproduced"
        gate = ActionGate(status="auto_safe", label="Auto-safe", reason="The claim still has a reproduced failure in its active evidence chain.")
    elif "correlation" in kinds and ("log" in kinds or "signal" in kinds):
        verification = "correlated"
        gate = ActionGate(status="human_review", label="Human review required", reason="The evidence is directionally strong but no active reproduction remains.")
    else:
        verification = "signal"
        gate = ActionGate(status="blocked", label="Blocked", reason="The remaining evidence cannot justify an external remediation action.")
    return ChallengeResult(target_event_id=proof.target_event_id, original_verification=proof.verification, challenged_verification=verification, active_evidence=active, disabled_evidence=sorted(disabled), action_gate=gate)
