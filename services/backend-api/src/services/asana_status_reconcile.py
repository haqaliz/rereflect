"""
Backend-side reconcile port for inbound Asana status-sync
(status-sync-realtime-mapping/asana-webhook aspect).

This is the backend-api mirror of the worker poller's `_sync_asana_org_body`
(services/worker-service/src/tasks/asana_sync.py) — used by the Asana
webhook receiver (src/api/routes/asana_webhook.py) to reconcile a SINGLE
task's freshly-observed `completed` state immediately on a verified event
delivery, instead of waiting for the 15-minute poll. Mirrors
src/services/jira_status_reconcile.py one-for-one (see that module's
docstring for the full architectural rationale — inline guarded UPDATE
against the shared, pure `status_sync_core`, duplicated here because the
worker cannot be imported from backend-api).

Like Jira's `FeedbackJiraIssue` (and unlike Zendesk's single-ticket-per-
feedback sidecar), `FeedbackAsanaTask` already stores the last-observed
state directly on each link row (`asana_completed` / `asana_status_category`
/ `last_status_synced_at`) — one feedback item can have MULTIPLE linked
Asana tasks. So the reconcile here mirrors the poller exactly:

  1. Look up every `FeedbackAsanaTask` link for the freshly-observed
     `asana_task_gid`, scoped to this org.
  2. For each link, `status_sync_core.decide_link_update` decides
     'seed' / 'noop' / 'changed' by comparing the freshly-computed category
     (`asana_adapter.asana_category(completed)`) against the link's own
     last-stored category. The link's asana_completed/asana_status_category/
     last_status_synced_at are updated for BOTH 'seed' and 'changed' (never
     for 'noop') — this closes the idempotency window: a duplicate/stale
     redelivery of the SAME completion state sees
     `fetched_category == link.asana_status_category` on the second call
     and is a pure noop, writing nothing.
  3. For every feedback whose link just recorded 'changed', the target
     status is resolved from the MOST ADVANCED category across THAT
     feedback's live links (status_sync_core.most_advanced) — exactly the
     poller's multi-task-per-feedback rule.
  4. The apply is a RACE-SAFE conditional
     `UPDATE feedback_items SET workflow_status=:new WHERE id=:id AND
     organization_id=:org AND workflow_status=:old`
     (`_apply_asana_status` below, mirroring
     `jira_status_reconcile._apply_jira_status` /
     `zendesk_status_reconcile._apply_zendesk_status` verbatim). If a
     concurrent writer (the poll task, or a second webhook delivery)
     already moved the row since `feedback` was loaded, 0 rows are affected
     and NO event is written.

`reconcile_task(db, integ, asana_task_gid, completed) -> dict` returns:
  - {"action": "no_feedback"} -- no FeedbackAsanaTask link matches this
        task gid for this org. Caller ACKs 200; nothing written.
  - {"action": "seed"}        -- every touched link was a first observation.
        Link fields are written; workflow_status is left untouched.
  - {"action": "noop"}        -- every touched link's fetched category
        equals its already-stored category. Nothing is written at all.
  - {"action": "changed", "status_changes": N} -- at least one link
        recorded a genuine category change. N is the number of feedback
        items whose workflow_status was actually moved (0 if the resolved
        target was None/unmapped, already equal, or lost the race).

Design task (source tag): mirrors jira_status_reconcile.py --
`metadata={"source": "asana", "asana_task_gid": ..., "asana_completed": ...}`
is threaded through explicitly via `workflow_service.create_workflow_event`.

Outbound webhook dispatch is explicitly NOT called here -- outbound is
deferred (mirrors the poll task's docstring).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.models.asana_integration import AsanaIntegration, FeedbackAsanaTask
from src.models.feedback import FeedbackItem
from src.services.asana_adapter import asana_category
from src.services.status_sync_core import decide_link_update, most_advanced, resolve_target_status
from src.services.workflow_service import create_workflow_event


def _apply_asana_status(
    db: Session,
    feedback: FeedbackItem,
    new_status: str,
    *,
    organization_id: int,
    old_status: str,
    asana_task_gid: Optional[str],
    asana_completed: Optional[bool],
) -> bool:
    """
    Apply a workflow_status change driven by an Asana webhook and write
    exactly ONE FeedbackWorkflowEvent timeline row (actor_id=None -- no
    acting user), tagged with source="asana" metadata.

    No-ops (returns False, writes nothing) when `new_status` already equals
    `old_status` (the CALLER-observed value -- see reconcile_task).

    RACE-SAFE: the write is a conditional
    `UPDATE ... WHERE id=? AND organization_id=? AND workflow_status=<old_status>`.
    If a concurrent writer already moved this row since the caller observed
    `old_status` (0 rows affected), this returns False and writes NO event --
    mirrors `jira_status_reconcile._apply_jira_status` verbatim (the worker
    cannot be imported from backend-api -- see module docstring).
    """
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
        # Someone else moved it (the poll task, or a concurrent webhook
        # delivery) -- no duplicate/conflicting event.
        return False

    # Keep the in-memory object in sync with the write we just made (the
    # conditional UPDATE above used synchronize_session=False).
    feedback.workflow_status = new_status

    create_workflow_event(
        db,
        feedback.id,
        organization_id,
        None,
        "status_changed",
        old_value=old_status,
        new_value=new_status,
        metadata={
            "source": "asana",
            "asana_task_gid": asana_task_gid,
            "asana_completed": asana_completed,
        },
    )
    db.flush()
    return True


def reconcile_task(
    db: Session,
    integ: AsanaIntegration,
    asana_task_gid: Any,
    completed: bool,
) -> Dict[str, Any]:
    """
    Reconcile one Asana task's freshly-observed `completed` state onto every
    feedback item it's linked to (immediate, single-task webhook path -- see
    module docstring for the full contract).

    Matches links by `asana_task_gid`, scoped to `integ.organization_id`.
    """
    category = asana_category(completed)
    label = "Completed" if completed else "Open"

    links = (
        db.query(FeedbackAsanaTask)
        .filter(
            FeedbackAsanaTask.organization_id == integ.organization_id,
            FeedbackAsanaTask.asana_task_gid == str(asana_task_gid),
        )
        .all()
    )
    if not links:
        return {"action": "no_feedback"}

    actions = []
    changed_feedback_ids: set = set()

    for link in links:
        action, _name, fetched_category = decide_link_update(
            category, label, link.asana_status_category
        )
        actions.append(action)
        if action == "noop":
            continue

        link.asana_completed = completed
        link.asana_status_category = fetched_category
        link.last_status_synced_at = datetime.utcnow()

        if action == "changed":
            changed_feedback_ids.add(link.feedback_id)

    db.flush()

    if not changed_feedback_ids:
        # Every touched link was either 'noop' (already-observed state --
        # closes the idempotency window for duplicate/stale deliveries) or
        # 'seed' (first observation -- never moves workflow_status).
        if any(a == "seed" for a in actions):
            return {"action": "seed"}
        return {"action": "noop"}

    status_changes = 0
    for feedback_id in changed_feedback_ids:
        feedback = (
            db.query(FeedbackItem)
            .filter(
                FeedbackItem.id == feedback_id,
                FeedbackItem.organization_id == integ.organization_id,
            )
            .first()
        )
        if feedback is None:
            continue

        live_links = (
            db.query(FeedbackAsanaTask)
            .filter(
                FeedbackAsanaTask.feedback_id == feedback_id,
                FeedbackAsanaTask.organization_id == integ.organization_id,
            )
            .all()
        )
        categories = [l.asana_status_category for l in live_links if l.asana_status_category]
        top_category = most_advanced(categories)
        if top_category is None:
            continue

        target = resolve_target_status(top_category, integ.status_mapping)
        observed_old_status = feedback.workflow_status
        if target is None or target == observed_old_status:
            continue

        # The link that drove the most-advanced category -- used for the
        # timeline event's metadata (which Asana task caused this).
        driving_link = next(
            (l for l in live_links if l.asana_status_category == top_category),
            live_links[0],
        )

        applied = _apply_asana_status(
            db,
            feedback,
            target,
            organization_id=integ.organization_id,
            old_status=observed_old_status,
            asana_task_gid=driving_link.asana_task_gid,
            asana_completed=driving_link.asana_completed,
        )
        if applied:
            status_changes += 1

    return {"action": "changed", "status_changes": status_changes}
