"""
Backend-side reconcile port for inbound Zendesk status-sync
(zendesk-status-sync/webhook-realtime aspect).
See docs/planning/zendesk-status-sync/webhook-realtime/{dig,plan_20260712,spec}.md.

This is the backend-api mirror of the worker's `reconcile_feedback` +
`apply_zendesk_status_worker` (services/worker-service/src/tasks/
zendesk_status_sync.py) — used by the Zendesk webhook receiver
(src/api/routes/source_webhooks.py) to reconcile a SINGLE ticket's status
immediately on a verified status-change webhook, instead of waiting for the
15-minute poll. The worker cannot be imported from backend-api (separate
service/deployment), so the reconcile + apply logic is duplicated here
against the pure, shared `zendesk_status_core` module (verbatim-copied
between both services) rather than shared via import.

`reconcile_ticket(db, integ, ticket_id, fetched_status) -> str` returns one
of:
  - "no_feedback" -- no FeedbackItem is linked to this ticket for this org.
                     Caller (the webhook route) ACKs 200; nothing written.
  - "seed"        -- first observation for this feedback item. Sidecar is
                     written; workflow_status is left untouched (mirrors the
                     poll task's seed semantics -- a first observation must
                     never move a feedback item's status).
  - "noop"        -- fetched_status == the sidecar's last-observed status.
                     Nothing is written at all (not even the sidecar
                     timestamp), matching the poll task's "poll twice,
                     second poll is a no-op" behavior at the DB-write level.
  - "changed"     -- fetched_status differs from the sidecar's last-observed
                     status. `resolve_target_status` maps it to a Rereflect
                     workflow_status (or None if unmapped/invalid, in which
                     case no apply happens); if mapped, the apply is
                     attempted via a RACE-SAFE conditional UPDATE (see
                     `_apply_zendesk_status` below). The sidecar is ALWAYS
                     updated to the freshly observed status on "changed",
                     regardless of whether the apply actually wrote (unknown
                     status, no-op-because-already-equal, or lost the
                     concurrency race) -- this keeps the sidecar accurate so
                     an already-observed status never re-triggers "changed"
                     on a later poll/webhook.

Design task #1 (source tag): `workflow_service.apply_status_change` does not
persist an actor/source tag today (see its docstring -- `actor_label` is
accepted for caller ergonomics only and not persisted). This module does NOT
call `apply_status_change`; it writes the conditional UPDATE + event
directly via `workflow_service.create_workflow_event`, threading
`metadata={"source": "zendesk", "zendesk_status": ..., "zendesk_ticket_id":
...}` through explicitly, per the webhook-realtime spec's acceptance
criteria (`metadata.source == "zendesk"`).

Design task #2 (race-safe guard): the apply is a conditional
`UPDATE feedback_items SET workflow_status=:new WHERE id=:id AND
organization_id=:org AND workflow_status=:old`. If a concurrent writer
(the poll task, or a second webhook delivery) already moved the row since
`feedback` was loaded, 0 rows are affected and NO event is written here --
the other writer's own apply is the sole source of truth for that
transition. This mirrors `apply_zendesk_status_worker` in
worker-service/src/tasks/zendesk_status_sync.py exactly.

Outbound webhook dispatch (`dispatch_status_webhooks`) is explicitly NOT
called here -- outbound is deferred (Jira parity, mirrors the poll task).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy.exc
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.feedback_zendesk_sync import FeedbackZendeskSync
from src.services.workflow_service import create_workflow_event
from src.services.zendesk_status_core import decide_update, resolve_target_status


def _upsert_sidecar(db: Session, feedback_id: int, status: str) -> None:
    """Write/update the FeedbackZendeskSync sidecar's last-observed status.

    First observation for a feedback_id is a plain INSERT (no existing row
    to UPDATE). If a concurrent writer — the worker's poll task and this
    webhook path both observing the SAME ticket for the first time —
    reaches this at the same instant, both may see `row is None` here and
    both attempt to INSERT the same feedback_id PK. The insert is isolated
    in a SAVEPOINT (mirrors the race-safe insert pattern already used
    elsewhere in this codebase, e.g. usage_webhooks.py) so the loser's
    IntegrityError only unwinds this nested transaction, not the whole
    request's session; the loser then treats the winner's already-committed
    row as authoritative and does nothing further — equivalent to Postgres
    `ON CONFLICT (feedback_id) DO NOTHING`, but dialect-agnostic (works
    against both the sqlite dialect used in tests and Postgres in
    production). This path is only ever reached on the "seed" action
    (decide_update only returns "seed" when no sidecar row existed), so no
    status change or event is ever at stake for the loser here.
    """
    row = db.get(FeedbackZendeskSync, feedback_id)
    now = datetime.utcnow()
    if row is None:
        sp = db.begin_nested()
        db.add(
            FeedbackZendeskSync(
                feedback_id=feedback_id,
                last_ticket_status=status,
                last_status_synced_at=now,
            )
        )
        try:
            sp.commit()  # flushes the row within the SAVEPOINT
        except sqlalchemy.exc.IntegrityError:
            sp.rollback()  # concurrent writer already inserted this PK — their row wins
        return
    row.last_ticket_status = status
    row.last_status_synced_at = now


def _apply_zendesk_status(
    db: Session,
    feedback: FeedbackItem,
    new_status: str,
    *,
    organization_id: int,
    ticket_id,
    zendesk_status: str,
) -> bool:
    """
    Apply a workflow_status change driven by a Zendesk webhook and write
    exactly ONE FeedbackWorkflowEvent timeline row (actor_id=None -- no
    acting user), tagged with source="zendesk" metadata.

    No-ops (returns False, writes nothing) when `new_status` already equals
    the feedback's current workflow_status.

    RACE-SAFE: the write is a conditional
    `UPDATE ... WHERE id=? AND organization_id=? AND workflow_status=<old>`.
    If a concurrent writer already moved this row since `feedback` was
    loaded (0 rows affected), this returns False and writes NO event.
    """
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
            "source": "zendesk",
            "zendesk_status": zendesk_status,
            "zendesk_ticket_id": str(ticket_id),
        },
    )
    db.flush()
    return True


def reconcile_ticket(db: Session, integ, ticket_id, fetched_status: str) -> str:
    """
    Reconcile one Zendesk ticket's freshly-observed status onto its linked
    feedback item's workflow_status (immediate, single-ticket path -- see
    module docstring for the full "no_feedback"/"seed"/"noop"/"changed"
    semantics).
    """
    feedback: Optional[FeedbackItem] = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.source == "zendesk",
            FeedbackItem.source_external_id == str(ticket_id),
            FeedbackItem.organization_id == integ.organization_id,
        )
        .first()
    )
    if feedback is None:
        return "no_feedback"

    sidecar = db.get(FeedbackZendeskSync, feedback.id)
    stored = sidecar.last_ticket_status if sidecar else None

    action = decide_update(fetched_status, stored)
    if action == "noop":
        return "noop"

    if action == "changed":
        target = resolve_target_status(fetched_status, integ.status_mapping)
        if target is not None:
            _apply_zendesk_status(
                db,
                feedback,
                target,
                organization_id=integ.organization_id,
                ticket_id=feedback.source_external_id,
                zendesk_status=fetched_status,
            )

    # seed AND changed both record the freshly observed status.
    _upsert_sidecar(db, feedback.id, fetched_status)
    return action
