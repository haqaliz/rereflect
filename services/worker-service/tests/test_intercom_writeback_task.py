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

from src.clients.intercom import IntercomTransientError
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


def _get_events(db) -> list:
    return (
        db.query(FeedbackWorkflowEvent)
        .filter_by(event_type="intercom_writeback")
        .order_by(FeedbackWorkflowEvent.id)
        .all()
    )


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


# ---------------------------------------------------------------------------
# TestCredentialResolution (plan D4 — token-paste wins, flag authoritative)
# ---------------------------------------------------------------------------


class TestCredentialResolution:
    def test_token_paste_wins_when_both_exist(self, db):
        """A disabled token-paste row beats an active OAuth row: the
        token-paste row's writeback_enabled flag is authoritative."""
        org = _make_org(db)
        _make_integration(db, org.id, writeback_enabled=False)
        _make_oauth_integration(db, org.id)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [
            {"id": item.id, "status": "noop", "reason": "writeback_disabled"}
        ]
        _assert_zero_client_calls(mock_client)


# ---------------------------------------------------------------------------
# TestMissingEncryptionKey (AC1 guard 6 — R6: no retry, recorded on the row)
# ---------------------------------------------------------------------------


class TestMissingEncryptionKey:
    def test_missing_key_returns_error_dict_without_retry(self, db, monkeypatch):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        iw = _reload_task_module()
        task_self = MagicMock()
        mock_client = _make_mock_client()
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        with patch.object(iw, "IntercomClient", return_value=mock_client):
            result = iw._push_resolved_writeback_body(
                task_self, db, org.id, [{"id": item.id, "resolution_note": None}]
            )

        assert result["results"] == [
            {"id": item.id, "status": "error", "reason": "missing_encryption_key"}
        ]
        task_self.retry.assert_not_called()
        _assert_zero_client_calls(mock_client)

        db.expire_all()
        integ = db.query(IntercomIntegration).filter_by(organization_id=org.id).first()
        assert integ.last_writeback_status == "error"
        assert integ.last_writeback_error == "missing_encryption_key"
        assert integ.last_writeback_at is None

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_ == {
            "source": "intercom",
            "action": "note_and_close",
            "note_sent": False,
            "closed": False,
            "reason": "missing_encryption_key",
        }

    def test_invalid_token_records_token_decrypt_failed(self, db, monkeypatch):
        """A token encrypted under a different key is a real Fernet
        InvalidToken — recorded token_decrypt_failed, no retry (plan §7.7)."""
        from cryptography.fernet import Fernet

        other_key = Fernet.generate_key()
        org = _make_org(db)
        _make_integration(
            db, org.id, access_token=Fernet(other_key).encrypt(b"plain-token").decode()
        )
        item = _make_feedback(db, org.id)

        iw = _reload_task_module()
        task_self = MagicMock()
        mock_client = _make_mock_client()
        with patch.object(iw, "IntercomClient", return_value=mock_client):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                result = iw._push_resolved_writeback_body(
                    task_self, db, org.id, [{"id": item.id, "resolution_note": None}]
                )

        assert result["results"] == [
            {"id": item.id, "status": "error", "reason": "token_decrypt_failed"}
        ]
        task_self.retry.assert_not_called()
        _assert_zero_client_calls(mock_client)

        db.expire_all()
        integ = db.query(IntercomIntegration).filter_by(organization_id=org.id).first()
        assert integ.last_writeback_status == "error"
        assert integ.last_writeback_error == "token_decrypt_failed"

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["reason"] == "token_decrypt_failed"


# ---------------------------------------------------------------------------
# TestAdminResolution (AC1 guard 7 — recorded error/no_admin, no retry)
# ---------------------------------------------------------------------------


class TestAdminResolution:
    def test_no_admin_recorded_without_retry(self, db):
        """Stored admin id absent AND fetch_admin_id fails -> error/no_admin,
        no retry, never reaching add_note/close. Pinned with a TRANSIENT
        /me failure: even 429/5xx on the admin fetch is a recorded terminal
        outcome, not a retry (plan §10 decision 5)."""
        from src.clients.intercom import IntercomTransientError

        org = _make_org(db)
        _make_integration(db, org.id, admin_id=None)
        item = _make_feedback(db, org.id)

        mock_client = _make_mock_client()
        mock_client.fetch_admin_id.side_effect = IntercomTransientError("rate limited on /me")

        result, _, _ = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}],
                                 mock_client=mock_client)

        assert result["results"] == [{"id": item.id, "status": "error", "reason": "no_admin"}]
        mock_client.fetch_admin_id.assert_called_once()
        mock_client.add_note.assert_not_called()
        mock_client.close_conversation.assert_not_called()

        db.expire_all()
        integ = db.query(IntercomIntegration).filter_by(organization_id=org.id).first()
        assert integ.last_writeback_status == "error: no_admin"
        assert integ.last_writeback_error == "rate limited on /me"
        assert integ.last_writeback_at is not None
        assert integ.is_active is True  # never touched

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["reason"] == "no_admin"
        assert events[0].metadata_["note_sent"] is False
        assert events[0].metadata_["closed"] is False


