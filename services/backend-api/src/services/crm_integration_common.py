"""
Shared CRM integration helpers: one-CRM-per-org guard + provider purge.

Used by both hubspot_integration.py and salesforce_integration.py so the
one-CRM-per-org invariant (PRD locked decision D2/D3) holds symmetrically
regardless of which CRM connects first, and so disconnecting a CRM never
leaves stale enrichment silently influencing health scores (locked
decision 7).
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def another_crm_active(db: Session, org_id: int, exclude_provider: str) -> Optional[str]:
    """
    Return the name of any OTHER active CRM integration for this org, or None.

    Checks hubspot_integrations and salesforce_integrations for an is_active
    row whose provider isn't `exclude_provider`. Called symmetrically from
    both hubspot_integration.py's connect and salesforce_integration.py's
    connect-url/callback so the one-CRM-per-org collision cannot be created
    from either direction.

    M1 (accepted for slice 1, DOCUMENT ONLY): this guard is application-level
    only — a plain SELECT with no cross-table DB constraint — so two
    near-simultaneous connect attempts for DIFFERENT CRMs on the same org
    (e.g. HubSpot and Salesforce both racing through connect within the same
    read window) could both pass this check and both write an active
    integration row. This is a genuine TOCTOU (time-of-check-to-time-of-use)
    window. It was deliberately NOT closed with a DB-level lock for slice 1:
    the probability is low (requires two concurrent connect requests for two
    different providers), and the outcome is non-corrupting — the
    crm_enrichment (org_id, customer_email) uniqueness constraint still
    holds, and whichever CRM syncs last simply wins the `provider` tag on
    enrichment rows. Adding a lock now would also complicate the SQLite-based
    test environment for a low-value race. v2 options if this needs
    tightening: (a) an advisory lock (e.g. Postgres pg_advisory_xact_lock
    keyed on org_id) around the check-then-write in both connect paths, or
    (b) a periodic reconciliation job that detects and resolves the rare
    case where two providers ended up active for the same org.
    """
    from src.models.hubspot_integration import HubSpotIntegration
    from src.models.salesforce_integration import SalesforceIntegration

    if exclude_provider != "hubspot":
        hs = (
            db.query(HubSpotIntegration)
            .filter(
                HubSpotIntegration.organization_id == org_id,
                HubSpotIntegration.is_active.is_(True),
            )
            .first()
        )
        if hs:
            return "hubspot"

    if exclude_provider != "salesforce":
        sf = (
            db.query(SalesforceIntegration)
            .filter(
                SalesforceIntegration.organization_id == org_id,
                SalesforceIntegration.is_active.is_(True),
            )
            .first()
        )
        if sf:
            return "salesforce"

    return None


def purge_crm_enrichment(db: Session, org_id: int, provider: str) -> int:
    """
    Delete all crm_enrichment rows for (org_id, provider) and recompute the
    affected customers' health scores, so a disconnected CRM stops
    influencing scores (locked decision 7).

    Returns the number of rows deleted. Health recompute is best-effort:
    a failure is logged and swallowed — a purge must never crash disconnect.
    """
    from src.models.crm_enrichment import CrmEnrichment

    rows = (
        db.query(CrmEnrichment)
        .filter(
            CrmEnrichment.organization_id == org_id,
            CrmEnrichment.provider == provider,
        )
        .all()
    )
    affected_emails = [row.customer_email for row in rows]
    count = len(rows)

    for row in rows:
        db.delete(row)
    db.commit()

    if affected_emails:
        from src.services.health_score_service import update_customer_health
        for email in affected_emails:
            try:
                update_customer_health(org_id, email, db)
            except Exception as exc:
                logger.warning(
                    "Health recompute after CRM purge failed for org %s / %s: %s",
                    org_id, email, exc,
                )

    return count
