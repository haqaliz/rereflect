"""
Salesforce CRM writeback task (push-task-trigger aspect).

Task:
  push_health_to_salesforce(org_id, customer_email) — idempotent, gated,
  soft-pausing push of a customer's current health score to a Salesforce
  Contact field.

R3: refresh_token/access_token are never logged. Log messages use org_id /
customer_email only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error",
    "reason": "missing_encryption_key"} and does NOT retry (non-transient
    config error) — mirrors salesforce_sync.py / hubspot_writeback.py.

Soft-pause semantics: permanent failures (missing write scope, field not
found, contact not found, daily API limit) are recorded on the integration
row's `last_writeback_*` columns but NEVER set `is_active=False` — that flag
is owned exclusively by the read-sync task (salesforce_sync.py). A
subsequent inbound sync must always still succeed after a writeback
soft-pause.

Contact-id resolution: the matched Contact Id is normally already persisted
on CrmEnrichment.salesforce_contact_id by salesforce_sync.py. If it is null
(e.g. the row predates that sync change, or was cleared), this task falls
back to a bounded SOQL lookup by email, deterministically picks the lowest
Id on a duplicate match (recording a soft `ambiguous_contact` note without
failing the push), and persists the resolved Id back onto the enrichment row
so subsequent pushes don't need to re-resolve it.

Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from celery import shared_task

from src.clients.salesforce import (
    SalesforceClient,
    SalesforceNotFoundError,
    SalesforceScopeError,
    SalesforceTransientError,
)
from src.database import get_db_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Salesforce Connected App / OAuth configuration — read at call time (not
# baked in at import) so tests can override via patch.dict(os.environ, ...).
# Mirrors src/tasks/salesforce_sync.py.
# ---------------------------------------------------------------------------


def _client_id() -> str:
    return os.environ.get("SALESFORCE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.environ.get("SALESFORCE_CLIENT_SECRET", "")


def _login_base() -> str:
    return os.environ.get("SALESFORCE_LOGIN_BASE", "https://login.salesforce.com")


def _api_version() -> str:
    return os.environ.get("SALESFORCE_API_VERSION", "v60.0")


# ---------------------------------------------------------------------------
# Local token decryption (verbatim copy of hubspot_writeback.py's _decrypt
# helper). R6: Worker cannot import from backend-api; uses its own Fernet
# helper.
# ---------------------------------------------------------------------------


def _decrypt(token: str) -> str:
    """Decrypt a Fernet-encrypted string using LLM_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _escape_soql_string(value: str) -> str:
    """Escape a value for safe interpolation into a single-quoted SOQL literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _resolve_contact_id_by_email(client: SalesforceClient, email: str) -> tuple:
    """
    Bounded SOQL lookup for a Contact Id by email (fallback when
    CrmEnrichment.salesforce_contact_id is null).

    Returns (contact_id_or_None, ambiguous: bool). On >1 match, the lowest
    Id is chosen deterministically and `ambiguous` is True (soft — caller
    should still write to the chosen contact and record a non-fatal note).
    """
    escaped = _escape_soql_string(email)
    soql = f"SELECT Id FROM Contact WHERE Email = '{escaped}'"
    records = client.query(soql)
    if not records:
        return None, False
    chosen = min(records, key=lambda r: str(r.get("Id")))
    return chosen.get("Id"), len(records) > 1


# ---------------------------------------------------------------------------
# Task implementation body (extracted so it can be called directly in tests)
# ---------------------------------------------------------------------------


def _push_health_to_salesforce_body(task_self, org_id: int, customer_email: str) -> dict:
    """
    Inner logic of push_health_to_salesforce. Extracted as a plain function
    so tests can call it directly without Celery machinery.
    """
    from src.models import CrmEnrichment, CustomerHealth, SalesforceIntegration

    with get_db_session() as db:
        integ = (
            db.query(SalesforceIntegration)
            .filter(SalesforceIntegration.organization_id == org_id)
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
            refresh_token = _decrypt(integ.refresh_token)
        except ValueError:
            logger.error(
                "salesforce_writeback: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt refresh_token; skipping",
                org_id,
            )
            integ.last_writeback_status = "error"
            integ.last_writeback_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        now = datetime.utcnow()
        try:
            with SalesforceClient(
                refresh_token=refresh_token,
                instance_url=integ.instance_url,
                client_id=_client_id(),
                client_secret=_client_secret(),
                login_base=_login_base(),
                api_version=_api_version(),
            ) as client:
                contact_id = enrichment.salesforce_contact_id
                ambiguous = False

                if not contact_id:
                    contact_id, ambiguous = _resolve_contact_id_by_email(
                        client, customer_email
                    )
                    if not contact_id:
                        return {"status": "noop", "reason": "no_contact_id"}
                    enrichment.salesforce_contact_id = contact_id
                    db.flush()

                # Validate the field still exists (and is writeable) before
                # pushing — mirrors HubSpot's get_contact_property_def check.
                describe = client.describe_object("Contact")
                field_names = {f.get("name") for f in describe.get("fields", [])}
                if field_name not in field_names:
                    integ.last_writeback_status = "field_not_found"
                    integ.last_writeback_error = f"Field '{field_name}' not found"
                    integ.last_writeback_at = now
                    db.flush()
                    return {"status": "error", "reason": "field_not_found"}

                client.update_contact_field(contact_id, field_name, score)

            enrichment.last_written_health_score = score
            enrichment.last_health_written_at = now
            integ.last_writeback_at = now
            integ.last_writeback_status = "ok"
            integ.last_writeback_error = "ambiguous_contact" if ambiguous else None
            integ.contacts_written = (integ.contacts_written or 0) + 1
            db.flush()
            return {"status": "ok"}

        except SalesforceScopeError as exc:
            # Soft-pause: never touch is_active — that's the read-sync's flag.
            logger.warning(
                "salesforce_writeback: scope error for org=%s (email=%s): %s",
                org_id, customer_email, exc,
            )
            integ.last_writeback_status = "error: missing_write_scope"
            integ.last_writeback_error = str(exc)[:500]
            integ.last_writeback_at = now
            db.flush()
            return {"status": "error", "reason": "missing_write_scope"}

        except SalesforceNotFoundError as exc:
            # Field already validated to exist above -> this 404 is the
            # contact. Per-customer skip; does not pause the whole org.
            logger.warning(
                "salesforce_writeback: contact not found for org=%s (email=%s): %s",
                org_id, customer_email, exc,
            )
            integ.last_writeback_status = "contact_not_found"
            integ.last_writeback_error = str(exc)[:500]
            integ.last_writeback_at = now
            db.flush()
            return {"status": "error", "reason": "contact_not_found"}

        except SalesforceTransientError as exc:
            msg = str(exc)
            # Salesforce's org-wide daily API request limit surfaces as a
            # 429; distinguish it from a generic 5xx blip so operators see
            # "deferred: daily_limit" rather than a bare "retrying" — still
            # retries (never a silent drop), per PRD.
            if "429" in msg:
                logger.warning(
                    "salesforce_writeback: daily API limit hit for org=%s "
                    "(email=%s): %s",
                    org_id, customer_email, exc,
                )
                integ.last_writeback_status = "deferred: daily_limit"
                integ.last_writeback_error = msg[:500]
                integ.last_writeback_at = now
                db.flush()
                raise task_self.retry(exc=exc)

            logger.warning(
                "salesforce_writeback: transient error for org=%s (email=%s): %s",
                org_id, customer_email, exc,
            )
            integ.last_writeback_status = "retrying"
            integ.last_writeback_error = msg[:500]
            db.flush()
            raise task_self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.salesforce_writeback.push_health_to_salesforce",
)
def push_health_to_salesforce(self, org_id: int, customer_email: str) -> dict:
    """
    Push a customer's current health score to Salesforce as a Contact field.

    Idempotent (no-ops when unchanged / < 2pt from last-written), gated to
    opted-in orgs, and soft-pausing on permanent failures — never disables
    the integration (is_active is owned exclusively by the read-sync task).
    """
    return _push_health_to_salesforce_body(self, org_id, customer_email)
