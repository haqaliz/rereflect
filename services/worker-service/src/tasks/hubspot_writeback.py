"""
HubSpot CRM writeback task (writeback-task-trigger aspect).

Task:
  push_health_to_hubspot(org_id, customer_email) — idempotent, gated,
  soft-pausing push of a customer's current health score to HubSpot.

R3: access_token is never logged. Log messages use org_id / customer_email only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error) — mirrors hubspot_sync.py.

Soft-pause semantics: permanent failures (missing write scope, field not found,
contact not found) are recorded on the integration row's `last_writeback_*`
columns but NEVER set `is_active=False` — that flag is owned exclusively by
the read-sync task (hubspot_sync.py). A subsequent inbound sync must always
still succeed after a writeback soft-pause.

Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from celery import shared_task

from src.clients.hubspot import (
    HubSpotClient,
    HubSpotNotFoundError,
    HubSpotScopeError,
    HubSpotTransientError,
)
from src.database import get_db_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local token decryption (verbatim copy of hubspot_sync.py's _decrypt helper)
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
# Task implementation body (extracted so it can be called directly in tests)
# ---------------------------------------------------------------------------


def _push_health_to_hubspot_body(task_self, org_id: int, customer_email: str) -> dict:
    """
    Inner logic of push_health_to_hubspot. Extracted as a plain function so
    tests can call it directly without Celery machinery.
    """
    from src.models import CrmEnrichment, CustomerHealth, HubSpotIntegration

    with get_db_session() as db:
        integ = (
            db.query(HubSpotIntegration)
            .filter(HubSpotIntegration.organization_id == org_id)
            .first()
        )
        if not integ or not integ.is_active:
            return {"status": "noop", "reason": "integration_inactive"}
        if not integ.writeback_enabled:
            return {"status": "noop", "reason": "writeback_disabled"}
        field_name = (integ.writeback_field_name or "").strip()
        if not field_name:
            return {"status": "noop", "reason": "no_field_name"}

        enrichment = (
            db.query(CrmEnrichment)
            .filter(
                CrmEnrichment.organization_id == org_id,
                CrmEnrichment.customer_email == customer_email,
            )
            .first()
        )
        if not enrichment:
            return {"status": "noop", "reason": "no_enrichment"}
        if not enrichment.hubspot_contact_id:
            return {"status": "noop", "reason": "no_contact_id"}

        health = (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.organization_id == org_id,
                CustomerHealth.customer_email == customer_email,
            )
            .first()
        )
        if not health:
            return {"status": "noop", "reason": "no_health_row"}

        score = health.health_score
        last_written = enrichment.last_written_health_score
        if last_written is not None:
            if score == last_written:
                return {"status": "noop", "reason": "score_unchanged"}
            if abs(score - last_written) < 2:
                return {"status": "noop", "reason": "change_too_small"}

        # R6: missing LLM_ENCRYPTION_KEY -> non-transient config error; do not retry
        try:
            token = _decrypt(integ.access_token)
        except ValueError:
            logger.error(
                "hubspot_writeback: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt token; skipping",
                org_id,
            )
            integ.last_writeback_status = "error"
            integ.last_writeback_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        now = datetime.utcnow()
        try:
            with HubSpotClient(token) as client:
                # Validate the property still exists before pushing. A 404
                # here means the *field* is gone — distinct from a missing
                # *contact*, which is only detectable from the PATCH below.
                try:
                    prop_def = client.get_contact_property_def(field_name)
                except HubSpotNotFoundError:
                    prop_def = None

                if prop_def is None:
                    integ.last_writeback_status = "field_not_found"
                    integ.last_writeback_error = f"Property '{field_name}' not found"
                    integ.last_writeback_at = now
                    db.flush()
                    return {"status": "error", "reason": "field_not_found"}

                client.update_contact_property(
                    enrichment.hubspot_contact_id, field_name, score
                )

            enrichment.last_written_health_score = score
            enrichment.last_health_written_at = now
            integ.last_writeback_at = now
            integ.last_writeback_status = "ok"
            integ.last_writeback_error = None
            integ.contacts_written = (integ.contacts_written or 0) + 1
            db.flush()
            return {"status": "ok"}

        except HubSpotScopeError as exc:
            # Soft-pause: never touch is_active — that's the read-sync's flag.
            logger.warning(
                "hubspot_writeback: scope error for org=%s (email=%s): %s",
                org_id, customer_email, exc,
            )
            integ.last_writeback_status = "error: missing_write_scope"
            integ.last_writeback_error = str(exc)[:500]
            integ.last_writeback_at = now
            db.flush()
            return {"status": "error", "reason": "missing_write_scope"}

        except HubSpotNotFoundError as exc:
            # Property already validated to exist above -> this 404 is the
            # contact. Per-customer skip; does not pause the whole org.
            logger.warning(
                "hubspot_writeback: contact not found for org=%s (email=%s): %s",
                org_id, customer_email, exc,
            )
            integ.last_writeback_status = "contact_not_found"
            integ.last_writeback_error = str(exc)[:500]
            integ.last_writeback_at = now
            db.flush()
            return {"status": "error", "reason": "contact_not_found"}

        except HubSpotTransientError as exc:
            logger.warning(
                "hubspot_writeback: transient error for org=%s (email=%s): %s",
                org_id, customer_email, exc,
            )
            integ.last_writeback_status = "retrying"
            integ.last_writeback_error = str(exc)[:500]
            db.flush()
            raise task_self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.hubspot_writeback.push_health_to_hubspot",
)
def push_health_to_hubspot(self, org_id: int, customer_email: str) -> dict:
    """
    Push a customer's current health score to HubSpot as a contact property.

    Idempotent (no-ops when unchanged / < 2pt from last-written), gated to
    opted-in orgs, and soft-pausing on permanent failures — never disables the
    integration (is_active is owned exclusively by the read-sync task).
    """
    return _push_health_to_hubspot_body(self, org_id, customer_email)
