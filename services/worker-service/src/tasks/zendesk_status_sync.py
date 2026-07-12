"""
Inbound Zendesk status-sync poller (zendesk-status-sync/poll-task).
See docs/planning/zendesk-status-sync/poll-task/plan_20260712.md.
Mirrors src/tasks/jira_sync.py's two-task fan-out shape.

Tasks:
  sync_all_zendesk_status  — fan-out over orgs with active AND
                              status_sync_enabled Zendesk integrations
  sync_zendesk_status_org  — per-org retryable sync (max_retries=3), thin
                              wrapper around `_sync_zendesk_status_org_body`

Core (Celery-free, tested directly):
  apply_zendesk_status_worker(db, feedback, new_status, *, organization_id,
  ticket_id, zendesk_status) -> bool
    The single point that changes `workflow_status` and emits exactly ONE
    source-tagged `FeedbackWorkflowEvent`. No-ops (returns False, writes
    nothing) when `new_status` already equals the feedback's current
    workflow_status. RACE-SAFE: applies the change via a conditional
    `UPDATE ... WHERE id=? AND organization_id=? AND workflow_status=<old>`;
    if a concurrent writer already moved the row (0 rows affected), returns
    False and writes no event — the other writer's own apply is the sole
    source of truth for that transition, so no duplicate/conflicting event
    is ever written here. This guard is new here (jira_sync's
    `apply_status_change_worker` has no equivalent — see this aspect's
    plan Phase 1 for why polling introduces a same-row race two orgs'
    beats could otherwise hit).

  reconcile_feedback / _sync_zendesk_status_org_body — added in later
  phases of this module (see plan Phases 2-3).

The worker cannot import backend-api — it uses its own copy of the pure
reconcile core (src/services/zendesk_status_core.py, a verbatim copy of
services/backend-api/src/services/zendesk_status_core.py) and its own
`ZendeskClient` (src/clients/zendesk.py), and mirrors the model columns it
needs (src/models/__init__.py ZendeskIntegration / FeedbackZendeskSync).

Outbound webhook dispatch on a Zendesk-driven status change is explicitly
DEFERRED (mirrors jira_sync.py) — this task writes the timeline event +
status change only.
"""

from __future__ import annotations

from datetime import datetime


# ---------------------------------------------------------------------------
# Phase 1 — race-safe apply writer (worker cannot import backend-api's
# apply_status_change / workflow_service)
# ---------------------------------------------------------------------------


def apply_zendesk_status_worker(
    db,
    feedback,
    new_status: str,
    *,
    organization_id: int,
    ticket_id,
    zendesk_status: str,
) -> bool:
    """
    Apply a workflow_status change driven by Zendesk polling and write
    exactly ONE FeedbackWorkflowEvent timeline row (actor_id=None — no
    acting user).

    No-ops (returns False, writes nothing) when `new_status` already equals
    the feedback's current workflow_status.

    CONCURRENCY GUARD: the write is a conditional
    `UPDATE ... WHERE id=? AND organization_id=? AND workflow_status=<old>`.
    If a concurrent writer already moved this row since `feedback` was
    loaded (0 rows affected), this returns False and writes NO event — the
    other writer's own apply is the sole source of truth for that
    transition, so no duplicate/conflicting event is ever written here.

    NOTE: this deliberately does NOT dispatch outbound
    `feedback.status_changed` webhooks — see this module's docstring.
    """
    from src.models import FeedbackItem, FeedbackWorkflowEvent

    old_status = feedback.workflow_status
    if old_status == new_status:
        return False

    rows = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == feedback.id,
            FeedbackItem.organization_id == organization_id,
            FeedbackItem.workflow_status == old_status,
        )
        .update({FeedbackItem.workflow_status: new_status}, synchronize_session=False)
    )
    if rows == 0:
        # Someone else moved it — no duplicate event.
        return False

    # Keep the in-memory object in sync with the write we just made (the
    # conditional UPDATE above used synchronize_session=False, so the ORM
    # instance's attribute is stale until we set it explicitly).
    feedback.workflow_status = new_status

    event = FeedbackWorkflowEvent(
        feedback_id=feedback.id,
        organization_id=organization_id,
        actor_id=None,
        event_type="status_changed",
        old_value=old_status,
        new_value=new_status,
        metadata_={
            "source": "zendesk",
            "zendesk_status": zendesk_status,
            "zendesk_ticket_id": str(ticket_id),
        },
        created_at=datetime.utcnow(),
    )
    db.add(event)
    # Flush immediately — mirrors the conditional UPDATE above, which is
    # already visible to same-session readers without a flush; the event
    # insert needs an explicit flush to be equally visible (this session
    # runs with autoflush disabled).
    db.flush()
    return True
