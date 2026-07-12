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

  reconcile_feedback(db, feedback, fetched_status, integ) -> "seed"|"noop"|"changed"
    Given one feedback item's freshly-fetched Zendesk ticket status, reads
    the `FeedbackZendeskSync` sidecar (last-observed status) and decides via
    the pure `zendesk_status_core.decide_update`:
      - 'seed'    -> first observation. Sidecar written, feedback
                     workflow_status untouched (safety: first observation
                     must never move a feedback item's workflow_status —
                     mirrors jira_sync's link-seed behavior).
      - 'noop'    -> fetched == stored. Nothing written at all (not even the
                     sidecar timestamp) — this is what makes "poll twice,
                     second poll is a no-op" hold at the DB-write level too.
      - 'changed' -> resolve_target_status(fetched, integ.status_mapping);
                     if not None, apply via apply_zendesk_status_worker
                     (itself a no-op if the target equals the current
                     status). Sidecar is ALWAYS updated to the new
                     last-observed status regardless of whether the target
                     resolved/applied, so an unknown/overridden-out status
                     is still recorded and won't re-trigger 'changed' next
                     poll.

  _sync_zendesk_status_org_body(integration_id, db, client=None) — loads the
  integration + this org's Zendesk-linked feedback (source='zendesk',
  source_external_id IS NOT NULL), batch-fetches current ticket status via
  `client.show_many(ids)` (chunked defense-in-depth, mirrors jira_sync's
  `_SEARCH_CHUNK_SIZE` pattern even though ZendeskClient.show_many already
  chunks internally), and reconciles every returned ticket through
  `reconcile_feedback`. Tickets requested but absent from the response
  (deleted/archived) are simply skipped — not an error.

  `client` is injectable (a plain object exposing `show_many`) so tests
  never need real HTTP or Celery. When `client` is None (the real
  `sync_zendesk_status_org` task path), a real `ZendeskClient` is
  constructed from the decrypted token.

R3: the api_token is never logged. Log messages use integration_id/org_id only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error) — mirrors jira_sync.py/zendesk_sync.py.
D7 (mirrors jira_sync.py/zendesk_sync.py): a ZendeskAuthError is operator-recoverable —
    last_status_sync_error is recorded WITHOUT disconnecting (is_active untouched) and
    without raising/retrying.

Beat schedule: every 15 minutes (interval, matching sync-zendesk-every-15-min
/ sync-jira-status-every-15-min).
Registration: see src/celery_app.py include list.

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

import logging
import os
from datetime import datetime
from typing import Any, Dict

from celery import shared_task

from src.clients.zendesk import ZendeskAuthError, ZendeskClient, ZendeskTransientError
from src.database import get_db_session
from src.services.zendesk_status_core import decide_update, resolve_target_status

logger = logging.getLogger(__name__)

# Cap the number of ticket ids sent to a single client.show_many() call —
# mirrors jira_sync's _SEARCH_CHUNK_SIZE (defense in depth; ZendeskClient
# already chunks internally at 100/request, but this keeps a single logical
# "page" of work per DB-visible batch here too).
_SHOW_MANY_CHUNK_SIZE = 100

# Per-run cap on the number of Zendesk-linked feedback items reconciled in a
# single beat tick (mirrors ZendeskClient.PER_RUN_PAGE_CAP's throttle
# intent) — a huge backlog reconciles over several beats rather than one
# task run trying to do everything at once.
_PER_RUN_FEEDBACK_CAP = 1000


# ---------------------------------------------------------------------------
# Local token decryption (mirrors jira_sync.py / zendesk_sync.py _decrypt)
# R6: Worker cannot import from backend-api; uses its own Fernet helper.
# ---------------------------------------------------------------------------


