"""
Cohort resolution — segment-actions / bulk-actions-api.

Resolves a `Cohort` (explicit email list OR filter) into the matching
`CustomerHealth` rows for the caller's organization. Shared by CSV export,
bulk tag, bulk assign-owner (this aspect), and by `playbook-cohort-run`
(a later aspect).
"""
from typing import List, Tuple

from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.schemas.cohort import Cohort


def resolve_cohort(
    db: Session, org: Organization, cohort: Cohort
) -> Tuple[List[CustomerHealth], int]:
    """Resolve a `Cohort` into `(matched_rows, skipped_count)`, org-scoped.

    - `cohort.emails`: each email is normalized (`.strip().lower()`) and
      deduplicated, then matched against `CustomerHealth.customer_email` for
      this org only. Unknown emails and emails belonging to another org are
      skipped (not errors) and counted in `skipped_count`.
    - `cohort.filter`: delegates to `_apply_customer_filters` (the exact
      filter logic `list_customers` uses) on an org-scoped base query, so
      results never drift from `GET /api/v1/customers/`. `skipped_count` is
      always 0 for the filter path (there is no notion of an "unknown" row).
    """
    if cohort.emails is not None:
        normalized = [e.strip().lower() for e in cohort.emails]
        unique_emails = list(dict.fromkeys(normalized))

        if not unique_emails:
            return [], 0

        rows = (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.organization_id == org.id,
                CustomerHealth.customer_email.in_(unique_emails),
            )
            .all()
        )
        matched_emails = {r.customer_email for r in rows}
        skipped = len(unique_emails) - len(matched_emails)
        return rows, skipped

    # Deferred import: avoids a circular import between
    # src.api.routes.customers <-> src.services.cohort_service, since
    # customers.py will import resolve_cohort for /export and /bulk/*.
    from src.api.routes.customers import _apply_customer_filters

    query = _apply_customer_filters(
        db.query(CustomerHealth),
        org,
        segment=cohort.filter.segment,
        risk_level=cohort.filter.risk_level,
        search=cohort.filter.search,
        include_archived=cohort.filter.include_archived,
    )
    rows = query.all()
    return rows, 0


def count_cohort(db: Session, org: Organization, cohort: Cohort) -> int:
    """Cheap count of a resolved cohort (matched rows only, not skipped).

    Uses `SELECT count(*)` rather than materializing rows.
    """
    if cohort.emails is not None:
        normalized = [e.strip().lower() for e in cohort.emails]
        unique_emails = list(dict.fromkeys(normalized))
        if not unique_emails:
            return 0
        return (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.organization_id == org.id,
                CustomerHealth.customer_email.in_(unique_emails),
            )
            .count()
        )

    from src.api.routes.customers import _apply_customer_filters

    query = _apply_customer_filters(
        db.query(CustomerHealth),
        org,
        segment=cohort.filter.segment,
        risk_level=cohort.filter.risk_level,
        search=cohort.filter.search,
        include_archived=cohort.filter.include_archived,
    )
    return query.count()
