"""
TDD tests for the Intercom write-back task push_resolved_writeback
(intercom-writeback aspect, worker-writeback-task).

Strategy: in-memory SQLite, mocked IntercomClient, NO Celery eager mode.
Token decryption is exercised as a REAL Fernet round-trip (house rule —
_decrypt is never monkeypatched): tokens are stored encrypted with
TEST_FERNET_KEY and the tests set LLM_ENCRYPTION_KEY to that key. Mirrors
tests/test_hubspot_writeback_task.py harness structure.

Acceptance criteria coverage (spec.md AC1-AC7, plan_20260815.md §6):
  AC1 guards 1-5 -> TestNoOpGuards; guard 6 -> TestMissingEncryptionKey;
  guard 7 -> TestAdminResolution; AC2 -> TestSuccessPath/TestTimelineEvent/
  TestMarkerSemantics; AC3 -> TestSoftPauseScopeError/TestAlreadyClosed/
  TestTransientRetry; AC4 -> TestReResolve; AC5 -> TestBatchIsolation;
  AC6 -> TestCeleryTaskRegistration; AC7 -> full worker suite.
"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    FeedbackItem,
    FeedbackWorkflowEvent,
    Integration,
    IntercomIntegration,
    Organization,
)

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)

# Real Fernet key for the house-rule round-trip decrypt tests (the same key
# shape test_discord_dispatch.py / test_alerts.py use for LLM_ENCRYPTION_KEY).
TEST_FERNET_KEY = "F5XVApZxzOVKc2xrZlnI6ouXipDzsxflzFn2Ki_5_yk="


def _encrypt(secret: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(TEST_FERNET_KEY.encode()).encrypt(secret.encode()).decode()


@contextmanager
def _fake_db_session():
    """Thin context manager yielding a SQLite session — mirrors get_db_session."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def _make_org(db: Session) -> Organization:
    org = Organization(name="TestCorp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_integration(db: Session, org_id: int, **overrides) -> IntercomIntegration:
    """Token-paste IntercomIntegration row with writeback defaults."""
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        access_token=_encrypt("plain-token"),
        workspace_id="ws-1",
        workspace_name="Test Workspace",
        admin_id="admin-1",
        is_active=True,
        writeback_enabled=True,
        writeback_action="note_and_close",
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    row = IntercomIntegration(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_oauth_integration(db: Session, org_id: int, **overrides) -> Integration:
    """Legacy OAuth Integration(type="intercom") row (no writeback columns)."""
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        type="intercom",
        name="Intercom",
        config={
            "integration_type": "intercom",
            "workspace_id": "ws-1",
            "workspace_name": "Test Workspace",
            "admin_id": "oauth-admin-1",
        },
        oauth_access_token=_encrypt("plain-oauth-token"),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    row = Integration(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_feedback(db: Session, org_id: int, **overrides) -> FeedbackItem:
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        text="Please fix the onboarding flow.",
        source="intercom",
        source_metadata={"conversation_id": "conv-1"},
        workflow_status="resolved",
        created_at=now,
    )
    defaults.update(overrides)
    row = FeedbackItem(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_UNSET = object()


def _make_mock_client(admin_id="admin-1") -> MagicMock:
    """MagicMock IntercomClient with context-manager support.

    Defaults: add_note and close_conversation succeed (no exception),
    fetch_admin_id returns `admin_id`. Pass side_effects on the returned
    mock to simulate upstream failures.
    """
    mc = MagicMock()
    mc.__enter__ = MagicMock(return_value=mc)
    mc.__exit__ = MagicMock(return_value=False)
    mc.add_note.return_value = None
    mc.close_conversation.return_value = None
    mc.fetch_admin_id.return_value = admin_id
    return mc


def _reload_task_module():
    import src.tasks.intercom_writeback as iw
    importlib.reload(iw)
    return iw


def _run_push(db, org_id, items, mock_client=None, task_self=None):
    """Call _push_resolved_writeback_body with the test doubles wired in."""
    iw = _reload_task_module()
    if task_self is None:
        task_self = MagicMock()
    if mock_client is None:
        mock_client = _make_mock_client()
    with patch.object(iw, "IntercomClient", return_value=mock_client):
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            result = iw._push_resolved_writeback_body(task_self, db, org_id, items)
    return result, iw, mock_client


def _assert_zero_client_calls(mock_client):
    mock_client.add_note.assert_not_called()
    mock_client.close_conversation.assert_not_called()
    mock_client.fetch_admin_id.assert_not_called()


# ---------------------------------------------------------------------------
# TestNoOpGuards (AC1 guards 1-5)
# ---------------------------------------------------------------------------


class TestNoOpGuards:
    def test_item_not_found(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": 999, "resolution_note": None}])

        assert result["status"] == "ok"
        assert result["processed"] == 1
        assert result["results"] == [{"id": 999, "status": "noop", "reason": "not_found"}]
        _assert_zero_client_calls(mock_client)

    def test_item_wrong_org(self, db):
        org = _make_org(db)
        other_org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, other_org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "noop", "reason": "not_found"}]
        _assert_zero_client_calls(mock_client)

    def test_non_intercom_source(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id, source="zendesk")

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "noop", "reason": "not_intercom"}]
        _assert_zero_client_calls(mock_client)

    def test_no_conversation_id(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id, source_metadata={})

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [
            {"id": item.id, "status": "noop", "reason": "no_conversation_id"}
        ]
        _assert_zero_client_calls(mock_client)

    def test_marker_already_set(self, db):
        """AC1 guard 3 / AC4: a marker present (prior writeback, re-resolve
        after reopen, or retry re-run) is a noop."""
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id, intercom_writeback_at=datetime.utcnow())

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "noop", "reason": "already_written"}]
        _assert_zero_client_calls(mock_client)

    def test_no_connection(self, db):
        """AC1 guard 4: no token-paste row and no active OAuth row."""
        org = _make_org(db)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "noop", "reason": "no_connection"}]
        _assert_zero_client_calls(mock_client)

    def test_writeback_disabled(self, db):
        """AC1 guard 5: token-paste row present but writeback_enabled false."""
        org = _make_org(db)
        _make_integration(db, org.id, writeback_enabled=False)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [
            {"id": item.id, "status": "noop", "reason": "writeback_disabled"}
        ]
        _assert_zero_client_calls(mock_client)

    def test_malformed_item_recorded_invalid_payload(self, db):
        """Edge case 10: an item without an int id never raises; the batch
        continues."""
        org = _make_org(db)
        _make_integration(db, org.id)
        other = _make_feedback(db, org.id, source="manual")

        result, _, mock_client = _run_push(
            db,
            org.id,
            [
                {"resolution_note": None},
                {"id": "not-an-int", "resolution_note": None},
                {"id": other.id, "resolution_note": None},
            ],
        )

        assert result["processed"] == 3
        assert [r["status"] for r in result["results"]] == ["error", "error", "noop"]
        assert result["results"][0]["reason"] == "invalid_payload"
        assert result["results"][1]["reason"] == "invalid_payload"
        assert result["results"][2]["reason"] == "not_intercom"
        _assert_zero_client_calls(mock_client)
