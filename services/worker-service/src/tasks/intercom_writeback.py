"""
Intercom write-back task (intercom-writeback aspect, worker-writeback-task).

Task:
  push_resolved_writeback(org_id, items) — given the org and the feedback
  items that just transitioned to `resolved`, append a note to each linked
  Intercom conversation and close it (per writeback_action).

R3: the access token is never logged. Log messages use org_id / feedback id /
    conversation outcome only.
R4: the per-item durable marker feedback_items.intercom_writeback_at is set
    AFTER the action completes (success or 404-idempotent already_closed) and
    checked before acting (guard 3 -> noop/already_written), so a re-resolve
    after reopen is a noop and a retry cannot double-write.
R6: missing LLM_ENCRYPTION_KEY / decrypt failure -> error, NO retry
    (non-transient config error) — mirrors the hubspot/salesforce writebacks.

Soft-pause semantics: permanent failures (missing write scope, missing key,
no admin) are recorded on the integration row's last_writeback_* columns but
NEVER set is_active=False — that flag is owned exclusively by the read-sync
task (intercom_sync.py). A subsequent inbound sync must always still succeed
after a writeback soft-pause.

Batch-retry semantics: a transient failure (429/5xx) aborts the run via
task_self.retry and the WHOLE payload is re-executed on retry. The marker and
row updates are committed PER ITEM (deliberate departure from the hubspot
flush-only idiom), so items completed before the abort keep their markers and
guard 3 turns them into noops on the retry — a mid-batch retry can never
duplicate a note for an already-completed item.

Registration: see src/celery_app.py include list. NOT beat-scheduled —
dispatched only via send_task/delay by the dispatch-seams aspect.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from celery import shared_task
from cryptography.fernet import InvalidToken

from src.clients.intercom import (
    IntercomAuthError,
    IntercomClient,
    IntercomError,
    IntercomNotFoundError,
    IntercomTransientError,
)
from src.database import get_db_session

logger = logging.getLogger(__name__)

_DEFAULT_NOTE_TEXT = "Marked resolved in Rereflect."


# ---------------------------------------------------------------------------
# Local token decryption (verbatim copy of intercom_sync.py's _decrypt helper)
# R6: Worker cannot import from backend-api; uses its own Fernet helper.
# ---------------------------------------------------------------------------


def _decrypt(token: str) -> str:
    """Decrypt a Fernet-encrypted string using LLM_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def _resolve_connection(db, org_id):
    """Resolve the org's Intercom credential: token-paste first, then legacy OAuth.

    The token-paste row is matched by organization_id only — it is a per-org
    row (uq_intercom_integrations_org_id), so no workspace matching is needed.
    The legacy OAuth row is matched by type == "intercom" + is_active (the
    source_events.py OR-clause precedent, :190-227). Returns
    (connection_row, kind) with kind "token_paste" | "oauth", or (None, None)
    when the org has no Intercom connection.
    """
    from src.models import Integration, IntercomIntegration

    token_paste = (
        db.query(IntercomIntegration)
        .filter(IntercomIntegration.organization_id == org_id)
        .first()
    )
    if token_paste is not None:
        return token_paste, "token_paste"

    oauth_row = (
        db.query(Integration)
        .filter(
            Integration.organization_id == org_id,
            Integration.type == "intercom",
            Integration.is_active == True,  # noqa: E712
        )
        .first()
    )
    if oauth_row is not None:
        return oauth_row, "oauth"

    return None, None


def _resolved_action(connection, connection_kind) -> str:
    """The writeback action for the resolved connection.

    Token-paste: the writeback_action column; an unknown/blank value falls
    back to note_and_close with a warning. Legacy OAuth rows have no column —
    the v1 grandfathered default is note_and_close (plan D4).
    """
    if connection_kind == "oauth":
        return "note_and_close"
    action = connection.writeback_action
    if action not in ("note_only", "note_and_close"):
        logger.warning(
            "intercom_writeback: unknown writeback_action %r on the org's "
            "IntercomIntegration row — falling back to note_and_close",
            action,
        )
        return "note_and_close"
    return action


def _record_row_outcome(connection, connection_kind, status, error, at=None):
    """Record a writeback outcome on the resolved credential source's row.

    Token-paste rows only: the legacy OAuth Integration row has no writeback
    columns, so for OAuth connections the task log + timeline event are the
    durable record (plan D4/D8). is_active is NEVER touched — that flag is
    owned exclusively by the read-sync task (intercom_sync.py).
    """
    if connection_kind != "token_paste":
        return
    connection.last_writeback_status = status
    connection.last_writeback_error = error
    if at is not None:
        connection.last_writeback_at = at