# ---------------------------------------------------------------------------
# TestLegacyOAuthPath (plan D4 — OAuth outcomes recorded in event only)
# ---------------------------------------------------------------------------


class TestLegacyOAuthPath:
    def test_oauth_missing_key_records_in_event_only(self, db, monkeypatch):
        """OAuth-only org with a missing key: outcome + event written; the
        legacy Integration row has no writeback columns to touch."""
        org = _make_org(db)
        _make_oauth_integration(db, org.id)
        item = _make_feedback(db, org.id)

        iw = _reload_task_module()
        task_self = MagicMock()
        mock_client = _make_mock_client()
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        with patch.object(iw, "IntercomClient", return_value=mock_client):
            result = iw._push_resolved_writeback_body(
                task_self, db, org.id, [{"id": item.id, "resolution_note": None}]
            )

        assert result["results"] == [
            {"id": item.id, "status": "error", "reason": "missing_encryption_key"}
        ]
        task_self.retry.assert_not_called()
        _assert_zero_client_calls(mock_client)

        db.expire_all()
        oauth = db.query(Integration).filter_by(
            organization_id=org.id, type="intercom"
        ).first()
        assert oauth.is_active is True
        assert not hasattr(oauth, "last_writeback_status")

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_ == {
            "source": "intercom",
            "action": "note_and_close",
            "note_sent": False,
            "closed": False,
            "reason": "missing_encryption_key",
        }


# ---------------------------------------------------------------------------
# TestSuccessPath (AC2 — note first, then close; marker; row; event)
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_note_then_close_called_with_correct_args(self, db):
        from unittest.mock import call

        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": "Thanks — shipped in v2.3."}]
        )

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        assert mock_client.method_calls == [
            call.add_note("conv-1", "admin-1", "Thanks — shipped in v2.3."),
            call.close_conversation("conv-1", "admin-1"),
        ]

    def test_default_note_text_when_no_resolution_note(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        mock_client.add_note.assert_called_once_with(
            "conv-1", "admin-1", "Marked resolved in Rereflect."
        )
        mock_client.close_conversation.assert_called_once_with("conv-1", "admin-1")

    def test_resolution_note_used(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": "Fixed in 2.3.0"}]
        )

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        mock_client.add_note.assert_called_once_with(
            "conv-1", "admin-1", "Fixed in 2.3.0"
        )

    def test_whitespace_resolution_note_falls_back_to_default(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": "   "}]
        )

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        mock_client.add_note.assert_called_once_with(
            "conv-1", "admin-1", "Marked resolved in Rereflect."
        )

    def test_note_only_skips_close(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_action="note_only")
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        mock_client.add_note.assert_called_once()
        mock_client.close_conversation.assert_not_called()

    def test_unknown_action_falls_back_to_note_and_close(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_action="delete-everything")
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        mock_client.close_conversation.assert_called_once()

    def test_stored_admin_id_used_no_fetch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, admin_id="stored-admin-9")
        item = _make_feedback(db, org.id)

        _, _, mock_client = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        mock_client.add_note.assert_called_once()
        assert mock_client.add_note.call_args.args[1] == "stored-admin-9"
        mock_client.fetch_admin_id.assert_not_called()

    def test_fetch_admin_id_fallback_value_used(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, admin_id=None)
        item = _make_feedback(db, org.id)

        mock_client = _make_mock_client(admin_id="fetched-admin-7")
        _, _, _ = _run_push(db, org.id, [{"id": item.id, "resolution_note": None}],
                            mock_client=mock_client)

        mock_client.fetch_admin_id.assert_called_once()
        assert mock_client.add_note.call_args.args[1] == "fetched-admin-7"


# ---------------------------------------------------------------------------
# TestMarkerSemantics (plan D3 — marker set on success, per-item committed)
# ---------------------------------------------------------------------------


