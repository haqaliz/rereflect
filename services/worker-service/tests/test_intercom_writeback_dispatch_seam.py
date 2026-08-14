"""
Seam tests for the intercom write-back dispatch from worker writers
(dispatch-seams aspect, R6 — worker side).

Strict TDD: written FIRST (RED) — no dispatch exists in the writers yet.

Every worker writer that can move an Intercom-sourced item to `resolved`
must dispatch the write-back task:

  4. playbook_engine._handle_change_status
  5. automation_feedback_trigger._execute_change_status

Each seam test asserts the EXACT .delay() args (org id + payload with
resolution_note=None — these handlers receive a status string only, the
task falls back to the default note text). Negatives per writer: non-Intercom
source, non-resolved status, and same-value no-op (old_status == new_status —
the writers mutate unconditionally, so the guard is what makes a re-save a
no-op) never dispatch.

Pattern: test_usage_trend_trigger_seam.py — self-contained SQLite engine,
fresh-db autouse fixture, patch the task import in the module under test.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    CustomerHealth,
    FeedbackItem,
    Organization,
)

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def db() -> Session:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session, name: str = "WritebackCorp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_health(db: Session, org_id: int, email: str) -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=70,
        risk_level="moderate",
        confidence_level="medium",
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _make_feedback(
    db: Session,
    org_id: int,
    email: str,
    source: str = "intercom",
    status: str = "new",
) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="Intercom-sourced complaint.",
        source=source,
        workflow_status=status,
        sentiment_label="negative",
        sentiment_score=-0.7,
        is_urgent=False,
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# Seam test 4 — playbook_engine._handle_change_status
# ---------------------------------------------------------------------------


class TestPlaybookEngineDispatch:
    def test_resolved_intercom_item_dispatches(self, db):
        from src.services.playbook_engine import _handle_change_status

        org = _make_org(db)
        email = "playbook-seam@example.com"
        health = _make_health(db, org.id, email)
        fb = _make_feedback(db, org.id, email, source="intercom", status="new")

        with patch("src.services.playbook_engine.push_resolved_writeback") as mock_task:
            result = _handle_change_status({"status": "resolved"}, email, health, db)

        assert result["ok"] is True
        mock_task.delay.assert_called_once_with(
            org.id, [{"id": fb.id, "resolution_note": None}]
        )

    def test_non_intercom_source_does_not_dispatch(self, db):
        from src.services.playbook_engine import _handle_change_status

        org = _make_org(db)
        email = "playbook-negative@example.com"
        health = _make_health(db, org.id, email)
        _make_feedback(db, org.id, email, source="email", status="new")

        with patch("src.services.playbook_engine.push_resolved_writeback") as mock_task:
            _handle_change_status({"status": "resolved"}, email, health, db)

        mock_task.delay.assert_not_called()

    def test_non_resolved_status_does_not_dispatch(self, db):
        from src.services.playbook_engine import _handle_change_status

        org = _make_org(db)
        email = "playbook-negative@example.com"
        health = _make_health(db, org.id, email)
        _make_feedback(db, org.id, email, source="intercom", status="new")

        with patch("src.services.playbook_engine.push_resolved_writeback") as mock_task:
            _handle_change_status({"status": "in_review"}, email, health, db)

        mock_task.delay.assert_not_called()

    def test_same_value_noop_does_not_dispatch(self, db):
        from src.services.playbook_engine import _handle_change_status

        org = _make_org(db)
        email = "playbook-negative@example.com"
        health = _make_health(db, org.id, email)
        _make_feedback(db, org.id, email, source="intercom", status="resolved")

        with patch("src.services.playbook_engine.push_resolved_writeback") as mock_task:
            _handle_change_status({"status": "resolved"}, email, health, db)

        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Seam test 5 — automation_feedback_trigger._execute_change_status
# ---------------------------------------------------------------------------


class TestAutomationTriggerDispatch:
    def test_resolved_intercom_item_dispatches(self, db):
        from src.services.automation_feedback_trigger import _execute_change_status

        org = _make_org(db)
        email = "automation-seam@example.com"
        fb = _make_feedback(db, org.id, email, source="intercom", status="new")

        with patch(
            "src.services.automation_feedback_trigger.push_resolved_writeback"
        ) as mock_task:
            result = _execute_change_status({"status": "resolved"}, fb)

        assert result["error"] is None
        mock_task.delay.assert_called_once_with(
            fb.organization_id, [{"id": fb.id, "resolution_note": None}]
        )

    def test_non_intercom_source_does_not_dispatch(self, db):
        from src.services.automation_feedback_trigger import _execute_change_status

        org = _make_org(db)
        email = "automation-negative@example.com"
        fb = _make_feedback(db, org.id, email, source="email", status="new")

        with patch(
            "src.services.automation_feedback_trigger.push_resolved_writeback"
        ) as mock_task:
            _execute_change_status({"status": "resolved"}, fb)

        mock_task.delay.assert_not_called()

    def test_non_resolved_status_does_not_dispatch(self, db):
        from src.services.automation_feedback_trigger import _execute_change_status

        org = _make_org(db)
        email = "automation-negative@example.com"
        fb = _make_feedback(db, org.id, email, source="intercom", status="new")

        with patch(
            "src.services.automation_feedback_trigger.push_resolved_writeback"
        ) as mock_task:
            _execute_change_status({"status": "in_review"}, fb)

        mock_task.delay.assert_not_called()

    def test_same_value_noop_does_not_dispatch(self, db):
        from src.services.automation_feedback_trigger import _execute_change_status

        org = _make_org(db)
        email = "automation-negative@example.com"
        fb = _make_feedback(db, org.id, email, source="intercom", status="resolved")

        with patch(
            "src.services.automation_feedback_trigger.push_resolved_writeback"
        ) as mock_task:
            _execute_change_status({"status": "resolved"}, fb)

        mock_task.delay.assert_not_called()