def _decrypt(token: str) -> str:
    """Decrypt a Fernet-encrypted string using LLM_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _persist_terminal_status(integration_id: int, error: str) -> None:
    """
    Persist last_status_sync_error in a FRESH session that commits
    independently of the caller's session (mirrors jira_sync.py's
    identically-purposed helper — see its docstring for the full rollback
    rationale: the caller's `with get_db_session() as db:` block rolls back
    on any exception that propagates out of it, so a terminal failure
    status written just before `raise self.retry(...)` would otherwise be
    silently discarded).
    """
    from src.models import ZendeskIntegration

    try:
        with get_db_session() as fresh_db:
            row = (
                fresh_db.query(ZendeskIntegration)
                .filter(ZendeskIntegration.id == integration_id)
                .first()
            )
            if row is not None:
                row.last_status_sync_error = error
    except Exception:
        logger.error(
            "zendesk_status_sync: failed to persist terminal status for "
            "integration_id=%s",
            integration_id,
            exc_info=True,
        )


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


# ---------------------------------------------------------------------------
# Phase 2 — per-feedback reconcile helper (shared shape with the webhook
# aspect, which re-implements this in backend-api since it can't import
# the worker — see this aspect's plan "Edge cases / notes")
# ---------------------------------------------------------------------------


def _upsert_sidecar(db, feedback_id: int, status: str) -> None:
    """Write/update the FeedbackZendeskSync sidecar's last-observed status."""
    from src.models import FeedbackZendeskSync

    row = db.get(FeedbackZendeskSync, feedback_id)
    now = datetime.utcnow()
    if row is None:
        db.add(
            FeedbackZendeskSync(
                feedback_id=feedback_id,
                last_ticket_status=status,
                last_status_synced_at=now,
            )
        )
        # Flush immediately so a same-session db.get() lookup (e.g. a
        # subsequent poll within the same request/session) sees the new
        # row without relying on autoflush (disabled in test sessions).
        db.flush()
    else:
        row.last_ticket_status = status
        row.last_status_synced_at = now


def reconcile_feedback(db, feedback, fetched_status: str, integ) -> str:
    """
    Reconcile one feedback item's freshly-fetched Zendesk ticket status.

    Returns "seed" | "noop" | "changed" (see module docstring for the full
    semantics of each).
    """
    from src.models import FeedbackZendeskSync

    row = db.get(FeedbackZendeskSync, feedback.id)
    stored = row.last_ticket_status if row else None

    action = decide_update(fetched_status, stored)
    if action == "noop":
        return "noop"

    if action == "changed":
        target = resolve_target_status(fetched_status, integ.status_mapping)
        if target is not None:
            apply_zendesk_status_worker(
                db,
                feedback,
                target,
                organization_id=integ.organization_id,
                ticket_id=feedback.source_external_id,
                zendesk_status=fetched_status,
            )

    # seed AND changed both record the last-observed status.
    _upsert_sidecar(db, feedback.id, fetched_status)
    return action


# ---------------------------------------------------------------------------
# Phase 3 — core sync logic (Celery-free — tested directly)
# ---------------------------------------------------------------------------