class TestMarkerSemantics:
    def test_marker_set_on_feedback_item(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        # Fresh session re-query proves the per-item commit, not a same-session
        # flush.
        with _fake_db_session() as fresh:
            marker = (
                fresh.query(FeedbackItem)
                .filter_by(id=item.id)
                .first()
            )
            assert marker.intercom_writeback_at is not None

    def test_marker_not_set_on_decrypt_failure(self, db, monkeypatch):
        """D3: config failures stay re-runnable — the marker must NOT be set
        so the operator's fix can be retried without a second dispatch."""
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        iw = _reload_task_module()
        task_self = MagicMock()
        mock_client = _make_mock_client()
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        with patch.object(iw, "IntercomClient", return_value=mock_client):
            iw._push_resolved_writeback_body(
                task_self, db, org.id, [{"id": item.id, "resolution_note": None}]
            )

        db.expire_all()
        assert db.query(FeedbackItem).filter_by(id=item.id).first().intercom_writeback_at is None


# ---------------------------------------------------------------------------
# TestTimelineEvent (AC2 / plan D7 — one event, exact metadata contract)
# ---------------------------------------------------------------------------


class TestTimelineEvent:
    def test_exactly_one_intercom_writeback_event(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        events = _get_events(db)
        assert len(events) == 1
        event = events[0]
        assert event.feedback_id == item.id
        assert event.organization_id == org.id
        assert event.actor_id is None
        assert event.event_type == "intercom_writeback"
        assert event.old_value is None
        assert event.new_value is None
        assert event.metadata_ == {
            "source": "intercom",
            "action": "note_and_close",
            "note_sent": True,
            "closed": True,
        }

    def test_note_only_event_records_closed_false(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_action="note_only")
        item = _make_feedback(db, org.id)

        _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["action"] == "note_only"
        assert events[0].metadata_["closed"] is False
        assert events[0].metadata_["note_sent"] is True

    def test_guard_noops_write_no_timeline_event(self, db):
        """D7: guards 1-5 are pure returns — no timeline noise."""
        org = _make_org(db)
        _make_integration(db, org.id, writeback_enabled=False)
        item = _make_feedback(db, org.id)

        _run_push(db, org.id, [{"id": item.id, "resolution_note": None}])

        assert _get_events(db) == []


# ---------------------------------------------------------------------------
# TestLegacyOAuthPath (cont. — plan D4: OAuth success, event-only recording)
# ---------------------------------------------------------------------------


class TestLegacyOAuthPath:
    def test_oauth_fallback_writes_no_columns_but_emits_event(self, db):
        org = _make_org(db)
        oauth = _make_oauth_integration(db, org.id)
        item = _make_feedback(db, org.id)

        result, _, mock_client = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": "OAuth-resolved note"}]
        )

        assert result["results"] == [{"id": item.id, "status": "ok", "reason": None}]
        # Token decrypted from oauth_access_token; admin from config["admin_id"].
        mock_client.add_note.assert_called_once_with(
            "conv-1", "oauth-admin-1", "OAuth-resolved note"
        )
        mock_client.close_conversation.assert_called_once_with("conv-1", "oauth-admin-1")

        # OAuth row has no writeback columns — nothing to update (the model
        # carries none; the timeline event is the durable record).
        db.expire_all()
        row = db.query(Integration).filter_by(id=oauth.id).first()
        assert row.is_active is True
        assert not hasattr(row, "last_writeback_status")

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["note_sent"] is True
        assert events[0].metadata_["closed"] is True


# ---------------------------------------------------------------------------
# TestSoftPauseScopeError (AC3 403 — soft-pause, is_active NEVER touched)
# ---------------------------------------------------------------------------


class TestSoftPauseScopeError:
    def test_403_records_missing_write_scope_and_never_flips_is_active(self, db):
        from src.clients.intercom import IntercomAuthError

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        mock_client = _make_mock_client()
        mock_client.add_note.side_effect = IntercomAuthError(
            "missing conversation:write scope"
        )

        result, _, _ = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": None}], mock_client=mock_client
        )

        assert result["results"] == [
            {"id": item.id, "status": "error", "reason": "missing_write_scope"}
        ]

        db.expire_all()
        row = db.query(IntercomIntegration).filter_by(id=integ.id).first()
        assert row.last_writeback_status == "error: missing_write_scope"
        assert row.last_writeback_error == "missing conversation:write scope"
        assert row.last_writeback_at is not None
        assert row.is_active is True  # never touched by writeback

        # Marker NOT set — the operator fixing the scope can retry without a
        # second dispatch.
        db.expire_all()
        assert (
            db.query(FeedbackItem).filter_by(id=item.id).first().intercom_writeback_at
            is None
        )

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["reason"] == "missing_write_scope"
        assert events[0].metadata_["note_sent"] is False
        assert events[0].metadata_["closed"] is False


