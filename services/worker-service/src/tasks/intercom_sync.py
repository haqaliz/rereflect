"""
Intercom conversation-pull sync tasks (pull-sync aspect).

Tasks:
  sync_all_intercom  — fan-out over orgs with active Intercom integrations
  sync_intercom_org  — per-org retryable sync (max_retries=3)

Core (Celery-free, tested directly):
  _sync_org — page through POST /conversations/search filtered on updated_at,
              synthesize a "conversation.user.created" event per conversation,
              and route it through the SHARED ingestion core
              (src.tasks.source_events._find_matching_sources /
              _process_event_for_source) — NOT ad-hoc FeedbackItem creation.
              This reuses the exact FeedbackSourceEvent dedup path the webhook
              entry point also uses, so pull and webhook can never diverge on
              "one feedback item per conversation".

Decisions inherited from zendesk_sync.py (asserted in tests, not assumed):

D1: cursor = IntercomIntegration.last_synced_at, falling back to connected_at
    if NULL (never epoch/None — a missing cursor can never cause a historical
    backfill of the whole workspace).
D2: in-process core calls, not a second Celery hop per conversation — _sync_org
    calls _find_matching_sources/_process_event_for_source directly inside the
    same DB session as the rest of the org's sync.
D3: every conversation is synthesized as "conversation.user.created";
    "one feedback item per conversation, ever" is enforced by
    FeedbackSourceEvent dedup on the conversation id, not by this task guessing
    new-vs-updated.
D7: a static auth failure is operator-recoverable — last_sync_status/last_error
    are recorded WITHOUT disconnecting (is_active untouched) and without
    raising/retrying. Disconnecting an org over a typo'd token would be a
    surprising destructive act they never asked for.

WHERE THIS DIVERGES FROM ZENDESK, deliberately:
Zendesk's incremental endpoint returns an authoritative `end_time` watermark to
store as the next cursor. Intercom's conversation search has no equivalent, so
the cursor is derived from the maximum `updated_at` observed in the run. To make
that lossless the query uses `>=` (see clients/intercom.py) and the cursor only
ever moves forward — an empty page leaves it untouched rather than advancing it
to "now", which would skip anything created during the request.

R3: the access token is never logged. Log messages use integration_id/org_id.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error",
    "reason": "missing_encryption_key"} and does NOT retry (config, not transient).

Beat schedule: every 15 minutes (interval, matching zendesk_sync).
Registration: see src/celery_app.py include list.

See docs/planning/intercom-selfhost-ingestion/pull-sync/.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from celery import shared_task

from src.clients.intercom import (
    IntercomAuthError,
    IntercomClient,
    IntercomTransientError,
)
from src.database import get_db_session

logger = logging.getLogger(__name__)

# Bound the work a single run can do, so one org with a large backlog cannot
# hold the worker (and its DB transaction) open indefinitely. The cursor still
# advances, so the remainder is picked up on the next tick rather than lost.
MAX_PAGES_PER_RUN = 20

# R1b per-run cap on conversation-detail fetches. Search pages are <=150
# conversations x 20 pages = <=3000/run; 500 bounds the detail fan-out while
# the cursor resumes (R5). Dropped conversations are counted and logged, never
# silent — the same house rule as usage_decline_label_detector's cap.
MAX_DETAIL_FETCHES_PER_RUN = 500


def _decrypt(token: str) -> str:
    """Mirrors zendesk_sync._decrypt / hubspot_sync._decrypt."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _to_unix_ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _persist_terminal_status(integration_id: int, status: str, error: str) -> None:
    """Record a terminal outcome in its own session.

    Separate session on purpose: the caller's transaction may be rolled back by
    the failure, and losing the diagnostic with it is how an operator ends up
    staring at an integration that silently does nothing.
    """
    from src.models import IntercomIntegration

    with get_db_session() as db:
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.id == integration_id)
            .first()
        )
        if row:
            row.last_sync_status = status
            row.last_error = error[:2000] if error else None
            row.updated_at = datetime.utcnow()
            db.commit()


def _enrich_conversation_replies(db, item, reply_parts, rating) -> bool:
    """Merge NEW reply parts into item.text and item.source_metadata.

    Diff is by part_id membership against source_metadata["replies"].
    Returns True iff item.text actually changed (new replies merged);
    a rating-only update returns False (metadata changed, no re-analysis).

    Never touches customer_email (admin/bot rule — adapter contract).
    """
    from src.adapters.intercom_parts import format_reply_merge, new_reply_parts

    metadata = dict(item.source_metadata or {})

    # Collapse duplicate part_ids within one payload: a part is merged once.
    seen: set = set()
    unique_parts = []
    for part in reply_parts:
        if part["part_id"] not in seen:
            seen.add(part["part_id"])
            unique_parts.append(part)

    merged_part_ids = [r["part_id"] for r in metadata.get("replies", [])]
    new_parts = new_reply_parts(unique_parts, merged_part_ids)

    text_changed = False
    if new_parts:
        blocks = "".join(format_reply_merge(p) for p in new_parts)
        item.text = (item.text or "") + blocks
        metadata["replies"] = list(metadata.get("replies", [])) + new_parts
        text_changed = True

    if rating is not None:
        # Metadata mirrors the adapter's "keys omitted when absent" contract.
        for key in ("rating", "remark", "rated_at"):
            if key in rating:
                metadata[key] = rating[key]
            else:
                metadata.pop(key, None)

    if metadata != (item.source_metadata or {}):
        item.source_metadata = metadata

    return text_changed


