import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 - register ORM models
from app.database import Base, get_session
from app.main import app
from app.repository import upsert_run
from app.schemas import ExecutionRun


class ApiContractTest(unittest.TestCase):
    """Route-level coverage for the local API contract Prism exposes to the UI."""

    @classmethod
    def setUpClass(cls):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        cls.session_factory = sessionmaker(bind=engine)
        fixture_path = Path(__file__).resolve().parents[2] / "sample_runs" / "checkout-conversion-drop.json"
        cls.fixture_run = ExecutionRun.model_validate(json.loads(fixture_path.read_text()))

    def setUp(self):
        self.session = self.session_factory()
        upsert_run(self.session, self.fixture_run)

        def override_session():
            yield self.session

        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        self.session.close()

    def test_import_proof_challenge_approval_and_diff_contract(self):
        listed = self.client.get("/api/runs")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(run["id"] == self.fixture_run.id for run in listed.json()))

        stored = self.client.get(f"/api/runs/{self.fixture_run.id}")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["events"][-1]["id"], "recommend")

        proof = self.client.post(f"/api/runs/{self.fixture_run.id}/proof/recommend")
        self.assertEqual(proof.status_code, 200)
        self.assertEqual(proof.json()["verification"], "reproduced")

        challenged = self.client.post(
            f"/api/runs/{self.fixture_run.id}/proof/recommend/challenge",
            json={"disabled_evidence": ["inspect:reproduction"]},
        )
        self.assertEqual(challenged.status_code, 200)
        self.assertEqual(challenged.json()["action_gate"]["status"], "human_review")

        approval = self.client.post(
            f"/api/runs/{self.fixture_run.id}/actions/recommend/approvals",
            json={"decision": "approved", "note": "Accepted in API contract test.", "disabled_evidence": ["inspect:reproduction"]},
        )
        self.assertEqual(approval.status_code, 201)
        self.assertEqual(approval.json()["challenge_snapshot"]["action_gate"]["status"], "human_review")

        imported = self.client.post("/api/traces/import", json={
            "adapter": "generic.events.v1",
            "payload": {"title": "Imported support run", "task": "Resolve a customer issue", "provider": "test_agent", "events": [
                {"type": "plan", "output": "Check the account history."},
                {"type": "tool", "name": "lookup_account", "tools": [{"name": "lookup_account", "status": "success"}], "output": "Account found."},
            ]},
        })
        self.assertEqual(imported.status_code, 201)
        self.assertEqual(imported.json()["provider"], "test_agent")

        candidate = self.fixture_run.model_copy(deep=True)
        candidate.id = "run_api_candidate"
        candidate.status = "failed"
        for event in candidate.events:
            event.id = f"candidate_{event.id}"
        candidate.events[-1].status = "failed"
        candidate.events[-1].output = "Rollback verification failed."
        imported_candidate = self.client.post("/api/runs/import", json=candidate.model_dump(mode="json"))
        self.assertEqual(imported_candidate.status_code, 201)
        diff = self.client.get(f"/api/runs/{candidate.id}/diff/{self.fixture_run.id}")
        self.assertEqual(diff.status_code, 200)
        self.assertGreater(len(diff.json()["changes"]), 0)


if __name__ == "__main__":
    unittest.main()