# ---------------------------------------------------------------------------
# TestAlreadyClosed (AC3 404 — idempotent-by-404, marker set, re-run skips)
# ---------------------------------------------------------------------------


class TestAlreadyClosed:
    def test_404_note_is_noop_already_closed_and_sets_marker(self, db):
        from src.clients.intercom import IntercomNotFoundError

        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        mock_client = _make_mock_client()
        mock_client.add_note.side_effect = IntercomNotFoundError(
            "conversation not found"
        )

        result, _, _ = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": None}], mock_client=mock_client
        )

        assert result["results"] == [
            {"id": item.id, "status": "noop", "reason": "already_closed"}
        ]

        # Marker set (404 is a terminal, idempotent outcome) — committed per
        # item, visible on a fresh session.
        with _fake_db_session() as fresh:
            assert (
                fresh.query(FeedbackItem).filter_by(id=item.id).first().intercom_writeback_at
                is not None
            )

        db.expire_all()
        row = db.query(IntercomIntegration).filter_by(organization_id=org.id).first()
        assert row.last_writeback_status == "noop: already_closed"

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["note_sent"] is True  # 404-idempotent
        assert events[0].metadata_["closed"] is True  # already closed
        assert events[0].metadata_["reason"] == "already_closed"

        # Re-run skips via guard 3 — zero calls.
        rerun, _, mc2 = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": None}]
        )
        assert rerun["results"] == [
            {"id": item.id, "status": "noop", "reason": "already_written"}
        ]
        mc2.add_note.assert_not_called()
        mc2.close_conversation.assert_not_called()

    def test_close_404_after_note_is_already_closed(self, db):
        from src.clients.intercom import IntercomNotFoundError

        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        mock_client = _make_mock_client()
        mock_client.close_conversation.side_effect = IntercomNotFoundError(
            "already closed"
        )

        result, _, _ = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": None}], mock_client=mock_client
        )

        assert result["results"] == [
            {"id": item.id, "status": "noop", "reason": "already_closed"}
        ]
        mock_client.add_note.assert_called_once()

        events = _get_events(db)
        assert len(events) == 1
        assert events[0].metadata_["note_sent"] is True
        assert events[0].metadata_["closed"] is True
        assert events[0].metadata_["reason"] == "already_closed"

        with _fake_db_session() as fresh:
            assert (
                fresh.query(FeedbackItem).filter_by(id=item.id).first().intercom_writeback_at
                is not None
            )


# ---------------------------------------------------------------------------
# TestTransientRetry (AC3 429/5xx — whole-payload retry, no eager mode)
# ---------------------------------------------------------------------------


class TestTransientRetry:
    @pytest.mark.parametrize(
        "exc",
        [
            IntercomTransientError("rate limited (429)"),
            IntercomTransientError("intercom returned 500"),
        ],
    )
    def test_transient_error_triggers_retry(self, db, exc):
        from celery.exceptions import Retry
        from src.clients.intercom import IntercomTransientError

        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id)

        mock_client = _make_mock_client()
        mock_client.add_note.side_effect = exc

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        # The body never swallows Retry — it propagates out of the run
        # (whole-payload abort-and-retry semantics).
        with pytest.raises(Retry):
            _run_push(
                db, org.id, [{"id": item.id, "resolution_note": None}],
                mock_client=mock_client, task_self=task_self,
            )

        task_self.retry.assert_called_once()


# ---------------------------------------------------------------------------
# TestReResolve (AC4 — marker makes a re-resolve after reopen a noop)
# ---------------------------------------------------------------------------


