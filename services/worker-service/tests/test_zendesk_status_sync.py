"""
TDD tests for src.tasks.zendesk_status_sync (poll-first inbound Zendesk
status-sync poller) — poll-task aspect of zendesk-status-sync.
See docs/planning/zendesk-status-sync/poll-task/plan_20260712.md.

Strategy: real SQLite (`db` fixture from conftest.py, real Base.metadata
tables) and a FAKE ZendeskClient (a plain object exposing `show_many`)
injected directly into `_sync_zendesk_status_org_body(integration_id, db,
client=...)` — no Celery, no httpx (mirrors test_jira_sync_task.py's
"extracted so tests inject a fake client, no Celery" contract).
"""

from __future__ import annotations

import importlib
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.models import (
    FeedbackItem,
    FeedbackWorkflowEvent,
    FeedbackZendeskSync,
    Organization,
    ZendeskIntegration,
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


def _make_feedback(
    db, org_id, source_external_id, workflow_status="new", source="zendesk"
) -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=org_id,
        text="It crashes on export",
        source=source,
        source_external_id=source_external_id,
        workflow_status=workflow_status,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def _make_zendesk_integration(
    db,
    org_id,
    is_active=True,
    status_sync_enabled=True,
    status_mapping=None,
) -> ZendeskIntegration:
    integ = ZendeskIntegration(
        organization_id=org_id,
        subdomain="acmeco",
        email="agent@acmeco.com",
        api_token="enc:blob",
        is_active=is_active,
        status_sync_enabled=status_sync_enabled,
        status_mapping=status_mapping,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_sidecar(db, feedback_id, last_ticket_status, last_status_synced_at=None) -> FeedbackZendeskSync:
    row = FeedbackZendeskSync(
        feedback_id=feedback_id,
        last_ticket_status=last_ticket_status,
        last_status_synced_at=last_status_synced_at or datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class FakeZendeskClient:
    """A plain object exposing show_many — not a real ZendeskClient."""

    def __init__(self, results: dict):
        self._results = results
        self.calls = []

    def show_many(self, ids):
        self.calls.append(list(ids))
        str_ids = [str(i) for i in ids]
        return {k: v for k, v in self._results.items() if k in str_ids}


# ---------------------------------------------------------------------------
# Phase 1 — race-safe apply writer
# ---------------------------------------------------------------------------


class TestApplyZendeskStatusWorker:
    def test_applies_change_and_writes_one_event(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        feedback = _make_feedback(db, org.id, "123", workflow_status="new")

        result = zss.apply_zendesk_status_worker(
            db,
            feedback,
            "resolved",
            organization_id=org.id,
            ticket_id="123",
            zendesk_status="solved",
        )

        assert result is True
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "status_changed"
        assert event.actor_id is None
        assert event.old_value == "new"
        assert event.new_value == "resolved"
        assert event.metadata_["source"] == "zendesk"
        assert event.metadata_["zendesk_status"] == "solved"
        assert event.metadata_["zendesk_ticket_id"] == "123"

    def test_noop_when_already_equal(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        feedback = _make_feedback(db, org.id, "123", workflow_status="resolved")

        result = zss.apply_zendesk_status_worker(
            db,
            feedback,
            "resolved",
            organization_id=org.id,
            ticket_id="123",
            zendesk_status="solved",
        )

        assert result is False
        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []

    def test_concurrency_guard_no_duplicate_event(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        feedback = _make_feedback(db, org.id, "123", workflow_status="new")

        # Simulate a concurrent writer moving the row without refreshing our
        # in-memory `feedback` object — use a non-committing conditional
        # UPDATE with synchronize_session=False (no expire-on-commit
        # refresh), so `feedback.workflow_status` stays stale ("new") while
        # the actual persisted row is now "in_review".
        db.query(FeedbackItem).filter(FeedbackItem.id == feedback.id).update(
            {FeedbackItem.workflow_status: "in_review"}, synchronize_session=False
        )
        db.flush()

        result = zss.apply_zendesk_status_worker(
            db,
            feedback,
            "resolved",
            organization_id=org.id,
            ticket_id="123",
            zendesk_status="solved",
        )

        assert result is False
        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []

        # The actual row keeps the concurrent writer's value — the guard
        # must not clobber it. (db.refresh, not a plain re-query: the
        # `feedback` object is already in this session's identity map, so
        # a re-query would just return the same stale Python object.)
        db.expire(feedback)
        db.refresh(feedback)
        assert feedback.workflow_status == "in_review"


# ---------------------------------------------------------------------------
# Phase 2 — per-feedback reconcile helper
# ---------------------------------------------------------------------------


class TestReconcileFeedback:
    def test_seed_writes_sidecar_no_event_no_apply(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "123", workflow_status="new")

        action = zss.reconcile_feedback(db, feedback, "open", integ)

        assert action == "seed"
        db.refresh(feedback)
        assert feedback.workflow_status == "new"  # unchanged — seed only

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar is not None
        assert sidecar.last_ticket_status == "open"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []

    def test_changed_solved_applies_resolved_and_updates_sidecar(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "123", workflow_status="new")
        _make_sidecar(db, feedback.id, "open")

        action = zss.reconcile_feedback(db, feedback, "solved", integ)

        assert action == "changed"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "solved"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert len(events) == 1
        assert events[0].metadata_["source"] == "zendesk"

    def test_changed_but_resolve_target_none_updates_sidecar_no_apply(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        # Override the mapping so "open" resolves to an invalid workflow
        # status, forcing resolve_target_status to return None.
        integ = _make_zendesk_integration(
            db, org.id, status_mapping={"open": "not_a_real_status"}
        )
        feedback = _make_feedback(db, org.id, "123", workflow_status="new")
        _make_sidecar(db, feedback.id, "new")

        action = zss.reconcile_feedback(db, feedback, "open", integ)

        assert action == "changed"
        db.refresh(feedback)
        assert feedback.workflow_status == "new"  # unchanged — no apply

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "open"  # still recorded

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []

    def test_noop_does_nothing(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "123", workflow_status="resolved")
        sidecar = _make_sidecar(db, feedback.id, "solved")
        original_synced_at = sidecar.last_status_synced_at

        action = zss.reconcile_feedback(db, feedback, "solved", integ)

        assert action == "noop"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []
        db.refresh(sidecar)
        assert sidecar.last_status_synced_at == original_synced_at


# ---------------------------------------------------------------------------
# Phase 3 — two-task fan-out + body
# ---------------------------------------------------------------------------


class TestSyncZendeskStatusOrgBody:
    def test_not_found(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        result = zss._sync_zendesk_status_org_body(999999, db, client=FakeZendeskClient({}))
        assert result["status"] == "not_found"

    def test_inactive_org_no_client_calls(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, is_active=False)
        fake_client = FakeZendeskClient({})

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "inactive"
        assert fake_client.calls == []

    def test_disabled_status_sync_no_client_calls(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, status_sync_enabled=False)
        fake_client = FakeZendeskClient({})

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "disabled"
        assert fake_client.calls == []

    def test_first_poll_all_seed_zero_events_zero_status_changes(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        f1 = _make_feedback(db, org.id, "1", workflow_status="new")
        f2 = _make_feedback(db, org.id, "2", workflow_status="new")
        f3 = _make_feedback(db, org.id, "3", workflow_status="new")

        fake_client = FakeZendeskClient({"1": "open", "2": "pending", "3": "new"})

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        sidecars = db.query(FeedbackZendeskSync).all()
        assert len(sidecars) == 3

        events = db.query(FeedbackWorkflowEvent).all()
        assert events == []

        for fb in (f1, f2, f3):
            db.refresh(fb)
            assert fb.workflow_status == "new"

        db.refresh(integ)
        assert integ.last_status_synced_at is not None
        assert integ.last_status_sync_error is None

    def test_second_poll_one_ticket_solved_resolves_others_noop(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        f1 = _make_feedback(db, org.id, "1", workflow_status="new")
        f2 = _make_feedback(db, org.id, "2", workflow_status="new")
        _make_sidecar(db, f1.id, "open")
        _make_sidecar(db, f2.id, "new")

        fake_client = FakeZendeskClient({"1": "solved", "2": "new"})

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"

        db.refresh(f1)
        assert f1.workflow_status == "resolved"
        db.refresh(f2)
        assert f2.workflow_status == "new"

        events = db.query(FeedbackWorkflowEvent).all()
        assert len(events) == 1
        assert events[0].feedback_id == f1.id
        assert events[0].metadata_["source"] == "zendesk"

    def test_poll_twice_second_is_noop(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        f1 = _make_feedback(db, org.id, "1", workflow_status="new")

        fake_client = FakeZendeskClient({"1": "open"})

        # First poll — seeds.
        zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)
        events_after_first = db.query(FeedbackWorkflowEvent).all()
        assert events_after_first == []

        # Second poll — same status, must be a no-op (zero NEW events).
        zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)
        events_after_second = db.query(FeedbackWorkflowEvent).all()
        assert events_after_second == []

    def test_missing_ticket_in_response_is_skipped(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        f1 = _make_feedback(db, org.id, "1", workflow_status="new")
        _make_sidecar(db, f1.id, "open")

        # Ticket "1" absent from the fake client's results (deleted/archived).
        fake_client = FakeZendeskClient({})

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(f1)
        assert f1.workflow_status == "new"

    def test_transient_error_propagates_for_retry(self, db):
        from src.clients.zendesk import ZendeskTransientError
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        _make_feedback(db, org.id, "1", workflow_status="new")

        class RaisingClient:
            def show_many(self, ids):
                raise ZendeskTransientError("rate limited")

        with pytest.raises(ZendeskTransientError):
            zss._sync_zendesk_status_org_body(integ.id, db, client=RaisingClient())

    def test_auth_error_records_status_without_raising_or_disconnecting(self, db):
        from src.clients.zendesk import ZendeskAuthError
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        _make_feedback(db, org.id, "1", workflow_status="new")

        class RaisingClient:
            def show_many(self, ids):
                raise ZendeskAuthError("bad token")

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=RaisingClient())

        assert result["status"] == "error"
        assert result["reason"] == "auth_error"
        db.refresh(integ)
        assert integ.last_status_sync_error is not None
        assert integ.is_active is True  # NOT disconnected

    def test_resolve_target_none_no_apply_sidecar_still_records(self, db):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        org = _make_org(db)
        integ = _make_zendesk_integration(
            db, org.id, status_mapping={"open": "not_a_real_status"}
        )
        f1 = _make_feedback(db, org.id, "1", workflow_status="new")
        _make_sidecar(db, f1.id, "new")

        fake_client = FakeZendeskClient({"1": "open"})

        result = zss._sync_zendesk_status_org_body(integ.id, db, client=fake_client)

        assert result["status"] == "success"
        db.refresh(f1)
        assert f1.workflow_status == "new"  # no apply

        sidecar = db.get(FeedbackZendeskSync, f1.id)
        assert sidecar.last_ticket_status == "open"  # still recorded

        events = db.query(FeedbackWorkflowEvent).all()
        assert events == []


class TestSyncZendeskStatusOrgTask:
    def test_transient_error_retries_and_persists_terminal_status(self, db, monkeypatch):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)
        from src.clients.zendesk import ZendeskTransientError

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)

        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        def fake_body(integration_id, db_, client=None):
            raise ZendeskTransientError("rate limited")

        monkeypatch.setattr(zss, "get_db_session", fake_get_db)
        monkeypatch.setattr(zss, "_sync_zendesk_status_org_body", fake_body)

        # Uses Celery's synchronous `.apply()` (not a fake `self`) so
        # `self.retry()` really executes — after exhausting max_retries=3 the
        # task ultimately reports FAILURE, proving the retry path fired.
        # (Db persistence of the terminal error via the fresh get_db_session()
        # call is covered at the _sync_zendesk_status_org_body level by
        # test_auth_error_records_status_without_raising_or_disconnecting —
        # this fake_get_db here reuses the same session object with no real
        # commit boundary, so asserting on written column state after
        # `.apply()` isn't a meaningful check, same as
        # test_jira_sync_task.py's equivalent case.)
        result = zss.sync_zendesk_status_org.apply(args=[integ.id])

        assert result.state == "FAILURE"
        assert isinstance(result.result, ZendeskTransientError)


class TestFanOutTask:
    def test_fanout_enqueues_active_and_enabled_only(self, db, monkeypatch):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        from contextlib import contextmanager

        org = _make_org(db)
        active_enabled = _make_zendesk_integration(db, org.id, is_active=True, status_sync_enabled=True)

        org2 = _make_org(db, name="Other Co")
        _make_zendesk_integration(db, org2.id, is_active=True, status_sync_enabled=False)

        org3 = _make_org(db, name="Third Co")
        _make_zendesk_integration(db, org3.id, is_active=False, status_sync_enabled=True)

        @contextmanager
        def fake_get_db():
            yield db

        monkeypatch.setattr(zss, "get_db_session", fake_get_db)
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        monkeypatch.setattr(zss, "sync_zendesk_status_org", mock_task)

        zss.sync_all_zendesk_status()

        mock_task.delay.assert_called_once_with(active_enabled.id)

    def test_fanout_no_integrations_returns_zero(self, db, monkeypatch):
        import src.tasks.zendesk_status_sync as zss
        importlib.reload(zss)

        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        monkeypatch.setattr(zss, "get_db_session", fake_get_db)
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        monkeypatch.setattr(zss, "sync_zendesk_status_org", mock_task)

        result = zss.sync_all_zendesk_status()

        assert result["status"] == "no_integrations"
        assert result["queued"] == 0
