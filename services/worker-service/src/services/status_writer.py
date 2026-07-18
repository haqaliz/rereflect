"""
Shared, provider-agnostic status writer for inbound status-sync pollers
(jira_sync.py, asana_sync.py — asana-status-sync/worker-sync-task aspect).

Originally lifted verbatim from jira_sync.py's `apply_status_change_worker`
(provider-neutral: takes an `actor_label` and a free-form `metadata` dict,
hardcodes nothing provider-specific). Both pollers import this single
function so the "one event, no-op-on-equal, actor_id=None, no outbound
webhook" invariants can never diverge between providers.

RACE-SAFE GUARD (status-sync-realtime-mapping/status-writer-race-guard):
the original implementation did an in-Python read-modify-write
(`if feedback.workflow_status == new_status: ...; feedback.workflow_status
= new_status`), which is NOT safe under concurrency — two overlapping
callers (the 15-min poll and a future real-time webhook, or two overlapping
poll runs) can both observe the same `old_status`, both pass the equality
check, and both write a duplicate/conflicting event.

This now mirrors the race-safe pattern already proven twice elsewhere in
this codebase — `apply_zendesk_status_worker` in
src/tasks/zendesk_status_sync.py (worker) and `_apply_zendesk_status` in
services/backend-api/src/services/zendesk_status_reconcile.py (backend-api):
a conditional `UPDATE feedback_items SET workflow_status=:new WHERE
id=:id AND organization_id=:org AND workflow_status=:old`, applied via the
ORM's `Query.update(synchronize_session=False)` (dialect-agnostic — works
identically against SQLite in tests and PostgreSQL in production). The
single `FeedbackWorkflowEvent` is written iff exactly 1 row was affected;
otherwise this returns False and writes nothing — the other writer's own
apply is the sole source of truth for that transition.

Unlike the Zendesk appliers (which derive `old_status` themselves from
`feedback.workflow_status` at call time), this function takes the
caller-observed `old_status` as an EXPLICIT required keyword — see
spec.md's "the guard is meaningful" rationale: the caller (jira_sync.py /
asana_sync.py) already reads `feedback.workflow_status` before deciding
whether to apply at all (the `target == feedback.workflow_status` no-op
check), so it threads that same observed value through explicitly rather
than relying on the callee to re-read a possibly-stale ORM attribute.

`_guarded_status_update` is factored out as the single place holding the
conditional-UPDATE SQL shape, so a future backend-api webhook reconcile
port (jira-webhook / asana-webhook aspects, which cannot import the worker
— separate service/deployment) can mirror it verbatim, exactly as the
Zendesk webhook-realtime aspect already mirrors
`apply_zendesk_status_worker`.

Characterization lock: tests/test_jira_sync_task.py and
tests/test_asana_sync_task.py must stay green, same count, before and
after this guard (proves the non-concurrent path is behavior-preserving).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _guarded_status_update(
    db,
    feedback_id: int,
    *,
    organization_id: int,
    old_status: str,
    new_status: str,
) -> bool:
    """
    Conditionally move `feedback_items.workflow_status` from `old_status` to
    `new_status`, guarded on id + organization_id (multi-tenancy, defense in
    depth) + the currently-persisted workflow_status still matching the
    caller-observed `old_status`.

    Returns True iff exactly 1 row was affected (i.e. no concurrent writer
    raced this apply). Returns False (writes nothing) if 0 rows matched —
    either the row was already moved by someone else, or it belongs to a
    different organization.
    """
    from src.models import FeedbackItem

    rows = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == feedback_id,
            FeedbackItem.organization_id == organization_id,
            FeedbackItem.workflow_status == old_status,
        )
        .update({FeedbackItem.workflow_status: new_status}, synchronize_session=False)
    )
    return rows == 1


def apply_status_change_worker(
    db,
    feedback,
    new_status: str,
    *,
    old_status: str,
    organization_id: int,
    actor_label: str,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Apply a workflow_status change driven by an automated source (no acting
    user — actor_id is always None here) and write exactly ONE
    FeedbackWorkflowEvent timeline row.

    `old_status` is the value the CALLER observed (e.g. the sidecar/link's
    last-known feedback status) — see module docstring. No-ops (returns
    False, writes nothing) when it already equals `new_status`.

    RACE-SAFE: the write is a conditional `UPDATE ... WHERE id=? AND
    organization_id=? AND workflow_status=<old_status>` (see
    `_guarded_status_update`). If a concurrent writer already moved this row
    since the caller observed `old_status` (0 rows affected), this returns
    False and writes NO event — the other writer's own apply is the sole
    source of truth for that transition, so no duplicate/conflicting event
    is ever written here.

    NOTE: this deliberately does NOT dispatch outbound `feedback.status_changed`
    webhooks — see the calling task modules' docstrings ("Outbound webhook
    dispatch ... DEFERRED"). If worker-side webhook dispatch is ever added,
    do it once here so both providers stay aligned.
    """
    from src.models import FeedbackWorkflowEvent

    if old_status == new_status:
        return False

    applied = _guarded_status_update(
        db,
        feedback.id,
        organization_id=organization_id,
        old_status=old_status,
        new_status=new_status,
    )
    if not applied:
        # Someone else moved it (or it's not this org's row) — no
        # duplicate/conflicting event.
        return False

    # Keep the in-memory object in sync with the write we just made (the
    # conditional UPDATE above used synchronize_session=False, so the ORM
    # instance's attribute is stale until we set it explicitly).
    feedback.workflow_status = new_status

    logger.info(
        "status_writer: %s changed feedback_id=%s org=%s %s -> %s",
        actor_label,
        feedback.id,
        organization_id,
        old_status,
        new_status,
    )

    event = FeedbackWorkflowEvent(
        feedback_id=feedback.id,
        organization_id=organization_id,
        actor_id=None,
        event_type="status_changed",
        old_value=old_status,
        new_value=new_status,
        metadata_=metadata,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.flush()
    return True
