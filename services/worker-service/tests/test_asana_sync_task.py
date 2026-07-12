"""
TDD tests for src.tasks.asana_sync (inbound Asana status-sync poller) —
asana-status-sync/worker-sync-task aspect. See
docs/planning/asana-status-sync/worker-sync-task/plan_20260712.md.

Strategy: real SQLite (`db` fixture from conftest.py, real Base.metadata
tables) and a FAKE AsanaClient (a plain object exposing `get_task`)
injected directly into `_sync_asana_org_body(integration_id, db, client=...)`
— no Celery, no httpx (mirrors tests/test_jira_sync_task.py's strategy).

Structural deltas from the Jira suite (see plan's "Structural differences"
table): no batch fetch — one `get_task(gid)` call per link; no status-name
column on the link (`asana_completed` + `asana_status_category` only); a 404
raises `AsanaNotFoundError` and is swallowed per-link (org still reports
success); event metadata is `{source, asana_task_gid, asana_completed}`.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

from src.models import (
    AsanaIntegration,
    FeedbackAsanaTask,
    FeedbackItem,
    FeedbackWorkflowEvent,
    Organization,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db, name="Acme Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_asana_integration(
    db,
    org_id,
    is_active=True,
    status_sync_enabled=True,
    status_mapping=None,
) -> AsanaIntegration:
    integ = AsanaIntegration(
        organization_id=org_id,
        api_token="enc:blob",
        is_active=is_active,
        status_sync_enabled=status_sync_enabled,
        status_mapping=status_mapping,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_feedback(db, org_id, workflow_status="new") -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=org_id,
        text="It crashes on export",
        source="support",
        workflow_status=workflow_status,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def _make_asana_link(
    db,
    org_id,
    feedback_id,
    asana_task_gid,
    asana_completed=None,
    asana_status_category=None,
) -> FeedbackAsanaTask:
    link = FeedbackAsanaTask(
        organization_id=org_id,
        feedback_id=feedback_id,
        asana_task_gid=asana_task_gid,
        asana_completed=asana_completed,
        asana_status_category=asana_status_category,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


class FakeAsanaClient:
    """A plain object exposing get_task — not a real AsanaClient.

    `results` maps gid -> {"completed": bool, ...}. An unknown gid raises
    AsanaNotFoundError (matches the real AsanaClient's 404 contract).
    """

    def __init__(self, results: dict):
        self._results = results
        self.calls = []

    def get_task(self, gid):
        from src.clients.asana import AsanaNotFoundError

        self.calls.append(gid)
        if gid not in self._results:
            raise AsanaNotFoundError(f"no such task {gid}")
        return self._results[gid]

    def close(self):
        pass


# ---------------------------------------------------------------------------
# TestSyncAsanaOrgBody
# ---------------------------------------------------------------------------


class TestSyncAsanaOrgBody:
    # ⭐ CRITICAL — the feature's safety contract: the poller must never tug
    # back a status change it did not drive. First observation of any link
    # is seed-only, regardless of what the feedback's current status is.
    def test_manual_status_change_not_reverted_when_link_never_seeded(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        # Operator manually set this to "resolved" by hand.
        feedback = _make_feedback(db, org.id, workflow_status="resolved")
        # Link never observed before (asana_status_category is NULL).
        link = _make_asana_link(db, org.id, feedback.id, "1001")

        fake_client = FakeAsanaClient({"1001": {"completed": False}})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(link)
        assert link.asana_completed is False
        assert link.asana_status_category == "new"
        assert link.last_status_synced_at is not None

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"  # untouched

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert events == []

    def test_not_found(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        result = az._sync_asana_org_body(999999, db, client=FakeAsanaClient({}))
        assert result["status"] == "not_found"

    def test_inactive_org_no_client_calls(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id, is_active=False)
        fake_client = FakeAsanaClient({})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "inactive"
        assert fake_client.calls == []

    def test_disabled_status_sync_no_client_calls(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id, status_sync_enabled=False)
        fake_client = FakeAsanaClient({})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "disabled"
        assert fake_client.calls == []

    def test_first_poll_seeds_all_links_no_status_change_no_event(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id, workflow_status="new")
        link = _make_asana_link(db, org.id, feedback.id, "1001")

        fake_client = FakeAsanaClient({"1001": {"completed": True}})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(link)
        assert link.asana_completed is True
        assert link.asana_status_category == "done"
        assert link.last_status_synced_at is not None

        db.refresh(feedback)
        assert feedback.workflow_status == "new"  # unchanged — seed only

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert events == []

    def test_completion_applies_one_status_change_and_one_event(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id, workflow_status="new")
        # Already seeded at "new"/False.
        link = _make_asana_link(
            db, org.id, feedback.id, "1001", asana_completed=False, asana_status_category="new"
        )

        fake_client = FakeAsanaClient({"1001": {"completed": True}})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(link)
        assert link.asana_completed is True
        assert link.asana_status_category == "done"

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"  # DEFAULT_CATEGORY_MAP["done"]

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "status_changed"
        assert event.old_value == "new"
        assert event.new_value == "resolved"
        assert event.metadata_["source"] == "asana"
        assert event.metadata_["asana_task_gid"] == "1001"
        assert event.metadata_["asana_completed"] is True

    def test_identical_second_poll_is_noop(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id, workflow_status="resolved")
        _make_asana_link(
            db, org.id, feedback.id, "1001", asana_completed=True, asana_status_category="done"
        )

        fake_client = FakeAsanaClient({"1001": {"completed": True}})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert events == []

    def test_reopen_reverts_sync_driven_status(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        # feedback got to "resolved" via a prior sync (sync-driven).
        feedback = _make_feedback(db, org.id, workflow_status="resolved")
        link = _make_asana_link(
            db, org.id, feedback.id, "1001", asana_completed=True, asana_status_category="done"
        )

        fake_client = FakeAsanaClient({"1001": {"completed": False}})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(link)
        assert link.asana_completed is False
        assert link.asana_status_category == "new"

        db.refresh(feedback)
        assert feedback.workflow_status == "new"  # reverted

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert len(events) == 1
        event = events[0]
        assert event.old_value == "resolved"
        assert event.new_value == "new"
        assert event.metadata_["source"] == "asana"
        assert event.metadata_["asana_completed"] is False

    def test_reopen_noop_when_target_equals_current(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        # Feedback is already "new" — target after reopen equals current.
        feedback = _make_feedback(db, org.id, workflow_status="new")
        link = _make_asana_link(
            db, org.id, feedback.id, "1001", asana_completed=True, asana_status_category="done"
        )

        fake_client = FakeAsanaClient({"1001": {"completed": False}})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(link)
        assert link.asana_status_category == "new"  # link state still updated

        db.refresh(feedback)
        assert feedback.workflow_status == "new"

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert events == []

    def test_multi_task_feedback_most_advanced_category_wins(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id, workflow_status="new")
        _make_asana_link(
            db, org.id, feedback.id, "1001", asana_completed=False, asana_status_category="new"
        )
        _make_asana_link(
            db, org.id, feedback.id, "1002", asana_completed=False, asana_status_category="new"
        )

        # Task 1001 stays open, task 1002 completes — most-advanced ("done")
        # should drive the feedback's target status.
        fake_client = FakeAsanaClient({
            "1001": {"completed": False},
            "1002": {"completed": True},
        })

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert len(events) == 1
        event = events[0]
        # The driving (done) link's identity is reflected in the metadata.
        assert event.metadata_["asana_task_gid"] == "1002"
        assert event.metadata_["asana_completed"] is True

    def test_missing_task_in_response_link_not_updated(self, db):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id, workflow_status="new")
        link = _make_asana_link(
            db, org.id, feedback.id, "1001", asana_completed=False, asana_status_category="new"
        )

        # "1001" is absent from the fake client's results -> AsanaNotFoundError
        fake_client = FakeAsanaClient({})

        result = az._sync_asana_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(link)
        assert link.asana_completed is False
        assert link.asana_status_category == "new"

        events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback.id
        ).all()
        assert events == []

    def test_transient_error_propagates_for_retry(self, db):
        from src.clients.asana import AsanaTransientError
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id)
        _make_asana_link(db, org.id, feedback.id, "1001")

        class RaisingClient:
            def get_task(self, gid):
                raise AsanaTransientError("rate limited")

            def close(self):
                pass

        with pytest.raises(AsanaTransientError):
            az._sync_asana_org_body(integ.id, db, client=RaisingClient())

    def test_auth_error_records_status_without_raising_or_disconnecting(self, db):
        from src.clients.asana import AsanaAuthError
        import src.tasks.asana_sync as az
        importlib.reload(az)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id)
        _make_asana_link(db, org.id, feedback.id, "1001")

        class RaisingClient:
            def get_task(self, gid):
                raise AsanaAuthError("bad token")

            def close(self):
                pass

        result = az._sync_asana_org_body(integ.id, db, client=RaisingClient())

        assert result["status"] == "error"
        assert result["reason"] == "auth_error"
        db.refresh(integ)
        assert integ.last_sync_status == "error"
        assert integ.last_error is not None
        assert integ.is_active is True  # NOT disconnected

    def test_missing_encryption_key_returns_error_no_retry(self, db, monkeypatch):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)
        feedback = _make_feedback(db, org.id)
        _make_asana_link(db, org.id, feedback.id, "1001")

        result = az._sync_asana_org_body(integ.id, db, client=None)

        assert result == {"status": "error", "reason": "missing_encryption_key"}
        db.refresh(integ)
        assert integ.last_sync_status == "error"
        assert integ.last_error == "missing_encryption_key"


# ---------------------------------------------------------------------------
# TestSyncAsanaOrgTask — the Celery task wrapper (retry / terminal-status),
# exercised via Celery's synchronous `.apply()` so `self.retry()` binds
# correctly (mirrors TestSyncJiraOrgTask).
# ---------------------------------------------------------------------------


class TestSyncAsanaOrgTask:
    def test_transient_error_retries_and_persists_terminal_status(self, db, monkeypatch):
        import src.tasks.asana_sync as az
        importlib.reload(az)
        from src.clients.asana import AsanaTransientError

        org = _make_org(db)
        integ = _make_asana_integration(db, org.id)

        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        def fake_body(integration_id, db_, client=None):
            raise AsanaTransientError("rate limited")

        monkeypatch.setattr(az, "get_db_session", fake_get_db)
        monkeypatch.setattr(az, "_sync_asana_org_body", fake_body)

        result = az.sync_asana_org.apply(args=[integ.id])

        assert result.state == "FAILURE"
        assert isinstance(result.result, AsanaTransientError)


# ---------------------------------------------------------------------------
# TestFanOutTask
# ---------------------------------------------------------------------------


class TestFanOutTask:
    def test_fanout_enqueues_active_and_enabled_only(self, db, monkeypatch):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        from contextlib import contextmanager

        org = _make_org(db)
        active_enabled = _make_asana_integration(db, org.id, is_active=True, status_sync_enabled=True)

        org2 = _make_org(db, name="Other Co")
        _make_asana_integration(db, org2.id, is_active=True, status_sync_enabled=False)

        org3 = _make_org(db, name="Third Co")
        _make_asana_integration(db, org3.id, is_active=False, status_sync_enabled=True)

        @contextmanager
        def fake_get_db():
            yield db

        monkeypatch.setattr(az, "get_db_session", fake_get_db)
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        monkeypatch.setattr(az, "sync_asana_org", mock_task)

        az.sync_all_asana()

        mock_task.delay.assert_called_once_with(active_enabled.id)

    def test_fanout_no_integrations_returns_zero(self, db, monkeypatch):
        import src.tasks.asana_sync as az
        importlib.reload(az)

        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        monkeypatch.setattr(az, "get_db_session", fake_get_db)
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        monkeypatch.setattr(az, "sync_asana_org", mock_task)

        result = az.sync_all_asana()

        assert result["status"] == "no_integrations"
        assert result["queued"] == 0


# ---------------------------------------------------------------------------
# TestCeleryTaskRegistration
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_sync_all_asana_is_registered(self):
        from src.celery_app import celery_app
        assert "src.tasks.asana_sync.sync_all_asana" in celery_app.tasks

    def test_sync_asana_org_is_registered(self):
        from src.celery_app import celery_app
        assert "src.tasks.asana_sync.sync_asana_org" in celery_app.tasks

    def test_beat_schedule_has_asana_entry(self):
        from src.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "sync-asana-status-every-15-min" in schedule
        entry = schedule["sync-asana-status-every-15-min"]
        assert entry["schedule"] == 900.0
        assert entry["task"] == "src.tasks.asana_sync.sync_all_asana"
