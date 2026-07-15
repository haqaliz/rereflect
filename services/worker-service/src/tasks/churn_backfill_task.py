"""
Historical CRM churn-suggestion backfill Celery task (historical-backfill
aspect).

Task:
  backfill_churn_suggestions(integration_id, months, provider) — a DISTINCT,
  cancellable task. Deliberately NOT part of sync_hubspot_org (03:15 UTC) /
  sync_salesforce_org (03:45 UTC): a multi-year page-through must never
  stall the daily enrichment beat. Registered in celery_app.py's include
  list ONLY — no beat_schedule entry (AC-1).

Core (Celery-free, tested directly):
  _backfill_body — the task's full logic, minus Celery/session plumbing.
  Takes `db` and an injectable `client_factory` directly (house rule:
  "Celery-free body with an injectable client"), so it's testable with a
  real SQLite session and a hand-written Fake client — no get_db_session
  patching, no mocking library.

R6: missing LLM_ENCRYPTION_KEY returns {"status": "error",
    "reason": "missing_encryption_key"} and does NOT retry (non-transient
    config error) — mirrors hubspot_sync.py / salesforce_sync.py.
R3: access_token / refresh_token are never logged.

Cancellation (AC-8): the DB `backfill_status` column is the mechanism —
Celery `revoke` cannot interrupt a running body. `should_abort` re-reads the
integration row before each fetch unit (company/account); a concurrent
PATCH .../backfill/cancel setting `backfill_status="cancelling"` is picked
up at the next unit boundary, and the run returns "cancelled" with whatever
partial progress was already committed (resumable — re-running completes
the rest via the DB UNIQUE constraint's idempotency).

Never writes CustomerChurnEvent — suggestions only (churn_backfill.run_backfill
never does; this task doesn't either).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from celery import shared_task

from src.clients.hubspot import HubSpotTransientError
from src.clients.salesforce import SalesforceTransientError
from src.database import get_db_session
from src.services.churn_backfill import run_backfill

logger = logging.getLogger(__name__)

_RENEWAL_KEY_BY_PROVIDER = {
    "hubspot": "renewal_pipeline_ids",
    "salesforce": "renewal_opportunity_types",
}
_TOKEN_FIELD_BY_PROVIDER = {
    "hubspot": "access_token",
    "salesforce": "refresh_token",
}
_TRANSIENT_ERROR_BY_PROVIDER = {
    "hubspot": HubSpotTransientError,
    "salesforce": SalesforceTransientError,
}


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


# ---------------------------------------------------------------------------
# Salesforce Connected App / OAuth configuration — mirrors salesforce_sync.py
# ---------------------------------------------------------------------------


def _client_id() -> str:
    return os.environ.get("SALESFORCE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.environ.get("SALESFORCE_CLIENT_SECRET", "")


def _login_base() -> str:
    return os.environ.get("SALESFORCE_LOGIN_BASE", "https://login.salesforce.com")


def _api_version() -> str:
    return os.environ.get("SALESFORCE_API_VERSION", "v60.0")


def _default_client_factory(provider: str, token: str, integ):
    """Construct the real, injected CRM client for `provider`. Overridable
    in tests via `_backfill_body(..., client_factory=...)` — never patched."""
    if provider == "hubspot":
        from src.clients.hubspot import HubSpotClient
        return HubSpotClient(
            token, arr_property_name=integ.arr_property_name or "annualrevenue"
        )
    if provider == "salesforce":
        from src.clients.salesforce import SalesforceClient
        return SalesforceClient(
            refresh_token=token,
            instance_url=integ.instance_url,
            client_id=_client_id(),
            client_secret=_client_secret(),
            login_base=_login_base(),
            api_version=_api_version(),
        )
    raise ValueError(f"unknown provider: {provider}")


def _build_known_emails_and_company_ids(
    db, org_id: int, contacts: list[dict], provider: str
) -> tuple[set, dict]:
    """
    Derive `known_emails` + `company_ids` from a fresh contact pull, exactly
    as _sync_org does in hubspot_sync.py / salesforce_sync.py (plan Decision
    #2 — an org-wide CRM query has no email/company link without this
    contact-association pass; there is no shorter path).
    """
    from src.models import CustomerHealth

    known_emails: set = {
        row.customer_email.lower()
        for row in (
            db.query(CustomerHealth)
            .filter(CustomerHealth.organization_id == org_id)
            .with_entities(CustomerHealth.customer_email)
            .all()
        )
    }

    company_ids: dict = {}

    if provider == "hubspot":
        for contact in contacts:
            props = contact.get("properties", {}) or {}
            email_lower = (props.get("email") or "").lower()
            if email_lower not in known_emails:
                continue
            company_id = props.get("associatedcompanyid")
            if company_id:
                company_ids[email_lower] = company_id

    elif provider == "salesforce":
        # Dedupe matched contacts by email, lowest Id wins — mirrors
        # salesforce_sync.py's deterministic tie-break.
        matched_by_email: dict = {}
        for contact in contacts:
            email_lower = (contact.get("Email") or "").lower()
            if email_lower not in known_emails:
                continue
            current = matched_by_email.get(email_lower)
            if current is None or str(contact.get("Id")) < str(current.get("Id")):
                matched_by_email[email_lower] = contact
        for email_lower, contact in matched_by_email.items():
            account_id = contact.get("AccountId")
            if account_id:
                company_ids[email_lower] = account_id

    return known_emails, company_ids


def _backfill_body(
    task_self,
    db,
    integration_id: int,
    months: int,
    provider: str,
    *,
    client_factory=_default_client_factory,
    _decrypt_fn=_decrypt,
) -> dict:
    """
    Celery-free task body. `db` and `client_factory` are injectable so this
    is directly testable with a real SQLite session and a hand-written Fake
    client — no get_db_session patching, no Celery machinery.
    """
    from src.models import HubSpotIntegration, SalesforceIntegration

    if provider == "hubspot":
        model = HubSpotIntegration
    elif provider == "salesforce":
        model = SalesforceIntegration
    else:
        return {"status": "error", "reason": "unknown_provider"}

    integ = db.query(model).filter(model.id == integration_id).first()
    if not integ:
        return {"status": "not_found", "integration_id": integration_id}
    if not integ.is_active:
        return {"status": "inactive", "integration_id": integration_id}

    # Default-deny re-check (spec §7 step 3): config may have changed
    # between the trigger endpoint's check and this task actually running.
    config = integ.churn_label_config or {}
    renewal_key = _RENEWAL_KEY_BY_PROVIDER[provider]
    renewal_set = frozenset(config.get(renewal_key) or [])
    if not integ.churn_labels_enabled or not renewal_set:
        integ.backfill_status = "failed"
        integ.backfill_error = "churn_labels_disabled_or_unconfigured"
        integ.backfill_last_run_at = datetime.utcnow()
        db.flush()
        db.commit()
        return {"status": "error", "reason": "churn_labels_disabled_or_unconfigured"}

    # R6: missing LLM_ENCRYPTION_KEY -> non-transient config error; no retry.
    token_field = _TOKEN_FIELD_BY_PROVIDER[provider]
    try:
        token = _decrypt_fn(getattr(integ, token_field))
    except ValueError:
        logger.error(
            "churn_backfill: LLM_ENCRYPTION_KEY unset for org=%s "
            "— cannot decrypt token; skipping (integration_id=%s)",
            integ.organization_id,
            integration_id,
        )
        integ.backfill_status = "failed"
        integ.backfill_error = "missing_encryption_key"
        integ.backfill_last_run_at = datetime.utcnow()
        db.flush()
        db.commit()
        return {"status": "error", "reason": "missing_encryption_key"}

    integ.backfill_status = "running"
    integ.backfill_error = None
    db.flush()
    db.commit()

    def _should_abort() -> bool:
        db.commit()
        db.refresh(integ)
        return integ.backfill_status == "cancelling"

    def _on_progress(counters: dict) -> None:
        integ.backfill_progress = dict(counters)
        integ.backfill_last_run_at = datetime.utcnow()
        db.flush()
        db.commit()

    transient_error_cls = _TRANSIENT_ERROR_BY_PROVIDER[provider]

    try:
        client = client_factory(provider, token, integ)
        with client:
            contacts = client.list_contacts()
            known_emails, company_ids = _build_known_emails_and_company_ids(
                db, integ.organization_id, contacts, provider
            )
            result = run_backfill(
                integ.organization_id,
                db,
                client,
                provider=provider,
                renewal_set=renewal_set,
                known_emails=known_emails,
                company_ids=company_ids,
                months=months,
                should_abort=_should_abort,
                on_progress=_on_progress,
            )

        # Keep "since" in the persisted progress (not just the log line) —
        # house rule: no silent caps, the covered window must be SURFACED
        # to the operator (spec §6), not just logged.
        integ.backfill_progress = {k: v for k, v in result.items() if k != "status"}
        integ.backfill_last_run_at = datetime.utcnow()
        integ.backfill_status = (
            "cancelled" if result["status"] == "cancelled" else "completed"
        )
        integ.backfill_error = None
        db.flush()
        db.commit()

        logger.info(
            "churn_backfill: %s org=%s provider=%s scanned=%s suggested=%s "
            "skipped_existing=%s denied=%s dropped_by_cap=%s",
            result["status"], integ.organization_id, provider,
            result.get("scanned"), result.get("suggested"),
            result.get("skipped_existing"), result.get("denied"),
            result.get("dropped_by_cap"),
        )
        return result

    except transient_error_cls as exc:
        logger.warning(
            "churn_backfill: transient error for org=%s (integration_id=%s): %s",
            integ.organization_id, integration_id, exc,
        )
        integ.backfill_status = "running"
        integ.backfill_error = str(exc)[:500]
        db.flush()
        db.commit()
        raise task_self.retry(exc=exc)

    except Exception as exc:
        logger.error(
            "churn_backfill: unhandled error for org=%s (integration_id=%s): %s",
            integ.organization_id, integration_id, exc, exc_info=True,
        )
        integ.backfill_status = "failed"
        integ.backfill_error = str(exc)[:500]
        db.flush()
        db.commit()
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.churn_backfill_task.backfill_churn_suggestions",
)
def backfill_churn_suggestions(self, integration_id: int, months: int, provider: str) -> dict:
    """
    Operator-triggered historical churn-suggestion backfill. Distinct from
    the daily sync tasks (AC-1) — no beat entry; dispatched only via the
    trigger endpoint's send_task.
    """
    with get_db_session() as db:
        return _backfill_body(self, db, integration_id, months, provider)
