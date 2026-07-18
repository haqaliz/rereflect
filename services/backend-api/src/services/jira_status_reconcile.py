"""
Backend-side reconcile port for inbound Jira status-sync
(status-sync-realtime-mapping/jira-webhook aspect).

This is the backend-api mirror of the worker poller's `_sync_jira_org_body`
+ `apply_status_change_worker` (services/worker-service/src/tasks/
jira_sync.py + services/worker-service/src/services/status_writer.py) —
used by the Jira webhook receiver (src/api/routes/jira_webhook.py) to
reconcile a SINGLE issue's freshly-observed status immediately on a
verified status-change webhook, instead of waiting for the 15-minute poll.
The worker cannot be imported from backend-api (separate service/
deployment), so the reconcile + guarded-apply logic is duplicated here
against the pure, shared `status_sync_core` module (already verbatim-copied
between backend-api and worker-service for the poller) rather than shared
via import. This module deliberately does NOT introduce a `status_writer.py`
in backend-api — per the aspect's hard rules, the guarded conditional
UPDATE is mirrored inline here exactly as Zendesk's webhook-realtime aspect
already does in `zendesk_status_reconcile.py::_apply_zendesk_status`.

Unlike Zendesk (which tracks a separate FeedbackZendeskSync sidecar keyed by
feedback_id, one Zendesk ticket per feedback), Jira's link model
(`FeedbackJiraIssue`) already stores the last-observed status directly on
each link row (`jira_status` / `jira_status_category` /
`last_status_synced_at`) — one feedback item can have MULTIPLE linked Jira
issues. So the reconcile here mirrors the poller exactly:

  1. Look up every `FeedbackJiraIssue` link for the freshly-observed
     `jira_issue_id`, scoped to this org (there is normally exactly one, but
     the schema does not forbid more).
  2. For each link, `status_sync_core.decide_link_update` decides
     'seed' / 'noop' / 'changed' by comparing the freshly-fetched category
     against the link's own last-stored category. The link's
     jira_status/jira_status_category/last_status_synced_at are updated for
     BOTH 'seed' and 'changed' (never for 'noop') — this is what closes the
     idempotency window: a duplicate/stale redelivery of the SAME status
     change sees `fetched_category == link.jira_status_category` on the
     second call and is a pure noop, writing nothing (see module-level
     "no_feedback"/"seed"/"noop"/"changed" contract below).
  3. For every feedback whose link just recorded 'changed', the target
     status is resolved from the MOST ADVANCED category across THAT
     feedback's live links (status_sync_core.most_advanced) — exactly the
     poller's multi-issue-per-feedback rule, so a feedback item linked to
     several Jira issues never regresses because one of them moved
     backwards while another stayed further along.
  4. The apply is a RACE-SAFE conditional
     `UPDATE feedback_items SET workflow_status=:new WHERE id=:id AND
     organization_id=:org AND workflow_status=:old`
     (`_apply_jira_status` below, mirroring
     `zendesk_status_reconcile._apply_zendesk_status` and the worker's
     `status_writer._guarded_status_update` verbatim). If a concurrent
     writer (the poll task, or a second webhook delivery) already moved the
     row since `feedback` was loaded, 0 rows are affected and NO event is
     written — the other writer's own apply is the sole source of truth for
     that transition.

`reconcile_issue(db, integ, jira_issue_id, jira_issue_key, status_name,
category) -> dict` returns:
  - {"action": "no_feedback"} -- no FeedbackJiraIssue link matches this
        issue id for this org. Caller ACKs 200; nothing written.
  - {"action": "seed"}        -- every touched link was a first observation.
        Link fields are written; workflow_status is left untouched (a first
        observation must never move a feedback item's status).
  - {"action": "noop"}        -- every touched link's fetched category
        equals its already-stored category. Nothing is written at all.
  - {"action": "changed", "status_changes": N} -- at least one link
        recorded a genuine category change. N is the number of feedback
        items whose workflow_status was actually moved (0 if the resolved
        target was None/unmapped, already equal, or lost the race).

Design task (source tag): mirrors zendesk_status_reconcile.py --
`metadata={"source": "jira", "jira_status": ..., "jira_status_category":
..., "jira_issue_key": ...}` is threaded through explicitly via
`workflow_service.create_workflow_event` (not `apply_status_change`, which
does not persist a source tag today).

Outbound webhook dispatch is explicitly NOT called here -- outbound is
deferred (mirrors the poll task's docstring).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.jira_integration import FeedbackJiraIssue, JiraIntegration
from src.services.status_sync_core import decide_link_update, most_advanced, resolve_target_status
from src.services.workflow_service import create_workflow_event


def _apply_jira_status(
    db: Session,
    feedback: FeedbackItem,
    new_status: str,
    *,
    organization_id: int,
    old_status: str,
    jira_status: Optional[str],
    jira_status_category: Optional[str],
    jira_issue_key: Optional[str],
) -> bool:
    """
    Apply a workflow_status change driven by a Jira webhook and write
    exactly ONE FeedbackWorkflowEvent timeline row (actor_id=None -- no
    acting user), tagged with source="jira" metadata.

    No-ops (returns False, writes nothing) when `new_status` already equals
    `old_status` (the CALLER-observed value -- see reconcile_issue).

    RACE-SAFE: the write is a conditional
    `UPDATE ... WHERE id=? AND organization_id=? AND workflow_status=<old_status>`.
    If a concurrent writer already moved this row since the caller observed
    `old_status` (0 rows affected), this returns False and writes NO event --
    mirrors `zendesk_status_reconcile._apply_zendesk_status` and the
    worker's `status_writer._guarded_status_update` verbatim (the worker
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
            "source": "jira",
            "jira_status": jira_status,
            "jira_status_category": jira_status_category,
            "jira_issue_key": jira_issue_key,
        },
    )
    db.flush()
    return True


