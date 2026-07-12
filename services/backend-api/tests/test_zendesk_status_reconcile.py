"""
TDD tests for src.services.zendesk_status_reconcile (webhook-realtime aspect
of zendesk-status-sync) — the backend-side mirror of the worker's
`reconcile_feedback` (services/worker-service/src/tasks/zendesk_status_sync.py),
used by the Zendesk webhook receiver for immediate, single-ticket reconcile.
See docs/planning/zendesk-status-sync/webhook-realtime/plan_20260712.md Phase 1.

Design tasks baked into this module (see dig.md):
  1. source tag: the emitted `status_changed` event's metadata must carry
     {"source": "zendesk", "zendesk_status": ..., "zendesk_ticket_id": ...}.
  2. race-safe apply: a conditional `UPDATE ... WHERE workflow_status=<old>`
     guard — a concurrent writer (e.g. the poll task) that already moved the
     row must result in NO event from this call.
  3. (anti-spoof branching lives in the route, not here.)
"""
from __future__ import annotations

from datetime import datetime

from src.models import (
    FeedbackItem,
    FeedbackWorkflowEvent,
    FeedbackZendeskSync,
    Organization,
    ZendeskIntegration,
)
from src.services.zendesk_status_reconcile import _upsert_sidecar, reconcile_ticket


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


def _events_for(db, feedback_id):
    return (
        db.query(FeedbackWorkflowEvent)
        .filter(FeedbackWorkflowEvent.feedback_id == feedback_id)
        .all()
    )


class TestReconcileTicketNoFeedback:
    def test_no_linked_feedback_returns_no_feedback(self, db):
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)

        result = reconcile_ticket(db, integ, 999, "solved")

        assert result == "no_feedback"

    def test_no_linked_feedback_in_other_org_is_ignored(self, db):
        org1 = _make_org(db, "Org1")
        org2 = _make_org(db, "Org2")
        integ = _make_zendesk_integration(db, org1.id)
        # Feedback with the same ticket id but scoped to a different org.
        _make_feedback(db, org2.id, "35436", workflow_status="new")

        result = reconcile_ticket(db, integ, 35436, "solved")

        assert result == "no_feedback"


class TestReconcileTicketSeed:
    def test_first_observation_seeds_sidecar_no_apply(self, db):
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="new")

        result = reconcile_ticket(db, integ, 35436, "open")

        assert result == "seed"
        db.refresh(feedback)
        assert feedback.workflow_status == "new"

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar is not None
        assert sidecar.last_ticket_status == "open"

        assert _events_for(db, feedback.id) == []


class TestReconcileTicketNoop:
    def test_same_status_is_noop(self, db):
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="new")
        _make_sidecar(db, feedback.id, "open")

        result = reconcile_ticket(db, integ, 35436, "open")

        assert result == "noop"
        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert _events_for(db, feedback.id) == []


class TestReconcileTicketChanged:
    def test_changed_solved_applies_resolved_with_source_tagged_event(self, db):
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        result = reconcile_ticket(db, integ, 35436, "solved")

        assert result == "changed"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "solved"

        events = _events_for(db, feedback.id)
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "status_changed"
        assert event.old_value == "in_review"
        assert event.new_value == "resolved"
        assert event.actor_id is None
        assert event.metadata_["source"] == "zendesk"
        assert event.metadata_["zendesk_status"] == "solved"
        assert event.metadata_["zendesk_ticket_id"] == "35436"

    def test_changed_unknown_target_status_no_apply_but_sidecar_updated(self, db):
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="new")
        _make_sidecar(db, feedback.id, "open")

        # status_mapping override that maps "solved" to an invalid workflow
        # status -- resolve_target_status must return None and no apply
        # should occur.
        integ.status_mapping = {"solved": "not_a_real_status"}
        db.commit()

        result = reconcile_ticket(db, integ, 35436, "solved")

        assert result == "changed"
        db.refresh(feedback)
        assert feedback.workflow_status == "new"

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "solved"
        assert _events_for(db, feedback.id) == []

    def test_changed_target_equals_current_status_is_apply_noop_no_event(self, db):
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="resolved")
        _make_sidecar(db, feedback.id, "open")

        result = reconcile_ticket(db, integ, 35436, "solved")

        assert result == "changed"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert _events_for(db, feedback.id) == []


class TestReconcileTicketRaceSafety:
    def test_concurrent_writer_wins_no_duplicate_event(self, db):
        """
        Simulate a concurrent writer (e.g. the poll task, or a second
        webhook delivery) moving the row between when this call reads the
        feedback and when it would apply the change. The conditional
        UPDATE ... WHERE workflow_status=<old> guard must see 0 rows
        affected and write NO event.
        """
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        # Concurrent writer moves the row without going through this
        # session's ORM-tracked `feedback` object (synchronize_session=False
        # so the in-memory object the reconcile call will load is stale).
        db.query(FeedbackItem).filter(FeedbackItem.id == feedback.id).update(
            {FeedbackItem.workflow_status: "resolved"}, synchronize_session=False
        )
        db.flush()

        result = reconcile_ticket(db, integ, 35436, "solved")

        assert result == "changed"
        events = _events_for(db, feedback.id)
        assert events == []

        db.expire(feedback)
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        # Sidecar is still updated to the freshly observed status even
        # though the apply lost the race.
        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "solved"

    def test_idempotent_second_call_same_change_is_noop(self, db):
        """Calling reconcile_ticket twice for the SAME change must write
        exactly one event total (second call sees fetched==stored -> noop)."""
        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        first = reconcile_ticket(db, integ, 35436, "solved")
        second = reconcile_ticket(db, integ, 35436, "solved")

        assert first == "changed"
        assert second == "noop"
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1


class TestUpsertSidecarConcurrentSeed:
    """
    Fix wave: the FeedbackZendeskSync sidecar row is INSERTed on first
    observation ("seed"). If the poll task (worker-service) and this
    webhook path both make the first-ever observation of the same ticket
    in the same instant, both would see `row is None` and both attempt to
    INSERT the same feedback_id PK — the loser must not raise
    IntegrityError.
    """

    def test_concurrent_first_observation_insert_conflict_does_not_raise(
        self, db, monkeypatch
    ):
        org = _make_org(db)
        feedback = _make_feedback(db, org.id, "35436", workflow_status="new")

        # The "winner" (e.g. the worker's poll task, in a concurrent
        # transaction) already committed the sidecar row for this
        # feedback_id.
        _make_sidecar(db, feedback.id, "open")

        # Force this call's pre-insert existence check to report None —
        # exactly what it would have seen a moment before the winner's
        # commit landed.
        monkeypatch.setattr(db, "get", lambda *a, **k: None)

        # Must not raise IntegrityError.
        _upsert_sidecar(db, feedback.id, "pending")

        rows = (
            db.query(FeedbackZendeskSync)
            .filter(FeedbackZendeskSync.feedback_id == feedback.id)
            .all()
        )
        assert len(rows) == 1
        # Loser does nothing — winner's row remains authoritative (mirrors
        # Postgres ON CONFLICT (feedback_id) DO NOTHING).
        assert rows[0].last_ticket_status == "open"

        # Session must remain usable after the swallowed IntegrityError.
        assert db.query(Organization).filter(Organization.id == org.id).first() is not None