class TestReResolve:
    def test_reresolve_after_reopen_is_noop(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        item = _make_feedback(db, org.id, intercom_writeback_at=datetime.utcnow())

        result, _, mock_client = _run_push(
            db, org.id, [{"id": item.id, "resolution_note": None}]
        )

        assert result["results"] == [
            {"id": item.id, "status": "noop", "reason": "already_written"}
        ]
        _assert_zero_client_calls(mock_client)


# ---------------------------------------------------------------------------
# TestBatchIsolation (AC5 — one bad item never aborts the batch)
# ---------------------------------------------------------------------------


class TestBatchIsolation:
    def test_one_bad_item_does_not_abort_the_batch(self, db):
        from src.clients.intercom import IntercomAuthError

        org = _make_org(db)
        _make_integration(db, org.id)
        ok_1 = _make_feedback(db, org.id, source_metadata={"conversation_id": "conv-1"})
        bad = _make_feedback(db, org.id, source_metadata={"conversation_id": "conv-2"})
        ok_2 = _make_feedback(db, org.id, source_metadata={"conversation_id": "conv-3"})

        mock_client = _make_mock_client()
        mock_client.add_note.side_effect = [
            None,
            IntercomAuthError("no write scope"),
            None,
        ]

        result, _, _ = _run_push(
            db,
            org.id,
            [
                {"id": ok_1.id, "resolution_note": None},
                {"id": bad.id, "resolution_note": None},
                {"id": ok_2.id, "resolution_note": None},
            ],
            mock_client=mock_client,
        )

        assert result["processed"] == 3
        assert [r["status"] for r in result["results"]] == ["ok", "error", "ok"]
        assert result["results"][1]["reason"] == "missing_write_scope"

        # Both good items have their markers committed; the failed item does
        # not (stays re-runnable).
        with _fake_db_session() as fresh:
            assert (
                fresh.query(FeedbackItem).filter_by(id=ok_1.id).first().intercom_writeback_at
                is not None
            )
            assert (
                fresh.query(FeedbackItem).filter_by(id=ok_2.id).first().intercom_writeback_at
                is not None
            )
            assert (
                fresh.query(FeedbackItem).filter_by(id=bad.id).first().intercom_writeback_at
                is None
            )

    def test_prior_items_markers_survive_mid_batch_retry(self, db):
        """Per-item commit proof: [ok, 429, ok] aborts at the 429; the first
        item's marker is already committed, so the retry run (guard 3) can
        never duplicate its note."""
        from celery.exceptions import Retry
        from src.clients.intercom import IntercomTransientError

        org = _make_org(db)
        _make_integration(db, org.id)
        ok_1 = _make_feedback(db, org.id, source_metadata={"conversation_id": "conv-1"})
        bad = _make_feedback(db, org.id, source_metadata={"conversation_id": "conv-2"})
        ok_2 = _make_feedback(db, org.id, source_metadata={"conversation_id": "conv-3"})

        mock_client = _make_mock_client()
        mock_client.add_note.side_effect = [
            None,
            IntercomTransientError("rate limited"),
            None,
        ]

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        with pytest.raises(Retry):
            _run_push(
                db,
                org.id,
                [
                    {"id": ok_1.id, "resolution_note": None},
                    {"id": bad.id, "resolution_note": None},
                    {"id": ok_2.id, "resolution_note": None},
                ],
                mock_client=mock_client, task_self=task_self,
            )

        task_self.retry.assert_called_once()
        # The abort happened at item 2's note; only item 1 reached the close
        # step and item 3 was never processed.
        mock_client.close_conversation.assert_called_once()

        with _fake_db_session() as fresh:
            assert (
                fresh.query(FeedbackItem).filter_by(id=ok_1.id).first().intercom_writeback_at
                is not None
            )
            assert (
                fresh.query(FeedbackItem).filter_by(id=bad.id).first().intercom_writeback_at
                is None
            )


# ---------------------------------------------------------------------------
# TestCeleryTaskRegistration (AC6 — dispatch name pinned, registry + include)
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_task_registered_with_exact_name(self):
        """The task name is the anchor for every dispatch seam.

        dispatch-seams adds the cross-site assertion (all 5 dispatch strings
        equal this name) in its aspect; the pin here is the registry + include
        check. The module is imported first because Celery's include list is
        lazy — a task only appears in celery_app.tasks once its module has
        been imported (beat-integrity discipline, test_beat_schedule_integrity
        docstring). D1: this task is NOT beat-scheduled.
        """
        import importlib
        import types

        importlib.import_module("src.tasks.intercom_writeback")
        from src.celery_app import celery_app

        name = "src.tasks.intercom_writeback.push_resolved_writeback"

        assert name in celery_app.tasks
        # Catches the churn_playbooks failure class: a name= that lacks the
        # src. prefix registers under a different string than dispatchers use.
        assert celery_app.tasks[name].name == name
        # A task module missing from `include` is never imported by the
        # worker, so send_task raises NotRegistered in production.
        assert "src.tasks.intercom_writeback" in (celery_app.conf.include or ())

        mod = importlib.import_module("src.tasks.intercom_writeback")
        assert hasattr(mod, "push_resolved_writeback")
        # An undecorated function imports cleanly yet raises NotRegistered at
        # dispatch time; the registry checks above already exclude that, and
        # this pins the module attribute is a Task-decorated callable, not a
        # plain function.
        assert not isinstance(mod.push_resolved_writeback, types.FunctionType)

        scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
        assert name not in scheduled  # D1 — dispatched only via send_task/delay
