"""
HubSpot CRM sync tasks (hubspot-sync aspect).

Tasks:
  sync_all_hubspot  — fan-out over orgs with active HubSpot integrations
  sync_hubspot_org  — per-org retryable sync (max_retries=3)

Core (Celery-free, tested directly):
  _sync_org         — pull contacts/companies/deals, match by email, upsert
  _pick_renewal_deal — select highest-amount open deal with a closedate
  _upsert_enrichment — Python-level upsert (no PG ON CONFLICT; SQLite-safe)
  _call_update_health — guarded health recompute (tolerates ImportError)
  _maybe_harvest      — additive, exception-isolated churn-suggestion harvest
                        (harvester-core aspect); default-deny, never touches
                        _sync_org's return dict (see churn_suggestion_harvester.py)

R3: access_token is never logged. Log messages use integration_id / org_id only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error).

Beat schedule: daily at 03:00 UTC — between integrations (02:00) and usage (04:00).
Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from celery import shared_task

from src.clients.hubspot import HubSpotClient, HubSpotTransientError
from src.database import get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local token decryption (mirrors webhook_delivery.py _decrypt)
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


def _pick_renewal_deal(deals: list[dict]) -> Optional[dict]:
    """
    Select the best renewal proxy deal.

    Criteria:
    - dealstage NOT IN (closedwon, closedlost)
    - closedate is not None / empty
    - highest amount (ties: first in iteration order)

    Returns the winning deal dict, or None if no qualifying deal.
    """
    CLOSED_STAGES = {"closedwon", "closedlost"}
    best = None
    best_amount = -1.0

    for deal in deals:
        props = deal.get("properties", {})
        stage = props.get("dealstage", "")
        if stage in CLOSED_STAGES:
            continue
        closedate = props.get("closedate")
        if not closedate:
            continue
        try:
            amount = float(props.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount > best_amount:
            best_amount = amount
            best = deal

    return best


def _upsert_enrichment(
    db,
    org_id: int,
    customer_email: str,
    fields: dict,
    now: datetime,
):
    """
    Insert or update a crm_enrichment row.

    Python-level upsert (no ON CONFLICT) so SQLite tests and PostgreSQL
    production both work. Mirrors _upsert_rollup in usage_metrics.py.
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

    # Always update all fields
    row.company_name = fields.get("company_name")
    row.lifecycle_stage = fields.get("lifecycle_stage")
    row.arr = fields.get("arr")
    row.renewal_date = fields.get("renewal_date")
    row.deal_name = fields.get("deal_name")
    row.deal_stage = fields.get("deal_stage")
    row.deal_amount = fields.get("deal_amount")
    row.hubspot_contact_id = fields.get("hubspot_contact_id")
    row.hubspot_company_id = fields.get("hubspot_company_id")
    row.hubspot_deal_id = fields.get("hubspot_deal_id")
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

    Verbatim copy from usage_metrics.py:135-153.
    """
    try:
        from src.services.health_score_service import update_customer_health
        update_customer_health(org_id, customer_email, db)
    except ImportError:
        logger.warning(
            "health_score_service not available; skipping health recompute "
            "for org=%s email=%s", org_id, customer_email,
        )


def _maybe_harvest(
    org_id: int,
    db,
    client: HubSpotClient,
    company_ids: dict,
    known_emails: set,
) -> None:
    """
    Best-effort churn-suggestion harvest, run after the enrichment loop.

    Default-deny: skipped unless the org's HubSpotIntegration has
    churn_labels_enabled=True AND a non-empty renewal_pipeline_ids config AND
    at least one matched company. Exception-isolated (R4) — any failure here,
    including one raised by the harvest itself, is caught and logged, never
    propagated, so this can never break the shipped enrichment loop above.
    Harvest stats go to a log line only; _sync_org's return dict is never
    touched (AC 7 holds in both toggle states).
    """
    try:
        from src.models import HubSpotIntegration
        from src.services.churn_suggestion_harvester import harvest_org_suggestions

        integ = (
            db.query(HubSpotIntegration)
            .filter(HubSpotIntegration.organization_id == org_id)
            .first()
        )
        if not integ or not integ.churn_labels_enabled:
            return

        config = integ.churn_label_config or {}
        renewal_set = frozenset(config.get("renewal_pipeline_ids") or [])
        if not renewal_set or not company_ids:
            return

        result = harvest_org_suggestions(
            org_id, db, client,
            provider="hubspot",
            renewal_set=renewal_set,
            known_emails=known_emails,
            company_ids=company_ids,
        )
        logger.info(
            "hubspot_sync: churn harvest org=%s status=%s scanned=%s suggested=%s "
            "skipped_existing=%s denied=%s dropped_by_cap=%s",
            org_id,
            result.get("status"),
            result.get("scanned"),
            result.get("suggested"),
            result.get("skipped_existing"),
            result.get("denied"),
            result.get("dropped_by_cap"),
        )
    except Exception:
        logger.exception(
            "hubspot_sync: churn suggestion harvest failed for org=%s", org_id,
        )


# ---------------------------------------------------------------------------
# Core sync logic (Celery-free — tested directly)
# ---------------------------------------------------------------------------


def _sync_org(org_id: int, db, client: HubSpotClient) -> dict:
    """
    Pull all HubSpot contacts for an org, match by email against CustomerHealth,
    upsert CrmEnrichment rows, and trigger health recompute for matches.

    Parameters
    ----------
    org_id  : organization ID being synced
    db      : SQLAlchemy session (caller manages transaction)
    client  : HubSpotClient instance (caller manages lifecycle)

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
    contacts_matched = 0
    now = datetime.utcnow()

    # harvester-core aspect: email -> HubSpot company id, for a best-effort
    # churn-suggestion harvest after this loop (additive; never touches the
    # loop's own enrichment behavior).
    company_ids: dict[str, str] = {}

    for contact in contacts:
        props = contact.get("properties", {})
        raw_email = props.get("email") or ""
        email_lower = raw_email.lower()

        if email_lower not in known_emails:
            continue

        contacts_matched += 1
        company_id = props.get("associatedcompanyid")
        if company_id:
            company_ids[email_lower] = company_id

        # Fetch company info
        company_data = None
        if company_id:
            company_data = client.get_company(company_id)

        company_name = None
        arr = None
        if company_data:
            company_name = company_data.get("name")
            raw_arr = company_data.get("annualrevenue")
            if raw_arr is not None:
                try:
                    arr = float(raw_arr)
                except (TypeError, ValueError):
                    arr = None

        # Fetch open deals for this company
        deals: list[dict] = []
        if company_id:
            deals = client.get_open_deals_for_company(company_id)

        renewal_deal = _pick_renewal_deal(deals)

        renewal_date = None
        deal_name = None
        deal_stage = None
        deal_amount = None
        hubspot_deal_id = None

        if renewal_deal:
            rdeal_props = renewal_deal.get("properties", {})
            closedate_str = rdeal_props.get("closedate")
            if closedate_str:
                # Parse ISO-8601 with or without timezone suffix
                try:
                    renewal_date = datetime.fromisoformat(
                        closedate_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    renewal_date = None
            deal_name = rdeal_props.get("dealname")
            deal_stage = rdeal_props.get("dealstage")
            try:
                deal_amount = float(rdeal_props.get("amount") or 0)
            except (TypeError, ValueError):
                deal_amount = None
            hubspot_deal_id = renewal_deal.get("id")

        fields = {
            "company_name": company_name,
            "lifecycle_stage": props.get("lifecyclestage"),
            "arr": arr,
            "renewal_date": renewal_date,
            "deal_name": deal_name,
            "deal_stage": deal_stage,
            "deal_amount": deal_amount,
            "hubspot_contact_id": contact.get("id"),
            "hubspot_company_id": company_id,
            "hubspot_deal_id": hubspot_deal_id,
        }

        _upsert_enrichment(db, org_id, email_lower, fields, now)
        _call_update_health(org_id, email_lower, db)

    _maybe_harvest(org_id, db, client, company_ids, known_emails)

    return {
        "contacts_synced": contacts_synced,
        "contacts_matched": contacts_matched,
        "unmatched": contacts_synced - contacts_matched,
    }


# ---------------------------------------------------------------------------
# Task implementation body (extracted so it can be called directly in tests)
# ---------------------------------------------------------------------------


def _sync_hubspot_org_body(task_self, integration_id: int) -> dict:
    """
    Inner logic of sync_hubspot_org. Extracted as a plain function so
    hardening tests can call it directly without Celery machinery.
    """
    from src.models import HubSpotIntegration

    with get_db_session() as db:
        integ = (
            db.query(HubSpotIntegration)
            .filter(HubSpotIntegration.id == integration_id)
            .first()
        )
        if not integ:
            return {"status": "not_found", "integration_id": integration_id}
        if not integ.is_active:
            return {"status": "inactive", "integration_id": integration_id}

        # R6: missing LLM_ENCRYPTION_KEY → non-transient config error; do not retry
        try:
            token = _decrypt(integ.access_token)
        except ValueError:
            logger.error(
                "hubspot_sync: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt token; skipping (integration_id=%s)",
                integ.organization_id,
                integration_id,
            )
            integ.last_sync_status = "error"
            integ.last_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        try:
            arr_prop = integ.arr_property_name or "annualrevenue"
            with HubSpotClient(token, arr_property_name=arr_prop) as client:
                result = _sync_org(integ.organization_id, db, client)

            integ.last_synced_at = datetime.utcnow()
            integ.last_sync_status = "success"
            integ.last_error = None
            integ.contacts_synced = result["contacts_synced"]
            integ.contacts_matched = result["contacts_matched"]
            db.flush()
            return {"status": "success", **result}

        except HubSpotTransientError as exc:
            logger.warning(
                "hubspot_sync: transient error for org=%s (integration_id=%s): %s",
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
                "hubspot_sync: unhandled error for org=%s (integration_id=%s): %s",
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


@shared_task(name="src.tasks.hubspot_sync.sync_all_hubspot")
def sync_all_hubspot() -> dict:
    """
    Fan-out: scan all active HubSpot integrations and enqueue per-org sync.

    Per-org try/except ensures one failure never aborts the batch.
    """
    from src.models import HubSpotIntegration

    with get_db_session() as db:
        integrations = (
            db.query(HubSpotIntegration)
            .filter(HubSpotIntegration.is_active.is_(True))
            .all()
        )
        if not integrations:
            return {"status": "no_integrations", "queued": 0}

        queued = 0
        for integ in integrations:
            try:
                sync_hubspot_org.delay(integ.id)
                queued += 1
            except Exception as exc:
                logger.error(
                    "sync_all_hubspot: failed to enqueue org=%s (integration_id=%s): %s",
                    integ.organization_id,
                    integ.id,
                    exc,
                )

        return {"status": "queued", "queued": queued}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.hubspot_sync.sync_hubspot_org",
)
def sync_hubspot_org(self, integration_id: int) -> dict:
    """
    Per-org HubSpot sync. Retries on HubSpotTransientError (max 3×).
    R6: missing LLM_ENCRYPTION_KEY returns error dict without retrying.
    """
    return _sync_hubspot_org_body(self, integration_id)
