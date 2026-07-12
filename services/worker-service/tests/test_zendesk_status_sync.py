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

from src.models import FeedbackItem, FeedbackWorkflowEvent, Organization


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
