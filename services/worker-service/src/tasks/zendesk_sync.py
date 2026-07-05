"""
Zendesk ticket-pull sync tasks (ingestion-pull aspect).

Tasks:
  sync_all_zendesk  — fan-out over orgs with active Zendesk integrations
  sync_zendesk_org  — per-org retryable sync (max_retries=3)

Core (Celery-free, tested directly):
  _sync_org — poll GET /api/v2/incremental/tickets (unix-seconds cursor),
              synthesize a "ticket.created" event per ticket, and route it
              through the SHARED ingestion core
              (src.tasks.source_events._find_matching_sources /
              _process_event_for_source) — NOT ad-hoc FeedbackItem
              creation. This reuses the exact FeedbackSourceEvent dedup
              path the webhook entry point (ingestion-webhook) also uses.

Both hard constraints carried from ingestion-core:
  1. `subdomain` placed into event_data/provider_context is ALWAYS
     `integ.subdomain` (the trusted ZendeskIntegration column) — never
     anything derived from the ticket payload itself.
  2. ZendeskIntegration has no `source.integration_id` FK, so this task
     does NOT rely on `_process_event_for_source`'s generic
     `Integration.oauth_access_token` lookup for `fetch_context`
     enrichment. Per plan D1b/§1b, requester email is resolved entirely
     client-side (ZendeskClient.incremental_tickets side-loads `users` and
     merges a flat `requester_email` onto each ticket) BEFORE the ticket
     ever reaches the shared core, so no FeedbackSource in this aspect's
     tests needs `include_context`/`include_author` set and
     `fetch_context`'s `access_token` parameter is never exercised by this
     task. See docs/planning/zendesk-integration/ingestion-pull/plan_20260705.md
     §1b for why this was locked as out-of-scope for the pull path, and the
     impl report for how a future aspect needing richer context should wire
     the `source.source_type == "zendesk"` access-token branch instead of
     assuming the generic lookup covers it.

D1 (plan): cursor = ZendeskIntegration.last_synced_at, falling back to
    connected_at if NULL (never epoch/None — no historical backfill).
D2 (plan): in-process core call, not a second Celery hop per ticket —
    _sync_org calls _find_matching_sources/_process_event_for_source
    directly inside the same DB session as the rest of the org's sync.
D3 (plan): every ticket returned by the incremental endpoint (new OR
    updated since cursor) is synthesized as event_type="ticket.created" —
    "one feedback item per ticket, ever" is enforced by FeedbackSourceEvent
    dedup on ticket id, not by this task guessing new-vs-updated.
D7 (plan): a static Zendesk API-token auth failure is operator-recoverable
    (unlike Salesforce's invalid_grant) — last_sync_status/last_error are
    recorded WITHOUT disconnecting (is_active untouched) and without
    raising/retrying.

R3: the api_token is never logged. Log messages use integration_id/org_id only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error).

Beat schedule: every 15 minutes (interval, not crontab — a fixed cadence
like process-unanalyzed-feedback's 30.0, not a specific wall-clock time).
Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from celery import shared_task

from src.clients.zendesk import ZendeskAuthError, ZendeskClient, ZendeskTransientError
from src.database import get_db_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local token decryption (mirrors hubspot_sync.py / salesforce_sync.py _decrypt)
# R6: Worker cannot import from backend-api; uses its own Fernet helper.
# ---------------------------------------------------------------------------


def _decrypt(token: str) -> str:
    """Decrypt a Fernet-encrypted string using LLM_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _to_unix_ts(dt: datetime) -> int:
    """Convert a naive UTC datetime (the convention used throughout this
    codebase — see datetime.utcnow() elsewhere) to a unix timestamp."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Core sync logic (Celery-free — tested directly)
# ---------------------------------------------------------------------------


def _sync_org(org_id: int, db, client: ZendeskClient, integ) -> Dict[str, Any]:
    """
    Pull new/updated Zendesk tickets for one org since the stored cursor,
    and route each one through the shared ingestion core.

    Parameters
    ----------
    org_id : organization ID being synced (== integ.organization_id)
    db     : SQLAlchemy session (caller manages transaction)
    client : ZendeskClient instance (caller manages lifecycle)
    integ  : ZendeskIntegration row (cursor is read from AND written to
             this instance — caller flushes/commits)

    Returns
    -------
    dict with keys: tickets_seen, tickets_ingested, no_source_match, end_time
    """
    from src.adapters import get_adapter
    from src.tasks.source_events import _find_matching_sources, _process_event_for_source

    # D1: cursor = last_synced_at, falling back to connected_at if a row is
    # ever found with a NULL cursor (defensive — never epoch/None, so a
    # missing cursor can never cause a historical backfill).
    cursor_dt = integ.last_synced_at or integ.connected_at
    start_time = _to_unix_ts(cursor_dt)

    # Hard constraint #1: subdomain is ALWAYS the trusted
    # ZendeskIntegration column — never derived from ticket payload data.
    subdomain = integ.subdomain

    poll_result = client.incremental_tickets(start_time=start_time)
    tickets = poll_result.get("tickets", [])
    end_time = poll_result.get("end_time", start_time)
    tickets_seen = len(tickets)

    sources = _find_matching_sources(db, "zendesk", {"subdomain": subdomain})

    if not sources:
        # Logged no-op (PRD 9a/9b) — never a crash, never a silent success.
        # Cursor still advances so we don't re-poll the exact same window
        # forever; per PRD scope this task ingests new tickets only, so a
        # source created later simply starts capturing from then on.
        integ.last_synced_at = datetime.utcfromtimestamp(end_time)
        return {
            "tickets_seen": tickets_seen,
            "tickets_ingested": 0,
            "no_source_match": True,
            "end_time": end_time,
        }

    adapter = get_adapter("zendesk")
    tickets_ingested = 0

    for ticket in tickets:
        ticket_id = ticket.get("id")
        event_data = {"ticket": ticket, "subdomain": subdomain}

        for source in sources:
            proc_result = _process_event_for_source(
                db=db,
                source=source,
                adapter=adapter,
                external_event_id=f"zendesk-pull-{integ.id}-{ticket_id}-{end_time}",
                event_type="ticket.created",
                event_data=event_data,
            )
            if proc_result.get("status") == "feedback_created":
                tickets_ingested += 1

    integ.last_synced_at = datetime.utcfromtimestamp(end_time)

    return {
        "tickets_seen": tickets_seen,
        "tickets_ingested": tickets_ingested,
        "no_source_match": False,
        "end_time": end_time,
    }


# ---------------------------------------------------------------------------
# Task implementation body (extracted so it can be called directly in tests)
# ---------------------------------------------------------------------------


def _sync_zendesk_org_body(task_self, integration_id: int) -> Dict[str, Any]:
    """
    Inner logic of sync_zendesk_org. Extracted as a plain function so
    hardening tests can call it directly without Celery machinery.
    """
    from src.models import ZendeskIntegration

    with get_db_session() as db:
        integ = (
            db.query(ZendeskIntegration)
            .filter(ZendeskIntegration.id == integration_id)
            .first()
        )
        if not integ:
            return {"status": "not_found", "integration_id": integration_id}
        if not integ.is_active:
            return {"status": "inactive", "integration_id": integration_id}

        # R6: missing LLM_ENCRYPTION_KEY → non-transient config error; do not retry
        try:
            token = _decrypt(integ.api_token)
        except ValueError:
            logger.error(
                "zendesk_sync: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt api_token; skipping (integration_id=%s)",
                integ.organization_id,
                integration_id,
            )
            integ.last_sync_status = "error"
            integ.last_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        try:
            with ZendeskClient(
                subdomain=integ.subdomain,
                email=integ.email,
                api_token=token,
            ) as client:
                result = _sync_org(integ.organization_id, db, client, integ)

            if result.get("no_source_match"):
                integ.last_sync_status = "no_source"
                integ.last_error = (
                    f"No active zendesk FeedbackSource matched subdomain "
                    f"'{integ.subdomain}' — {result['tickets_seen']} ticket(s) "
                    f"seen but not ingested"
                )
            else:
                integ.last_sync_status = "success"
                integ.last_error = None

            db.flush()
            return {"status": "success", **result}

        except ZendeskAuthError as exc:
            # D7: a static API-token auth failure is operator-recoverable
            # (re-enter the token) — unlike Salesforce's invalid_grant, this
            # does NOT disconnect the integration (is_active untouched), and
            # does NOT raise/retry.
            logger.error(
                "zendesk_sync: auth error for org=%s (integration_id=%s): %s",
                integ.organization_id,
                integration_id,
                exc,
            )
            integ.last_sync_status = "error"
            integ.last_error = str(exc)[:500]
            db.flush()
            return {"status": "error", "reason": "auth_error"}

        except ZendeskTransientError as exc:
            logger.warning(
                "zendesk_sync: transient error for org=%s (integration_id=%s): %s",
                integ.organization_id,
                integration_id,
                exc,
            )
            integ.last_sync_status = "retrying"
            integ.last_error = str(exc)
            db.flush()
            raise task_self.retry(exc=exc)

        except Exception as exc:
            logger.error(
                "zendesk_sync: unhandled error for org=%s (integration_id=%s): %s",
                integ.organization_id,
                integration_id,
                exc,
                exc_info=True,
            )
            integ.last_sync_status = "error"
            integ.last_error = str(exc)[:500]
            db.flush()
            raise


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------


@shared_task(name="src.tasks.zendesk_sync.sync_all_zendesk")
def sync_all_zendesk() -> Dict[str, Any]:
    """
    Fan-out: scan all active Zendesk integrations and enqueue per-org sync.

    Per-org try/except ensures one failure never aborts the batch.
    """
    from src.models import ZendeskIntegration

    with get_db_session() as db:
        integrations = (
            db.query(ZendeskIntegration)
            .filter(ZendeskIntegration.is_active.is_(True))
            .all()
        )
        if not integrations:
            return {"status": "no_integrations", "queued": 0}

        queued = 0
        for integ in integrations:
            try:
                sync_zendesk_org.delay(integ.id)
                queued += 1
            except Exception as exc:
                logger.error(
                    "sync_all_zendesk: failed to enqueue org=%s (integration_id=%s): %s",
                    integ.organization_id,
                    integ.id,
                    exc,
                )

        return {"status": "queued", "queued": queued}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.zendesk_sync.sync_zendesk_org",
)
def sync_zendesk_org(self, integration_id: int) -> Dict[str, Any]:
    """
    Per-org Zendesk sync. Retries on ZendeskTransientError (max 3x).
    R6: missing LLM_ENCRYPTION_KEY returns error dict without retrying.
    Auth failure marks last_sync_status/last_error without raising/retrying.
    """
    return _sync_zendesk_org_body(self, integration_id)
