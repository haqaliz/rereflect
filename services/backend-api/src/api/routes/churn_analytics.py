"""
Churn cohort analytics API endpoint (M4.1 Phase 4).

GET /api/v1/analytics/churn-cohorts?dimension=source|month|volume&range=30d|90d|all

Plan gate: Business+ (churn_cohorts feature).
SQLite-compatible for tests; PostgreSQL in production.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_feature
from src.database.session import get_db
from src.models.churn_event import CustomerChurnEvent
from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.schemas.churn_cohort import (
    CohortAnalyticsResponse,
    CohortBucket,
    CohortGridCell,
)

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["churn-analytics"],
    dependencies=[Depends(require_feature("churn_cohorts"))],
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cutoff_date(range_param: str) -> Optional[datetime]:
    """Return the earliest last_feedback_at allowed, or None for 'all'."""
    now = datetime.utcnow()
    if range_param == "30d":
        return now - timedelta(days=30)
    if range_param == "90d":
        return now - timedelta(days=90)
    return None  # "all" — no filter


def _volume_label(feedback_count: int) -> str:
    """Map feedback_count to a volume bucket label."""
    if feedback_count <= 3:
        return "Light (1-3)"
    if feedback_count <= 10:
        return "Regular (4-10)"
    return "Power (11+)"


def _iso_month(dt: datetime) -> str:
    """Format datetime as 'YYYY-MM'."""
    return dt.strftime("%Y-%m")


def _iso_week_label(dt: datetime) -> str:
    """Format datetime as 'Week N' (ISO week number)."""
    return f"Week {dt.isocalendar()[1]}"


def _time_bucket_for(churned_at: datetime, range_param: str) -> str:
    """Determine the grid time_bucket for a churn event timestamp."""
    if range_param == "all":
        return _iso_month(churned_at)
    return _iso_week_label(churned_at)


def _primary_source_map(
    org_id: int, emails: list[str], db: Session
) -> dict[str, str]:
    """
    Return {customer_email: primary_source} by computing the mode source
    across feedback_items per customer.  Done in Python for SQLite compatibility.
    """
    if not emails:
        return {}
    rows = (
        db.query(FeedbackItem.customer_email, FeedbackItem.source)
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.customer_email.in_(emails),
        )
        .all()
    )
    # Group source counts per customer
    source_counts: dict[str, Counter] = defaultdict(Counter)
    for email, source in rows:
        if source:
            source_counts[email][source] += 1

    result: dict[str, str] = {}
    for email in emails:
        counts = source_counts.get(email)
        if counts:
            result[email] = counts.most_common(1)[0][0]
        else:
            result[email] = "unknown"
    return result


def _first_feedback_map(
    org_id: int, emails: list[str], db: Session
) -> dict[str, datetime]:
    """Return {customer_email: earliest feedback created_at}."""
    if not emails:
        return {}
    rows = (
        db.query(FeedbackItem.customer_email, FeedbackItem.created_at)
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.customer_email.in_(emails),
        )
        .order_by(FeedbackItem.customer_email, FeedbackItem.created_at.asc())
        .all()
    )
    result: dict[str, datetime] = {}
    for email, created_at in rows:
        if email not in result:
            result[email] = created_at
    return result


def _compute_top_reasons(
    churned_emails: list[str], org_id: int, db: Session
) -> list[dict]:
    """Return top-3 reason codes for a set of churned customers."""
    if not churned_emails:
        return []
    rows = (
        db.query(CustomerChurnEvent.reason_code)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.customer_email.in_(churned_emails),
        )
        .all()
    )
    counts: Counter = Counter(r[0] for r in rows)
    return [
        {"code": code, "count": cnt}
        for code, cnt in counts.most_common(3)
    ]


# ---------------------------------------------------------------------------
# Per-dimension cohort query builders
# ---------------------------------------------------------------------------


def _query_source_cohorts(
    customers: list[CustomerHealth],
    churn_set: set[str],
    churn_events: list[CustomerChurnEvent],
    org_id: int,
    db: Session,
) -> list[CohortBucket]:
    """Group customers by their primary feedback source."""
    emails = [c.customer_email for c in customers]
    source_map = _primary_source_map(org_id, emails, db)

    # Group customers by cohort label
    cohort_customers: dict[str, list[CustomerHealth]] = defaultdict(list)
    for c in customers:
        label = source_map.get(c.customer_email, "unknown")
        cohort_customers[label].append(c)

    # Map email → all churn events for reason code lookup
    churn_email_to_events: dict[str, list[CustomerChurnEvent]] = defaultdict(list)
    for ev in churn_events:
        churn_email_to_events[ev.customer_email].append(ev)

    return _build_buckets(cohort_customers, churn_set, org_id, db)


def _query_month_cohorts(
    customers: list[CustomerHealth],
    churn_set: set[str],
    churn_events: list[CustomerChurnEvent],
    org_id: int,
    db: Session,
) -> list[CohortBucket]:
    """Group customers by acquisition month (earliest feedback_items.created_at)."""
    emails = [c.customer_email for c in customers]
    first_fb_map = _first_feedback_map(org_id, emails, db)

    cohort_customers: dict[str, list[CustomerHealth]] = defaultdict(list)
    for c in customers:
        first_at = first_fb_map.get(c.customer_email)
        label = _iso_month(first_at) if first_at else "unknown"
        cohort_customers[label].append(c)

    buckets = _build_buckets(cohort_customers, churn_set, org_id, db)
    # Sort descending by label (most recent first) and cap at 12 months
    buckets.sort(key=lambda b: b.label, reverse=True)
    return buckets[:12]


def _query_volume_cohorts(
    customers: list[CustomerHealth],
    churn_set: set[str],
    churn_events: list[CustomerChurnEvent],
    org_id: int,
    db: Session,
) -> list[CohortBucket]:
    """Group customers by feedback_count volume segment."""
    cohort_customers: dict[str, list[CustomerHealth]] = defaultdict(list)
    for c in customers:
        label = _volume_label(c.feedback_count or 0)
        cohort_customers[label].append(c)

    return _build_buckets(cohort_customers, churn_set, org_id, db)


def _build_buckets(
    cohort_customers: dict[str, list[CustomerHealth]],
    churn_set: set[str],
    org_id: int,
    db: Session,
) -> list[CohortBucket]:
    """Convert grouped customers into CohortBucket rows."""
    buckets: list[CohortBucket] = []
    for label, members in cohort_customers.items():
        total = len(members)
        churned_emails = [m.customer_email for m in members if m.customer_email in churn_set]
        churned = len(churned_emails)
        rate = churned / total if total > 0 else 0.0

        probs = [
            float(m.churn_probability)
            for m in members
            if m.churn_probability is not None
        ]
        avg_prob = sum(probs) / len(probs) if probs else None

        top_reasons = _compute_top_reasons(churned_emails, org_id, db)

        buckets.append(
            CohortBucket(
                label=label,
                total_customers=total,
                churned_customers=churned,
                churn_rate=rate,
                avg_probability=avg_prob,
                top_reason_codes=top_reasons,
            )
        )
    return buckets


def _build_grid(
    customers: list[CustomerHealth],
    churn_set: set[str],
    churn_events: list[CustomerChurnEvent],
    cohort_label_map: dict[str, str],   # email → cohort label
    range_param: str,
) -> list[CohortGridCell]:
    """
    Build 2-D grid: (cohort_label × time_bucket).

    For each churn event, look up which cohort the customer belongs to and
    which time_bucket the event falls in.  Accumulate churned counts and
    compute rates per cell.
    """
    # Cell: (cohort_label, time_bucket) → {churned, total}
    cell_churned: dict[tuple[str, str], int] = defaultdict(int)
    cell_total: dict[tuple[str, str], set] = defaultdict(set)

    for ev in churn_events:
        label = cohort_label_map.get(ev.customer_email)
        if label is None:
            continue
        tb = _time_bucket_for(ev.churned_at, range_param)
        cell_churned[(label, tb)] += 1

    # Use customer health to assign customers to time buckets (by last_feedback_at)
    for c in customers:
        label = cohort_label_map.get(c.customer_email)
        if label is None:
            continue
        # For grid denominator, use last_feedback_at as the time reference
        ref_dt = c.last_feedback_at or datetime.utcnow()
        tb = _time_bucket_for(ref_dt, range_param)
        cell_total[(label, tb)].add(c.customer_email)

    cells: list[CohortGridCell] = []
    all_keys = set(cell_churned.keys()) | set(cell_total.keys())
    for (label, tb) in all_keys:
        churned_cnt = cell_churned.get((label, tb), 0)
        total_cnt = len(cell_total.get((label, tb), set()))
        rate = churned_cnt / total_cnt if total_cnt > 0 else 0.0
        cells.append(
            CohortGridCell(
                cohort_label=label,
                time_bucket=tb,
                churn_rate=rate,
                churned_count=churned_cnt,
            )
        )
    return cells


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/churn-cohorts", response_model=CohortAnalyticsResponse)
def get_churn_cohorts(
    dimension: str = Query(..., pattern="^(source|month|volume)$"),
    range: str = Query(..., pattern="^(30d|90d|all)$"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> CohortAnalyticsResponse:
    """Return cohort churn analytics for the organization.

    Groups customers by the requested dimension and returns per-cohort metrics,
    a 2-D grid (cohort × time), and aggregate totals.
    """
    org_id: int = current_org.id
    cutoff = _cutoff_date(range)

    # --- Fetch customers in scope ---
    hs_query = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.is_archived == False,  # noqa: E712
    )
    if cutoff is not None:
        hs_query = hs_query.filter(CustomerHealth.last_feedback_at >= cutoff)

    customers: list[CustomerHealth] = hs_query.all()

    if not customers:
        return CohortAnalyticsResponse(
            dimension=dimension,
            range=range,
            cohorts=[],
            grid=[],
            overall_churn_rate=0.0,
            total_customers=0,
            total_churned=0,
        )

    customer_emails = [c.customer_email for c in customers]

    # --- Fetch ALL churn events for these customers (historical — no time filter) ---
    churn_events: list[CustomerChurnEvent] = (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.customer_email.in_(customer_emails),
        )
        .all()
    )

    # Set of emails that ever churned (recovered_at does NOT erase history)
    churn_set: set[str] = {ev.customer_email for ev in churn_events}

    # --- Build cohorts per dimension ---
    if dimension == "source":
        buckets = _query_source_cohorts(customers, churn_set, churn_events, org_id, db)
    elif dimension == "month":
        buckets = _query_month_cohorts(customers, churn_set, churn_events, org_id, db)
    else:  # volume
        buckets = _query_volume_cohorts(customers, churn_set, churn_events, org_id, db)

    # --- Build cohort label map for grid ---
    cohort_label_map: dict[str, str] = _build_cohort_label_map(
        dimension, customers, customer_emails, org_id, db
    )

    grid = _build_grid(customers, churn_set, churn_events, cohort_label_map, range)

    # --- Aggregate totals ---
    total_customers = len(customers)
    total_churned = len(churn_set & set(customer_emails))
    overall_rate = total_churned / total_customers if total_customers > 0 else 0.0

    return CohortAnalyticsResponse(
        dimension=dimension,
        range=range,
        cohorts=buckets,
        grid=grid,
        overall_churn_rate=overall_rate,
        total_customers=total_customers,
        total_churned=total_churned,
    )


def _build_cohort_label_map(
    dimension: str,
    customers: list[CustomerHealth],
    emails: list[str],
    org_id: int,
    db: Session,
) -> dict[str, str]:
    """Return {customer_email: cohort_label} for the given dimension."""
    if dimension == "source":
        return _primary_source_map(org_id, emails, db)
    if dimension == "month":
        first_fb_map = _first_feedback_map(org_id, emails, db)
        return {
            c.customer_email: (
                _iso_month(first_fb_map[c.customer_email])
                if c.customer_email in first_fb_map
                else "unknown"
            )
            for c in customers
        }
    # volume
    return {c.customer_email: _volume_label(c.feedback_count or 0) for c in customers}
