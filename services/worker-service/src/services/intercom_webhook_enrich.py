"""Intercom webhook enrichment module (webhook-enrich-module aspect).

Turns a `conversation.user.replied` / `conversation.rating.added` webhook event
into a MERGE into the existing per-conversation FeedbackItem — conversation id
extraction, item lookup, payload-first parts/rating extraction with a
`get_conversation` fallback, and merge via the #16 seams — returning a status
dict the core branch (core-branch-dispatch, next aspect) dispatches on.

CONTRACT (plan §1.2 — pinned by tests/test_intercom_webhook_enrich.py):

    enrich_webhook_item(db, source, event_type, event_data) -> dict
    {"status": str, "changed": bool, "feedback_id": int | None}

    status values:
      "enriched"           — item exists, merge ran (payload-first OR fallback).
                             `changed` is True iff item.text changed (new reply
                             parts); a rating-only merge is changed=False.
      "noop/no_item"       — conversation id missing/unparseable, or no
                             FeedbackItem for (org, intercom, conversation_id).
      "noop/not_found"     — fallback get_conversation → 404 (conversation gone
                             at Intercom). distinct from no_item for auditability.
      "error/auth_error"   — fallback 401/403, or token decrypt failure
                             (missing LLM_ENCRYPTION_KEY / InvalidToken —
                             non-transient, operator-recoverable config, plan A3).
      "error/no_connection" — no Intercom connection row resolvable for the org.

    IntercomTransientError (429/5xx/network) is the ONLY exception that escapes
    — the task's retry path. Every other branch returns a dict. There is NO
    swallowed-`except` anywhere in this module: a bare `except Exception` around
    an import here would silently disable the module while the UI shows it
    enabled (automations-delivery-integrity rule).

INVARIANTS:
  * Never creates items — strictly merge-into-existing (PRD D3).
  * Never touches customer_email (admin/bot rule — adapter contract).
  * Never commits / never dispatches re-analysis — the caller owns the
    transaction and the post-commit dispatch (house rule — this module only
    mutates the item in place; R4 belongs to core-branch-dispatch).

IMPORT DISCIPLINE (plan §2.2, sweep-safe):
  * Module-level: pure `intercom_parts.py` only.
  * Lazy (inside functions): `intercom_sync._enrich_conversation_replies`,
    `clients.intercom.{IntercomClient, IntercomAuthError, IntercomNotFoundError}`,
    `models.{FeedbackItem, Integration, IntercomIntegration}`,
    `cryptography.fernet.InvalidToken`.
  * The module imports NO backend-only path (`src.api`, `src.utils`,
    `src.services.automation_engine`, `src.services.health_score_service`,
    `src.models.feedback_workflow_event`) — test_worker_import_sweep.py scans
    every src/*.py including this file.

Because `IntercomClient` is lazy-imported inside `_fetch_conversation`, the
injectable-client test seam patches `src.clients.intercom.IntercomClient` (a
`from X import Y` resolves Y at call time) — NOT a module attribute.

See docs/planning/intercom-webhook-reply-rating/webhook-enrich-module/.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from src.adapters.intercom_parts import extract_rating, extract_reply_parts

logger = logging.getLogger(__name__)


def _decrypt(token: str) -> str:
    """Mirrors intercom_sync._decrypt / intercom_writeback._decrypt verbatim.

    House-local copy — the worker never imports backend `src.utils.encryption`.
    Raises ValueError when LLM_ENCRYPTION_KEY is unset; InvalidToken when the
    stored token does not decrypt under it.
    """
    from cryptography.fernet import Fernet

    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _resolve_connection(db, org_id):
    """Resolve the org's Intercom credential: token-paste first, then legacy OAuth.

    Mirrors intercom_writeback._resolve_connection (plan A1): the token-paste
    IntercomIntegration is org-scoped (uq_intercom_integrations_org_id), so no
    workspace matching is needed; the legacy OAuth Integration is matched by
    type == "intercom" + is_active. Returns (connection_row, kind) with kind
    "token_paste" | "oauth", or (None, None) when the org has no Intercom
    connection.
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