def _sync_org(org_id: int, db, client: IntercomClient, integ) -> Dict[str, Any]:
    """Pull conversations for one org since the stored cursor.

    Parameters
    ----------
    org_id : organization ID being synced (== integ.organization_id)
    db     : SQLAlchemy session (caller manages the transaction)
    client : IntercomClient (caller manages lifecycle)
    integ  : IntercomIntegration row — the cursor is read from AND written to
             this instance; the caller flushes/commits

    Returns
    -------
    dict: conversations_seen, conversations_ingested, no_source_match, cursor
    """
    from src.adapters import get_adapter
    from src.adapters.intercom_parts import extract_rating, extract_reply_parts
    from src.models import FeedbackItem
    from src.tasks.source_events import _find_matching_sources, _process_event_for_source

    # D1 — never epoch/None.
    cursor_dt = integ.last_synced_at or integ.connected_at
    updated_since = _to_unix_ts(cursor_dt)

    # The workspace_id placed into provider_context is ALWAYS the trusted
    # IntercomIntegration column, never anything derived from payload data.
    # Same hard constraint zendesk_sync carries for subdomain.
    workspace_id = integ.workspace_id

    sources = _find_matching_sources(db, "intercom", {"workspace_id": workspace_id})

    conversations_seen = 0
    conversations_ingested = 0
    changed_feedback_ids: list = []
    detail_fetches = 0
    dropped_by_cap = 0
    max_updated_at: Optional[int] = None
    starting_after: Optional[str] = None
    pages = 0

    while pages < MAX_PAGES_PER_RUN:
        conversations, next_cursor, _total_count = client.search_conversations(
            updated_since=updated_since, starting_after=starting_after
        )
        pages += 1
        conversations_seen += len(conversations)

        for conversation in conversations:
            updated_at = conversation.get("updated_at")
            if isinstance(updated_at, int):
                max_updated_at = (
                    updated_at if max_updated_at is None else max(max_updated_at, updated_at)
                )

            if not sources:
                continue

            conversation_id = conversation.get("id")
            # D3 — the adapter's contract is the webhook envelope, so the pull
            # path hands it exactly that shape. One extraction path, one dedup.
            event_data = {
                "topic": "conversation.user.created",
                "data": {"item": conversation},
            }

            for source in sources:
                result = _process_event_for_source(
                    db=db,
                    source=source,
                    adapter=get_adapter("intercom"),
                    external_event_id=f"intercom-pull-{integ.id}-{conversation_id}",
                    event_type="conversation.user.created",
                    event_data=event_data,
                )
                if result.get("status") == "feedback_created":
                    conversations_ingested += 1

            # ── Enrichment pass (pull-enrichment) ──────────────────────────
            # Merge new reply parts + the rating into the item the event loop
            # just created (or already existed from a previous run). R1b: the
            # search object carries no parts, so fetch the detail — bounded by
            # the per-run cap. If the search object does carry parts (a live
            # shape some deployments return), use them and skip the fetch.
            parts = extract_reply_parts(conversation)
            rating = extract_rating(conversation)
            if not parts and not rating:
                if detail_fetches >= MAX_DETAIL_FETCHES_PER_RUN:
                    # Dropped, not lost: the cursor already advanced for this
                    # conversation on the search side, so it is re-seen when
                    # it next updates. No silent caps — counted and logged.
                    dropped_by_cap += 1
                    continue
                detail = client.get_conversation(conversation_id)
                detail_fetches += 1
                parts = extract_reply_parts(detail)
                rating = extract_rating(detail)
            if not parts and not rating:
                continue
            # ix_feedback_items_org_source_external serves this exact shape.
            item = (
                db.query(FeedbackItem)
                .filter(
                    FeedbackItem.organization_id == org_id,
                    FeedbackItem.source == "intercom",
                    FeedbackItem.source_external_id == conversation_id,
                )
                .first()
            )
            if item is None:
                continue
            if _enrich_conversation_replies(db, item, parts, rating):
                changed_feedback_ids.append(item.id)

        if not next_cursor:
            break
        starting_after = next_cursor
    else:
        logger.warning(
            "Intercom pull hit the %s-page cap for integration %s; "
            "the remainder resumes on the next run",
            MAX_PAGES_PER_RUN,
            integ.id,
        )

    if dropped_by_cap:
        # House rule: no silent caps (usage_decline_label_detector precedent).
        logger.warning(
            "Intercom pull: detail-fetch per-run cap reached integration=%s "
            "cap=%s dropped_by_cap=%s",
            integ.id,
            MAX_DETAIL_FETCHES_PER_RUN,
            dropped_by_cap,
        )

    # The cursor only ever moves FORWARD. An empty page leaves it alone rather
    # than advancing to "now", which would skip anything created mid-request.
    if max_updated_at is not None:
        candidate = datetime.utcfromtimestamp(max_updated_at)
        if integ.last_synced_at is None or candidate > integ.last_synced_at:
            integ.last_synced_at = candidate

    if not sources:
        # Logged no-op, never a crash and never a silent success.
        logger.info(
            "Intercom pull: no matching feedback source for org %s (integration %s)",
            org_id,
            integ.id,
        )

    return {
        "conversations_seen": conversations_seen,
        "conversations_ingested": conversations_ingested,
        "changed_feedback_ids": changed_feedback_ids,
        "dropped_by_cap": dropped_by_cap,
        "no_source_match": not sources,
        "cursor": max_updated_at,
    }


