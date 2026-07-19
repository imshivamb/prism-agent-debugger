import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analysis_service import get_or_generate
from app.agent_service import create_pending_run
from app.approval_service import list_approvals, record_approval
from app.database import Base
from app import models  # noqa: F401 - registers ORM models
from app.proof_service import challenge, get_or_compile
from app.repository import get_run, upsert_run
from app.schemas import AgentRunRequest, ApprovalDecisionRequest, ExecutionRun, RawArtifact
from app.trace_ingest import import_trace
from app.diff_service import compare_runs
from app.schemas import TraceImportRequest


class TraceServicesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        cls.session_factory = sessionmaker(bind=engine)
        fixture_path = Path(__file__).resolve().parents[2] / "sample_runs" / "checkout-conversion-drop.json"
        cls.fixture_run = ExecutionRun.model_validate(json.loads(fixture_path.read_text()))

    def setUp(self):
        self.session = self.session_factory()
        upsert_run(self.session, self.fixture_run)

    def tearDown(self):
        self.session.close()

    def test_persists_ordered_execution_events(self):
        stored = get_run(self.session, self.fixture_run.id)
        self.assertIsNotNone(stored)
        self.assertEqual([event.id for event in stored.events], ["scope", "validate", "compare", "inspect", "recommend"])

    def test_preserves_protocol_metadata_and_raw_artifacts(self):
        self.fixture_run.provider = "test_provider"
        self.fixture_run.raw_artifacts = [RawArtifact(kind="provider.raw", payload="immutable source event")]
        upsert_run(self.session, self.fixture_run)
        stored = get_run(self.session, self.fixture_run.id)
        self.assertEqual(stored.trace_version, "1.0")
        self.assertEqual(stored.provider, "test_provider")
        self.assertEqual(stored.raw_artifacts[0].payload, "immutable source event")

    def test_creates_a_pollable_pending_agent_run(self):
        pending = create_pending_run(self.session, AgentRunRequest(task="Research a safe payments migration."))
        self.assertEqual(pending.status, "running")
        self.assertEqual(pending.provider, "openai_agents")
        self.assertEqual(pending.events[0].status, "active")

    def test_creates_a_gemini_pending_run(self):
        pending = create_pending_run(self.session, AgentRunRequest(task="Research a safe payments migration.", provider="gemini"))
        self.assertEqual(pending.provider, "gemini")
        self.assertEqual(pending.events[0].metadata.model, "gemini-3.5-flash")

    def test_records_branch_provenance_before_running(self):
        branch = create_pending_run(self.session, AgentRunRequest(
            task="Research a safe payments migration.", branch_from_run_id=self.fixture_run.id,
            branch_instruction="Exclude web search and state uncertainty.",
        ))
        self.assertEqual(branch.raw_artifacts[0].kind, "prism.branch.v1")
        self.assertIn(self.fixture_run.id, branch.raw_artifacts[0].payload)

    def test_normalizes_a_generic_external_trace(self):
        imported = import_trace(TraceImportRequest(adapter="generic.events.v1", payload={
            "title": "External support agent", "task": "Resolve a customer escalation", "provider": "example_provider",
            "events": [{"type": "plan", "input": "Customer report", "output": "Investigate account history"}, {"type": "tool", "name": "lookup_account", "tools": [{"name": "lookup_account", "status": "success"}], "output": "Account located"}],
        }))
        self.assertEqual(imported.provider, "example_provider")
        self.assertEqual(len(imported.events), 2)
        self.assertEqual(imported.events[1].tool_calls[0].name, "lookup_account")
        self.assertEqual(imported.raw_artifacts[0].kind, "source.generic.events.v1")
        upsert_run(self.session, imported)
        proof = get_or_compile(self.session, imported, imported.events[-1].id)
        self.assertEqual(proof.verification, "signal")
        self.assertTrue(proof.evidence)

    def test_compiles_and_caches_a_decision_proof(self):
        first = get_or_compile(self.session, self.fixture_run, "recommend")
        second = get_or_compile(self.session, self.fixture_run, "recommend")
        self.assertEqual(first.verification, "reproduced")
        self.assertEqual(len(first.evidence), 4)
        self.assertEqual(second.source, "cached")
        self.assertTrue(all(item.event_id in {event.id for event in self.fixture_run.events} for item in first.evidence))

    def test_challenge_downgrades_an_unsupported_action(self):
        proof = get_or_compile(self.session, self.fixture_run, "recommend")
        challenged = challenge(proof, ["inspect:reproduction"])
        self.assertEqual(challenged.challenged_verification, "correlated")
        self.assertEqual(challenged.action_gate.status, "human_review")
        blocked = challenge(proof, ["inspect:reproduction", "compare:correlation", "inspect:log"])
        self.assertEqual(blocked.action_gate.status, "blocked")

    def test_generic_weak_evidence_is_blocked(self):
        fixture_path = Path(__file__).resolve().parents[2] / "sample_runs" / "insufficient-evidence-action.json"
        weak_run = ExecutionRun.model_validate(json.loads(fixture_path.read_text()))
        proof = get_or_compile(self.session, weak_run, "alert_recommend")
        assessment = challenge(proof, [])
        self.assertEqual(proof.verification, "signal")
        self.assertEqual(assessment.action_gate.status, "blocked")

    def test_persists_human_approval_with_challenge_snapshot(self):
        approval = record_approval(self.session, self.fixture_run, "recommend", ApprovalDecisionRequest(
            decision="approved", note="Rollback reviewed by on-call engineer.", disabled_evidence=["inspect:reproduction"],
        ))
        self.assertEqual(approval.challenge_snapshot.action_gate.status, "human_review")
        history = list_approvals(self.session, self.fixture_run.id, "recommend")
        self.assertEqual(history[0].id, approval.id)

    def test_diffs_changed_execution_outcomes(self):
        candidate = self.fixture_run.model_copy(deep=True)
        candidate.id = "run_checkout_retry_043"
        candidate.status = "failed"
        candidate.events[-1].status = "failed"
        candidate.events[-1].output = "The retry failed before the rollback could be verified."
        diff = compare_runs(self.fixture_run, candidate)
        self.assertEqual(diff.candidate_status, "failed")
        self.assertTrue(any(change.category == "status" and change.impact == "risk" for change in diff.changes))
        self.assertTrue(any(change.category == "outcome" for change in diff.changes))

    def test_analysis_falls_back_without_a_key(self):
        event = next(item for item in self.fixture_run.events if item.id == "inspect")
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            analysis = get_or_generate(self.session, self.fixture_run.id, event, "failure")
        self.assertEqual(analysis.source, "deterministic")
        self.assertEqual(analysis.confidence, "high")


if __name__ == "__main__":
    unittest.main()