def _fetch_conversation(db, source, conversation_id) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Fallback: single `get_conversation(conversation_id)` fetch.

    Returns (conversation, None) on success; (None, status) on the mapped
    non-transient branches:
      error/no_connection — no Intercom connection row for the org
      error/auth_error   — token decrypt failure (config, non-retry)
      noop/not_found     — 404 (conversation gone at Intercom)
      error/auth_error   — 401/403
    IntercomTransientError (429/5xx/network) is NOT caught here — it propagates
    for task retry (the only exception that escapes this module).

    The decrypted token is never logged; log messages use org_id /
    conversation_id only (R3).
    """
    from cryptography.fernet import InvalidToken

    connection, kind = _resolve_connection(db, source.organization_id)
    if connection is None:
        return None, "error/no_connection"

    token_column = (
        connection.access_token
        if kind == "token_paste"
        else connection.oauth_access_token
    )
    try:
        token = _decrypt(token_column)
    except (ValueError, InvalidToken) as exc:  # non-transient config
        logger.error(
            "intercom_webhook_enrich: cannot decrypt the Intercom token for org %s: %s",
            source.organization_id,
            exc,
        )
        return None, "error/auth_error"

    from src.clients.intercom import (  # LAZY (see module docstring / plan §2.2)
        IntercomAuthError,
        IntercomClient,
        IntercomNotFoundError,
    )

    try:
        with IntercomClient(token) as client:
            return client.get_conversation(conversation_id), None
    except IntercomNotFoundError as exc:
        logger.info(
            "intercom_webhook_enrich: conversation %s gone: %s",
            conversation_id,
            exc,
        )
        return None, "noop/not_found"
    except IntercomAuthError as exc:
        logger.warning(
            "intercom_webhook_enrich: auth error org=%s: %s",
            source.organization_id,
            exc,
        )
        return None, "error/auth_error"
    # IntercomTransientError is NOT caught here — it propagates for task retry.


def enrich_webhook_item(db, source, event_type, event_data) -> dict:
    """Merge a replied/rating webhook event into the conversation's FeedbackItem.

    Steps (plan §2):
      1. Conversation id from event_data["data"]["item"]["id"] (defensive;
         missing/unparseable → noop/no_item, logged at WARNING, never a crash).
      2. Item lookup — org-scoped FeedbackItem(source="intercom",
         source_external_id==conversation_id); none → noop/no_item.
      3. Payload-first extraction from event_data["data"]["item"]; if neither
         parts nor rating → single get_conversation fallback.
      4. Merge via _enrich_conversation_replies (lazy import; idempotent by
         part_id; rating metadata-only; never touches customer_email).
      5. {"status": "enriched", "changed": changed, "feedback_id": item.id}.

    `event_type` is accepted for signature parity and logged only — both routed
    topics map to the same merge; topic-gating lives in core-branch-dispatch
    (plan A7). The `created` topic is out of scope here.

    Never creates, never commits, never dispatches. IntercomTransientError is
    the only exception that escapes (task retry path).
    """
    try:
        item = event_data["data"]["item"]
        conversation_id = item.get("id")
    except (KeyError, TypeError, AttributeError):
        conversation_id = None

    if not conversation_id:
        logger.warning(
            "intercom_webhook_enrich: no conversation id in %s payload (org %s)",
            event_type,
            getattr(source, "organization_id", None),
        )
        return {"status": "noop/no_item", "changed": False, "feedback_id": None}

    from src.models import FeedbackItem

    item_row = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.organization_id == source.organization_id,
            FeedbackItem.source == "intercom",
            FeedbackItem.source_external_id == conversation_id,
        )
        .first()
    )
    if item_row is None:
        return {"status": "noop/no_item", "changed": False, "feedback_id": None}

    parts = extract_reply_parts(item)
    rating = extract_rating(item)
    if not parts and not rating:
        conversation, fallback_status = _fetch_conversation(
            db, source, conversation_id
        )
        if fallback_status is not None:
            return {"status": fallback_status, "changed": False, "feedback_id": None}
        parts = extract_reply_parts(conversation)
        rating = extract_rating(conversation)

    from src.tasks.intercom_sync import _enrich_conversation_replies  # LAZY

    changed = _enrich_conversation_replies(db, item_row, parts, rating)

    return {"status": "enriched", "changed": changed, "feedback_id": item_row.id}