def _write_writeback_event(db, feedback_id, org_id, action, note_sent, closed, reason=None):
    """One intercom_writeback FeedbackWorkflowEvent per acted item (plan D7).

    metadata_ keys are a cross-aspect contract consumed by dispatch-seams'
    timeline fetcher — do not rename (source/action/note_sent/closed/reason).
    """
    from src.models import FeedbackWorkflowEvent

    metadata = {
        "source": "intercom",
        "action": action,
        "note_sent": bool(note_sent),
        "closed": bool(closed),
    }
    if reason is not None:
        metadata["reason"] = reason

    event = FeedbackWorkflowEvent(
        feedback_id=feedback_id,
        organization_id=org_id,
        actor_id=None,  # system-driven, status_writer precedent
        event_type="intercom_writeback",
        old_value=None,
        new_value=None,
        metadata_=metadata,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.flush()


# ---------------------------------------------------------------------------
# Task implementation body (extracted so it can be called directly in tests;
# db is injected — the wrapper owns get_db_session())
# ---------------------------------------------------------------------------


def _push_resolved_writeback_body(task_self, db, org_id: int, items: list) -> dict:
    """
    Inner logic of push_resolved_writeback. Extracted as a plain function so
    tests can call it directly without Celery machinery.

    Never raises except the deliberate Retry propagation from _act_on_item
    (whole-payload batch-retry semantics); every other failure is recorded
    per item and the batch continues.
    """
    from src.models import FeedbackItem

    results = []
    for item in items or []:
        feedback_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(feedback_id, int):
            results.append({"id": feedback_id, "status": "error", "reason": "invalid_payload"})
            continue
        resolution_note = item.get("resolution_note") if isinstance(item, dict) else None

        # Guard 1 — the item exists and belongs to this org.
        feedback = (
            db.query(FeedbackItem)
            .filter(
                FeedbackItem.id == feedback_id,
                FeedbackItem.organization_id == org_id,
            )
            .first()
        )
        if feedback is None:
            results.append({"id": feedback_id, "status": "noop", "reason": "not_found"})
            continue

        # Guard 2 — Intercom-sourced with a conversation id in source_metadata.
        if feedback.source != "intercom":
            results.append({"id": feedback_id, "status": "noop", "reason": "not_intercom"})
            continue
        conversation_id = (feedback.source_metadata or {}).get("conversation_id")
        if not conversation_id:
            results.append({"id": feedback_id, "status": "noop", "reason": "no_conversation_id"})
            continue

        # Guard 3 — the durable marker (re-resolve-after-reopen / retry-idempotency).
        if feedback.intercom_writeback_at is not None:
            results.append({"id": feedback_id, "status": "noop", "reason": "already_written"})
            continue

        # Guard 4 — connection: token-paste first, then legacy OAuth.
        connection, connection_kind = _resolve_connection(db, org_id)
        if connection is None:
            results.append({"id": feedback_id, "status": "noop", "reason": "no_connection"})
            continue

        # Guard 5 — writeback eligibility. The writeback_enabled gate applies
        # to the token-paste row only; the OAuth row is grandfathered in by
        # its active connection (plan D4).
        if connection_kind == "token_paste" and not connection.writeback_enabled:
            results.append({"id": feedback_id, "status": "noop", "reason": "writeback_disabled"})
            continue

        now = datetime.utcnow()
        action = _resolved_action(connection, connection_kind)

        # Guard 6 — decrypt the token. Missing LLM_ENCRYPTION_KEY (ValueError)
        # and a key change (InvalidToken) are permanent operator-config errors:
        # recorded on the row, NO retry (R6 contract).
        token_column = (
            connection.access_token
            if connection_kind == "token_paste"
            else connection.oauth_access_token
        )
        try:
            token = _decrypt(token_column)
        except ValueError:
            logger.error(
                "intercom_writeback: LLM_ENCRYPTION_KEY unset for org=%s — "
                "cannot decrypt token; skipping feedback_id=%s",
                org_id, feedback_id,
            )
            _record_row_outcome(connection, connection_kind, "error", "missing_encryption_key")
            _write_writeback_event(
                db, feedback_id, org_id, action, False, False,
                reason="missing_encryption_key",
            )
            results.append({"id": feedback_id, "status": "error", "reason": "missing_encryption_key"})
            continue
        except InvalidToken:
            logger.error(
                "intercom_writeback: token decrypt failed for org=%s (key "
                "changed?) — skipping feedback_id=%s",
                org_id, feedback_id,
            )
            _record_row_outcome(connection, connection_kind, "error", "token_decrypt_failed")
            _write_writeback_event(
                db, feedback_id, org_id, action, False, False,
                reason="token_decrypt_failed",
            )
            results.append({"id": feedback_id, "status": "error", "reason": "token_decrypt_failed"})
            continue

        # Guard 7 — admin id: stored first, fetch_admin_id (GET /me) fallback.
        # Any fetch failure — including a transient one — is a recorded
        # terminal error/no_admin with no retry: a missing admin is an
        # operator-config problem, not an upstream blip (plan §10 decision 5).
        admin_id = (
            connection.admin_id
            if connection_kind == "token_paste"
            else (connection.config or {}).get("admin_id")
        )
        if not admin_id:
            try:
                with IntercomClient(token) as client:
                    admin_id = client.fetch_admin_id()
            except IntercomError as exc:
                logger.warning(
                    "intercom_writeback: no admin id for org=%s feedback_id=%s: %s",
                    org_id, feedback_id, exc,
                )
                _record_row_outcome(
                    connection, connection_kind, "error: no_admin", str(exc)[:500], at=now
                )
                _write_writeback_event(
                    db, feedback_id, org_id, action, False, False, reason="no_admin"
                )
                results.append({"id": feedback_id, "status": "error", "reason": "no_admin"})
                continue

        # Act stage — Phase 3.
        results.append(
            {
                "id": feedback_id,
                "status": "error",
                "reason": "not_implemented",
            }
        )

    return {"status": "ok", "processed": len(results), "results": results}


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.intercom_writeback.push_resolved_writeback",
)
def push_resolved_writeback(self, org_id: int, items: list) -> dict:
    """
    Append a resolution note to each Intercom conversation linked to the
    given feedback items and close it (per writeback_action).

    Idempotent per item (durable intercom_writeback_at marker), guarded
    (7 guards), soft-pausing on permanent failures — never disables the
    integration (is_active is owned exclusively by the read-sync task).
    Dispatched only via send_task/delay by the dispatch-seams aspect.
    """
    with get_db_session() as db:
        return _push_resolved_writeback_body(self, db, org_id, items)
