import json
from pathlib import Path
from sqlalchemy.orm import Session
from .repository import get_run, upsert_run
from .schemas import ExecutionRun

DEMO_RUN_PATH = Path(__file__).resolve().parents[2] / "sample_runs" / "checkout-conversion-drop.json"
INSUFFICIENT_EVIDENCE_PATH = Path(__file__).resolve().parents[2] / "sample_runs" / "insufficient-evidence-action.json"


def seed_demo_run(session: Session) -> None:
    """Install curated traces only when a user has not already imported them."""
    for path in (DEMO_RUN_PATH, INSUFFICIENT_EVIDENCE_PATH):
        payload = json.loads(path.read_text())
        if get_run(session, payload["id"]) is None:
            upsert_run(session, ExecutionRun.model_validate(payload))