def _sync_intercom_org_body(task_self, integration_id: int) -> Dict[str, Any]:
    """Task body, extracted so tests can call it without a broker."""
    from src.models import IntercomIntegration

    client: Optional[IntercomClient] = None
    try:
        with get_db_session() as db:
            integ = (
                db.query(IntercomIntegration)
                .filter(
                    IntercomIntegration.id == integration_id,
                    IntercomIntegration.is_active == True,  # noqa: E712
                )
                .first()
            )
            if not integ:
                return {"status": "skipped", "reason": "not_found_or_inactive"}

            try:
                access_token = _decrypt(integ.access_token)
            except ValueError as exc:
                # R6 — configuration error, not transient. Do not retry.
                logger.error(
                    "Intercom sync for integration %s cannot decrypt its token: %s",
                    integration_id,
                    exc,
                )
                return {"status": "error", "reason": "missing_encryption_key"}

            client = IntercomClient(access_token)
            org_id = integ.organization_id

            try:
                result = _sync_org(org_id, db, client, integ)
            except IntercomAuthError as exc:
                # D7 — record, do not disconnect, do not retry.
                db.rollback()
                _persist_terminal_status(integration_id, "auth_error", str(exc))
                logger.error(
                    "Intercom sync auth failure for integration %s (org %s)",
                    integration_id,
                    org_id,
                )
                return {"status": "error", "reason": "auth_error"}

            integ.last_sync_status = "ok"
            integ.last_error = None
            integ.updated_at = datetime.utcnow()
            db.commit()

            # Re-analysis dispatch — AFTER the commit, never before, never
            # inside _sync_org: the batch task opens a fresh session and reads
            # the item's text, so a pre-commit dispatch would analyze stale
            # content (pinned ordering, plan §1.3). Guarded so a failed seam
            # call can never break the sync — the seam's own task retries.
            from src.tasks.analysis import reanalyze_feedback

            for feedback_id in result.get("changed_feedback_ids", []):
                try:
                    reanalyze_feedback(db, feedback_id)
                except Exception:
                    logger.exception(
                        "Intercom pull: re-analysis dispatch failed for feedback "
                        "%s (integration %s)",
                        feedback_id,
                        integration_id,
                    )

            from src.cache import cache_invalidate

            cache_invalidate(f"dashboard:{org_id}:*")
            cache_invalidate(f"analytics:{org_id}:*")

            logger.info(
                "Intercom pull for integration %s: %s seen, %s ingested",
                integration_id,
                result["conversations_seen"],
                result["conversations_ingested"],
            )
            return {"status": "ok", **result}

    except IntercomTransientError as exc:
        _persist_terminal_status(integration_id, "transient_error", str(exc))
        logger.warning(
            "Intercom sync transient failure for integration %s: %s",
            integration_id,
            exc,
        )
        raise task_self.retry(exc=exc)
    finally:
        if client is not None:
            client.close()


@shared_task(name="src.tasks.intercom_sync.sync_all_intercom")
def sync_all_intercom() -> Dict[str, Any]:
    """Fan out a per-org sync for every active Intercom integration."""
    from src.models import IntercomIntegration

    with get_db_session() as db:
        integration_ids = [
            row.id
            for row in db.query(IntercomIntegration)
            .filter(IntercomIntegration.is_active == True)  # noqa: E712
            .all()
        ]

    for integration_id in integration_ids:
        sync_intercom_org.delay(integration_id)

    return {"status": "dispatched", "count": len(integration_ids)}


@shared_task(
    bind=True,
    name="src.tasks.intercom_sync.sync_intercom_org",
    max_retries=3,
    default_retry_delay=60,
)
def sync_intercom_org(self, integration_id: int) -> Dict[str, Any]:
    return _sync_intercom_org_body(self, integration_id)
