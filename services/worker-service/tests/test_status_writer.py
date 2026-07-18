"""
TDD tests for src.services.status_writer.apply_status_change_worker —
status-sync-realtime-mapping/status-writer-race-guard aspect.
See docs/planning/status-sync-realtime-mapping/status-writer-race-guard/spec.md.

Strategy: real SQLite (`db` fixture from conftest.py, real Base.metadata
tables), no Celery. Mirrors the race-safe pattern already proven in
tests/test_zendesk_status_sync.py::TestApplyZendeskStatusWorker (the
`old_status` mismatch is simulated via a non-committing conditional UPDATE
with synchronize_session=False so the in-memory ORM object stays stale).

Unlike the Zendesk applier (which reads `feedback.workflow_status` itself),
`apply_status_change_worker` takes the caller-observed `old_status` as an
explicit keyword — see spec.md's "the guard is meaningful" rationale.
"""

from __future__ import annotations

from src.models import FeedbackItem, FeedbackWorkflowEvent, Organization
from src.services.status_writer import apply_status_change_worker


def _make_org(db, name="Acme Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_feedback(db, org_id, workflow_status="new") -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=org_id,
        text="It crashes on export",
        source="jira",
        source_external_id="PROJ-1",
        workflow_status=workflow_status,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


class TestApplyStatusChangeWorker:
    def test_happy_path_applies_change_and_writes_one_event(self, db):
        org = _make_org(db)
        feedback = _make_feedback(db, org.id, workflow_status="new")

        result = apply_status_change_worker(
            db,
            feedback,
            "in_review",
            old_status="new",
            organization_id=org.id,
            actor_label="jira-sync",
            metadata={"source": "jira", "jira_status_category": "indeterminate"},
        )

        assert result is True
        db.refresh(feedback)
        assert feedback.workflow_status == "in_review"

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
        assert event.new_value == "in_review"
        assert event.organization_id == org.id
        assert event.metadata_["source"] == "jira"

    def test_noop_on_equal_status_writes_zero_events(self, db):
        org = _make_org(db)
        feedback = _make_feedback(db, org.id, workflow_status="resolved")

        result = apply_status_change_worker(
            db,
            feedback,
            "resolved",
            old_status="resolved",
            organization_id=org.id,
            actor_label="asana-sync",
            metadata={"source": "asana"},
        )

        assert result is False
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []

    def test_stale_observed_old_status_no_duplicate_event(self, db):
        """
        The caller observed old_status='new', but a concurrent writer (the
        15-min poll, or a real-time webhook) already moved the row to
        'resolved' since the caller last read it. The guarded UPDATE's WHERE
        clause (workflow_status='new') matches zero rows, so this call must
        write NO event, return False, and must NOT clobber the concurrent
        writer's 'resolved' value with 'in_review'.
        """
        org = _make_org(db)
        feedback = _make_feedback(db, org.id, workflow_status="new")

        # Simulate a concurrent writer moving the row without refreshing our
        # in-memory `feedback` object — a non-committing conditional UPDATE
        # with synchronize_session=False leaves feedback.workflow_status
        # stale ("new") while the persisted row is now "resolved".
        db.query(FeedbackItem).filter(FeedbackItem.id == feedback.id).update(
            {FeedbackItem.workflow_status: "resolved"}, synchronize_session=False
        )
        db.flush()

        result = apply_status_change_worker(
            db,
            feedback,
            "in_review",
            old_status="new",
            organization_id=org.id,
            actor_label="jira-sync",
            metadata={"source": "jira"},
        )

        assert result is False

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []

        # The row keeps the concurrent writer's value — the guard must not
        # clobber it. db.expire + db.refresh (not a plain re-query): the
        # `feedback` object is already in this session's identity map.
        db.expire(feedback)
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

    def test_multi_tenancy_organization_id_in_where_clause(self, db):
        """
        A row with the right id but the WRONG organization_id must never be
        moved — defense in depth per spec's multi-tenancy requirement.
        """
        org = _make_org(db, name="Org A")
        other_org = _make_org(db, name="Org B")
        feedback = _make_feedback(db, org.id, workflow_status="new")

        result = apply_status_change_worker(
            db,
            feedback,
            "in_review",
            old_status="new",
            organization_id=other_org.id,
            actor_label="jira-sync",
            metadata={"source": "jira"},
        )

        assert result is False
        db.expire(feedback)
        db.refresh(feedback)
        assert feedback.workflow_status == "new"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == feedback.id)
            .all()
        )
        assert events == []