def reconcile_issue(
    db: Session,
    integ: JiraIntegration,
    jira_issue_id: Any,
    jira_issue_key: Optional[str],
    status_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Reconcile one Jira issue's freshly-observed status onto every feedback
    item it's linked to (immediate, single-issue webhook path -- see module
    docstring for the full contract).

    Matches links by `jira_issue_id` (Jira's internal, immutable issue id --
    unlike `jira_issue_key`, which changes if the issue moves projects),
    scoped to `integ.organization_id`.
    """
    links = (
        db.query(FeedbackJiraIssue)
        .filter(
            FeedbackJiraIssue.organization_id == integ.organization_id,
            FeedbackJiraIssue.jira_issue_id == str(jira_issue_id),
        )
        .all()
    )
    if not links:
        return {"action": "no_feedback"}

    actions = []
    changed_feedback_ids: set = set()

    for link in links:
        action, name, fetched_category = decide_link_update(
            category, status_name, link.jira_status_category
        )
        actions.append(action)
        if action == "noop":
            continue

        link.jira_status = name
        link.jira_status_category = fetched_category
        link.last_status_synced_at = datetime.utcnow()

        if action == "changed":
            changed_feedback_ids.add(link.feedback_id)

    db.flush()

    if not changed_feedback_ids:
        # Every touched link was either 'noop' (already-observed status --
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
            db.query(FeedbackJiraIssue)
            .filter(
                FeedbackJiraIssue.feedback_id == feedback_id,
                FeedbackJiraIssue.organization_id == integ.organization_id,
            )
            .all()
        )
        categories = [l.jira_status_category for l in live_links if l.jira_status_category]
        top_category = most_advanced(categories)
        if top_category is None:
            continue

        target = resolve_target_status(top_category, integ.status_mapping)
        observed_old_status = feedback.workflow_status
        if target is None or target == observed_old_status:
            continue

        # The link that drove the most-advanced category -- used for the
        # timeline event's metadata (which Jira issue caused this).
        driving_link = next(
            (l for l in live_links if l.jira_status_category == top_category),
            live_links[0],
        )

        applied = _apply_jira_status(
            db,
            feedback,
            target,
            organization_id=integ.organization_id,
            old_status=observed_old_status,
            jira_status=driving_link.jira_status,
            jira_status_category=driving_link.jira_status_category,
            jira_issue_key=driving_link.jira_issue_key,
        )
        if applied:
            status_changes += 1

    return {"action": "changed", "status_changes": status_changes}