def _sync_zendesk_status_org_body(integration_id: int, db, client=None) -> Dict[str, Any]:
    """
    Inner logic of sync_zendesk_status_org. Extracted as a plain function
    taking `db` and an injectable `client` so tests never need real HTTP or
    Celery machinery.

    Raises:
        ZendeskTransientError: propagated to the caller
            (sync_zendesk_status_org) so Celery can retry — never caught
            here.

    ZendeskAuthError is caught HERE (not propagated) — recorded on the
    integration row and returned as a result dict, matching D7
    (operator-recoverable, no retry, no disconnect).
    """
    from src.models import FeedbackItem, ZendeskIntegration

    integ = (
        db.query(ZendeskIntegration)
        .filter(ZendeskIntegration.id == integration_id)
        .first()
    )
    if not integ:
        return {"status": "not_found", "integration_id": integration_id}
    if not integ.is_active:
        return {"status": "inactive", "integration_id": integration_id}
    if not integ.status_sync_enabled:
        return {"status": "disabled", "integration_id": integration_id}

    owns_client = client is None
    if owns_client:
        # R6: missing LLM_ENCRYPTION_KEY -> non-transient config error; do not retry.
        try:
            token = _decrypt(integ.api_token)
        except ValueError:
            logger.error(
                "zendesk_status_sync: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt api_token; skipping (integration_id=%s)",
                integ.organization_id,
                integration_id,
            )
            integ.last_status_sync_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        client = ZendeskClient(integ.subdomain, integ.email, token)

    try:
        feedback_items = (
            db.query(FeedbackItem)
            .filter(
                FeedbackItem.source == "zendesk",
                FeedbackItem.source_external_id.isnot(None),
                FeedbackItem.organization_id == integ.organization_id,
            )
            .limit(_PER_RUN_FEEDBACK_CAP)
            .all()
        )

        by_ticket_id = {fb.source_external_id: fb for fb in feedback_items}
        ticket_ids = list(by_ticket_id.keys())

        fetched: Dict[str, str] = {}
        for start in range(0, len(ticket_ids), _SHOW_MANY_CHUNK_SIZE):
            chunk = ticket_ids[start : start + _SHOW_MANY_CHUNK_SIZE]
            fetched.update(client.show_many(chunk))

        seeded = 0
        noop = 0
        changed = 0

        for ticket_id, fetched_status in fetched.items():
            feedback = by_ticket_id.get(ticket_id)
            if feedback is None:
                # Not one of ours (shouldn't happen — show_many is only
                # ever called with our own ids) — skip defensively.
                continue

            action = reconcile_feedback(db, feedback, fetched_status, integ)
            if action == "seed":
                seeded += 1
            elif action == "noop":
                noop += 1
            elif action == "changed":
                changed += 1

        integ.last_status_synced_at = datetime.utcnow()
        integ.last_status_sync_error = None
        db.flush()

        return {
            "status": "success",
            "polled": len(ticket_ids),
            "seeded": seeded,
            "noop": noop,
            "changed": changed,
        }

    except ZendeskAuthError as exc:
        # D7: operator-recoverable auth failure — record without
        # disconnecting (is_active untouched) and without raising/retrying.
        logger.error(
            "zendesk_status_sync: auth error for org=%s (integration_id=%s): %s",
            integ.organization_id,
            integration_id,
            exc,
        )
        integ.last_status_sync_error = str(exc)[:500]
        db.flush()
        return {"status": "error", "reason": "auth_error"}

    finally:
        if owns_client:
            client.close()


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------


@shared_task(name="src.tasks.zendesk_status_sync.sync_all_zendesk_status")
def sync_all_zendesk_status() -> Dict[str, Any]:
    """
    Fan-out: scan all active + status_sync_enabled Zendesk integrations and
    enqueue per-org status sync.

    Per-org try/except ensures one failure never aborts the batch.
    """
    from src.models import ZendeskIntegration

    with get_db_session() as db:
        integrations = (
            db.query(ZendeskIntegration)
            .filter(
                ZendeskIntegration.is_active.is_(True),
                ZendeskIntegration.status_sync_enabled.is_(True),
            )
            .all()
        )
        if not integrations:
            return {"status": "no_integrations", "queued": 0}

        queued = 0
        for integ in integrations:
            try:
                sync_zendesk_status_org.delay(integ.id)
                queued += 1
            except Exception as exc:
                logger.error(
                    "sync_all_zendesk_status: failed to enqueue org=%s (integration_id=%s): %s",
                    integ.organization_id,
                    integ.id,
                    exc,
                )

        return {"status": "queued", "queued": queued}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.zendesk_status_sync.sync_zendesk_status_org",
)
def sync_zendesk_status_org(self, integration_id: int) -> Dict[str, Any]:
    """
    Per-org Zendesk status-sync poll. Retries on ZendeskTransientError
    (max 3x). ZendeskAuthError / missing-encryption-key are handled inside
    `_sync_zendesk_status_org_body` (recorded without raising/retrying).
    """
    with get_db_session() as db:
        try:
            return _sync_zendesk_status_org_body(integration_id, db)
        except ZendeskTransientError as exc:
            logger.warning(
                "zendesk_status_sync: transient error for integration_id=%s: %s",
                integration_id,
                exc,
            )
            # NOTE: deliberately NOT db.flush()'d — this session's
            # transaction rolls back on the `raise` below regardless (see
            # get_db_session), and flushing here would additionally take a
            # row lock that could self-deadlock against the fresh session
            # _persist_terminal_status opens next (same row, same process).
            # _persist_terminal_status is the sole durable write for this
            # branch — mirrors jira_sync.py/zendesk_sync.py.
            _persist_terminal_status(integration_id, str(exc))
            raise self.retry(exc=exc)
