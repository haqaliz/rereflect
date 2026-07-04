"""
Salesforce CRM sync tasks (salesforce-sync aspect).

Tasks:
  sync_all_salesforce  — fan-out over orgs with active Salesforce integrations
  sync_salesforce_org   — per-org retryable sync (max_retries=3)

Core (Celery-free, tested directly):
  _sync_org                  — pull contacts/accounts/opportunities, match by
                                email, upsert CrmEnrichment(provider='salesforce')
  _pick_renewal_opportunity  — select highest-amount open opportunity with a
                                CloseDate
  _upsert_enrichment         — Python-level upsert (no PG ON CONFLICT; SQLite-safe)
  _call_update_health        — guarded health recompute (tolerates ImportError)

R3: the access_token/refresh_token are never logged. Log messages use
    integration_id / org_id only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error).

invalid_grant on token refresh marks the integration disconnected
(is_active=False + last_error) and does NOT retry — the stored refresh
token is no longer usable and retrying would just repeat the same failure.

Beat schedule: daily at 03:45 UTC — avoids 03:00 (global calibration) and
03:15 (hubspot sync).
Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from celery import shared_task

from src.clients.salesforce import (
    SalesforceAuthError,
    SalesforceClient,
    SalesforceTransientError,
)
from src.database import get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Salesforce Connected App / OAuth configuration — read at call time (not
# baked in at import) so tests can override via patch.dict(os.environ, ...).
# Mirrors src/api/routes/salesforce_integration.py on the backend.
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
# Local token decryption (mirrors hubspot_sync.py _decrypt)
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
# Pure helpers
# ---------------------------------------------------------------------------


def _pick_renewal_opportunity(opportunities: list[dict]) -> Optional[dict]:
    """
    Select the best renewal proxy Opportunity.

    Criteria:
    - IsClosed is falsy (query already filters IsClosed=false, but this is
      defensive in case the client passes unfiltered data)
    - CloseDate is not None / empty
    - highest Amount (ties: first in iteration order)

    Returns the winning opportunity dict, or None if no qualifying opportunity.
    """
    best = None
    best_amount = -1.0

    for opp in opportunities:
        if opp.get("IsClosed"):
            continue
        close_date = opp.get("CloseDate")
        if not close_date:
            continue
        try:
            amount = float(opp.get("Amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount > best_amount:
            best_amount = amount
            best = opp

    return best


def _upsert_enrichment(
    db,
    org_id: int,
    customer_email: str,
    fields: dict,
    now: datetime,
    provider: str = "salesforce",
):
    """
    Insert or update a crm_enrichment row.

    Python-level upsert (no ON CONFLICT) so SQLite tests and PostgreSQL
    production both work. Mirrors _upsert_enrichment in hubspot_sync.py.
    """
    from src.models import CrmEnrichment

    row = (
        db.query(CrmEnrichment)
        .filter_by(organization_id=org_id, customer_email=customer_email)
        .first()
    )
    if row is None:
        row = CrmEnrichment(
            organization_id=org_id,
            customer_email=customer_email,
            created_at=now,
        )
        db.add(row)

    row.provider = provider
    row.company_name = fields.get("company_name")
    row.lifecycle_stage = fields.get("lifecycle_stage")
    row.arr = fields.get("arr")
    row.renewal_date = fields.get("renewal_date")
    row.deal_name = fields.get("deal_name")
    row.deal_stage = fields.get("deal_stage")
    row.deal_amount = fields.get("deal_amount")
    # M5a (push-task-trigger): persist the matched Salesforce Contact Id so
    # the writeback push task has a target. Deterministic dup-email
    # resolution (lowest Id) happens in _sync_org before this is called.
    if "salesforce_contact_id" in fields:
        row.salesforce_contact_id = fields.get("salesforce_contact_id")
    row.last_synced_at = now
    row.updated_at = now

    db.flush()
    return row


def _call_update_health(org_id: int, customer_email: str, db) -> None:
    """
    Trigger a health-score recompute for the customer.

    ImportError is silently tolerated: during a partial-deploy the
    health_score_service module may not yet be present in the worker image.
    All other errors propagate so the Celery task can decide on retry.

    Verbatim copy from hubspot_sync.py:136-153.
    """
    try:
        from src.services.health_score_service import update_customer_health
        update_customer_health(org_id, customer_email, db)
    except ImportError:
        logger.warning(
            "health_score_service not available; skipping health recompute "
            "for org=%s email=%s", org_id, customer_email,
        )


# ---------------------------------------------------------------------------
# Core sync logic (Celery-free — tested directly)
# ---------------------------------------------------------------------------


def _sync_org(org_id: int, db, client: SalesforceClient) -> dict:
    """
    Pull all Salesforce contacts for an org, match by email against
    CustomerHealth, resolve each match's Account (direct AccountId FK — no
    associations round-trip) + best open renewal Opportunity, upsert
    CrmEnrichment rows (provider='salesforce'), and trigger health recompute
    for matches.

    Parameters
    ----------
    org_id  : organization ID being synced
    db      : SQLAlchemy session (caller manages transaction)
    client  : SalesforceClient instance (caller manages lifecycle)

    Returns
    -------
    dict with keys: contacts_synced, contacts_matched, unmatched
    """
    from src.models import CustomerHealth

    # Build set of lowercase known customer emails for this org
    known_emails: set[str] = {
        row.customer_email.lower()
        for row in (
            db.query(CustomerHealth)
            .filter(CustomerHealth.organization_id == org_id)
            .with_entities(CustomerHealth.customer_email)
            .all()
        )
    }

    contacts = client.list_contacts()
    contacts_synced = len(contacts)
    now = datetime.utcnow()

    # M5a (push-task-trigger): dedupe matched contacts by email BEFORE doing
    # any enrichment work. When two Contacts share the same customer email,
    # pick deterministically — the lowest Id — so the sync is stable across
    # runs regardless of the API's return order.
    matched_by_email: dict[str, dict] = {}
    for contact in contacts:
        raw_email = contact.get("Email") or ""
        email_lower = raw_email.lower()
        if email_lower not in known_emails:
            continue
        current = matched_by_email.get(email_lower)
        if current is None or str(contact.get("Id")) < str(current.get("Id")):
            matched_by_email[email_lower] = contact

    contacts_matched = len(matched_by_email)

    # M2: memoize Account + open-Opportunities fetches per sync run so
    # multiple matched contacts sharing one AccountId don't each re-fetch
    # the same Account/Opportunities data from Salesforce (N+1).
    account_cache: dict[str, Optional[dict]] = {}
    opportunities_cache: dict[str, list[dict]] = {}

    for email_lower, contact in matched_by_email.items():
        account_id = contact.get("AccountId")

        # Resolve Account via the direct Contact.AccountId FK.
        account_data = None
        if account_id:
            if account_id not in account_cache:
                account_cache[account_id] = client.get_account(account_id)
            account_data = account_cache[account_id]

        company_name = None
        arr = None
        lifecycle_stage = None
        if account_data:
            company_name = account_data.get("Name")
            raw_arr = account_data.get("AnnualRevenue")
            if raw_arr is not None:
                try:
                    arr = float(raw_arr)
                except (TypeError, ValueError):
                    arr = None
            lifecycle_stage = account_data.get("Type")

        # Fetch open opportunities for this account.
        opportunities: list[dict] = []
        if account_id:
            if account_id not in opportunities_cache:
                opportunities_cache[account_id] = client.get_open_opportunities(account_id)
            opportunities = opportunities_cache[account_id]

        renewal_opp = _pick_renewal_opportunity(opportunities)

        renewal_date = None
        deal_name = None
        deal_stage = None
        deal_amount = None

        if renewal_opp:
            close_date_str = renewal_opp.get("CloseDate")
            if close_date_str:
                # Parse ISO-8601 date/datetime with or without timezone suffix
                try:
                    renewal_date = datetime.fromisoformat(
                        str(close_date_str).replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    renewal_date = None
            deal_name = renewal_opp.get("Name")
            deal_stage = renewal_opp.get("StageName")
            try:
                deal_amount = float(renewal_opp.get("Amount") or 0)
            except (TypeError, ValueError):
                deal_amount = None

        fields = {
            "company_name": company_name,
            "lifecycle_stage": lifecycle_stage,
            "arr": arr,
            "renewal_date": renewal_date,
            "deal_name": deal_name,
            "deal_stage": deal_stage,
            "deal_amount": deal_amount,
            "salesforce_contact_id": contact.get("Id"),
        }

        _upsert_enrichment(db, org_id, email_lower, fields, now, provider="salesforce")
        _call_update_health(org_id, email_lower, db)

    return {
        "contacts_synced": contacts_synced,
        "contacts_matched": contacts_matched,
        "unmatched": contacts_synced - contacts_matched,
    }


# ---------------------------------------------------------------------------
# Task implementation body (extracted so it can be called directly in tests)
# ---------------------------------------------------------------------------


def _sync_salesforce_org_body(task_self, integration_id: int) -> dict:
    """
    Inner logic of sync_salesforce_org. Extracted as a plain function so
    hardening tests can call it directly without Celery machinery.
    """
    from src.models import SalesforceIntegration

    with get_db_session() as db:
        integ = (
            db.query(SalesforceIntegration)
            .filter(SalesforceIntegration.id == integration_id)
            .first()
        )
        if not integ:
            return {"status": "not_found", "integration_id": integration_id}
        if not integ.is_active:
            return {"status": "inactive", "integration_id": integration_id}

        # R6: missing LLM_ENCRYPTION_KEY → non-transient config error; do not retry
        try:
            refresh_token = _decrypt(integ.refresh_token)
        except ValueError:
            logger.error(
                "salesforce_sync: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt refresh_token; skipping (integration_id=%s)",
                integ.organization_id,
                integration_id,
            )
            integ.last_sync_status = "error"
            integ.last_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        try:
            with SalesforceClient(
                refresh_token=refresh_token,
                instance_url=integ.instance_url,
                client_id=_client_id(),
                client_secret=_client_secret(),
                login_base=_login_base(),
                api_version=_api_version(),
            ) as client:
                result = _sync_org(integ.organization_id, db, client)

            integ.last_synced_at = datetime.utcnow()
            integ.last_sync_status = "success"
            integ.last_error = None
            integ.contacts_synced = result["contacts_synced"]
            integ.contacts_matched = result["contacts_matched"]
            db.flush()
            return {"status": "success", **result}

        except SalesforceAuthError as exc:
            # invalid_grant (or any other non-transient auth failure) means
            # the stored refresh token is no longer usable — disconnect the
            # integration rather than retrying the same failure forever.
            logger.error(
                "salesforce_sync: auth error for org=%s (integration_id=%s): %s "
                "— disconnecting integration",
                integ.organization_id,
                integration_id,
                exc,
            )
            integ.is_active = False
            integ.last_sync_status = "error"
            integ.last_error = str(exc)[:500]
            db.flush()
            return {"status": "error", "reason": "invalid_grant"}

        except SalesforceTransientError as exc:
            logger.warning(
                "salesforce_sync: transient error for org=%s (integration_id=%s): %s",
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
                "salesforce_sync: unhandled error for org=%s (integration_id=%s): %s",
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


@shared_task(name="src.tasks.salesforce_sync.sync_all_salesforce")
def sync_all_salesforce() -> dict:
    """
    Fan-out: scan all active Salesforce integrations and enqueue per-org sync.

    Per-org try/except ensures one failure never aborts the batch.
    """
    from src.models import SalesforceIntegration

    with get_db_session() as db:
        integrations = (
            db.query(SalesforceIntegration)
            .filter(SalesforceIntegration.is_active.is_(True))
            .all()
        )
        if not integrations:
            return {"status": "no_integrations", "queued": 0}

        queued = 0
        for integ in integrations:
            try:
                sync_salesforce_org.delay(integ.id)
                queued += 1
            except Exception as exc:
                logger.error(
                    "sync_all_salesforce: failed to enqueue org=%s (integration_id=%s): %s",
                    integ.organization_id,
                    integ.id,
                    exc,
                )

        return {"status": "queued", "queued": queued}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.salesforce_sync.sync_salesforce_org",
)
def sync_salesforce_org(self, integration_id: int) -> dict:
    """
    Per-org Salesforce sync. Retries on SalesforceTransientError (max 3x).
    R6: missing LLM_ENCRYPTION_KEY returns error dict without retrying.
    invalid_grant marks the integration disconnected without retrying.
    """
    return _sync_salesforce_org_body(self, integration_id)
