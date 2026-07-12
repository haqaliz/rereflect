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
