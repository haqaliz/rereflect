"""
Customer Timeline Service — merges multiple event sources into a reverse-chronological,
cursor-paged event stream.

Constants (module-level):
  DORMANCY_DAYS = 14        — gap threshold for usage_reactivated events
  DEFAULT_LIMIT = 20        — default page size
  MAX_LIMIT = 100           — maximum page size
  USAGE_SCAN_WINDOW_DAYS = 365  — bounded window for notable-usage derivation scan

Cursor encoding:
  base64url(  ts_naive_utc_isoformat  |  event_type  |  source_id  )

Sort order:
  (timestamp DESC, type ASC, source_id ASC)

IMPORTANT — notable-usage derivation:
  The raw usage_events scan uses the full bounded window (USAGE_SCAN_WINDOW_DAYS).
  The 'before' cursor is NOT applied to the raw scan input so that gap-detection
  and first-occurrence detection see the complete history.  The derived synthetic
  events are filtered by the cursor after derivation, like every other source.
"""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DORMANCY_DAYS: int = 14
DEFAULT_LIMIT: int = 20
MAX_LIMIT: int = 100
USAGE_SCAN_WINDOW_DAYS: int = 365
CRM_RENEWAL_WINDOW_DAYS: int = 30

# Display names for crm_enrichment.provider values whose brand capitalization
# differs from str.title() (e.g. "hubspot".title() == "Hubspot", not
# "HubSpot"). Unknown/future providers fall back to .title().
_CRM_PROVIDER_DISPLAY_NAMES: dict = {
    "hubspot": "HubSpot",
    "salesforce": "Salesforce",
}


# ---------------------------------------------------------------------------
# Internal event shape
# ---------------------------------------------------------------------------

@dataclass
class TimelineEvent:
    """Internal timeline event.  source_id is used for cursor tiebreaking only
    and is NOT included in the external API response."""
    type: str
    timestamp: datetime        # always naive UTC after normalisation
    description: str
    source: str                # source table / discriminator
    source_id: int             # row id for tiebreaking
    feedback_id: Optional[int] = None
    old_score: Optional[int] = None
    new_score: Optional[int] = None
    risk_level: Optional[str] = None
    reason_code: Optional[str] = None
    feature_name: Optional[str] = None
    gap_days: Optional[int] = None
    # CRM payload fields (HubSpot)
    company_name: Optional[str] = None
    renewal_date: Optional[datetime] = None
    deal_stage: Optional[str] = None
    arr: Optional[float] = None


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------

def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise a datetime to naive UTC.
    Handles aware (tz=UTC or any tz) and naive (assumed UTC) inputs.
    Returns None if dt is None.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _encode_cursor(ts: datetime, event_type: str, source_id: int) -> str:
    """Encode a composite cursor as url-safe base64.

    Format: base64url( "<ts_isoformat>|<event_type>|<source_id>" )
    """
    raw = f"{ts.isoformat()}|{event_type}|{source_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> Tuple[datetime, str, int]:
    """Decode a cursor string.

    Returns (ts_naive_utc, event_type, source_id).
    Raises ValueError on malformed input.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Cursor is not valid base64: {exc}") from exc

    parts = raw.split("|")
    if len(parts) != 3:
        raise ValueError(
            f"Cursor decoded to {len(parts)} parts, expected 3: '{raw}'"
        )
    try:
        ts = datetime.fromisoformat(parts[0])
        event_type = parts[1]
        source_id = int(parts[2])
    except Exception as exc:
        raise ValueError(f"Cursor payload is malformed: {exc}") from exc

    return _to_naive_utc(ts), event_type, source_id


# ---------------------------------------------------------------------------
# Cursor filtering
# ---------------------------------------------------------------------------

def _after_cursor(
    event: TimelineEvent,
    cursor_ts: datetime,
    cursor_type: str,
    cursor_source_id: int,
) -> bool:
    """Return True if *event* comes AFTER *cursor* in the sort order
    (timestamp DESC, type ASC, source_id ASC).

    "After" means the event has not yet been returned and should appear on the
    next page.  In DESC time order, "after" = older or, within the same second,
    a higher type/source_id.
    """
    ets = event.timestamp
    if ets < cursor_ts:
        return True
    if ets == cursor_ts:
        if event.type > cursor_type:
            return True
        if event.type == cursor_type and event.source_id > cursor_source_id:
            return True
    return False


# ---------------------------------------------------------------------------
# Sort key
# ---------------------------------------------------------------------------

def _sort_key(event: TimelineEvent):
    """Composite sort: timestamp DESC (negate epoch), type ASC, source_id ASC."""
    return (-event.timestamp.timestamp(), event.type, event.source_id)


# ---------------------------------------------------------------------------
# Cursor SQL filter helper
# ---------------------------------------------------------------------------

def _sql_cursor_filter(ts_col, id_col, source_type: str, cursor_ts: datetime,
                       cursor_type: str, cursor_source_id: int):
    """Build a SQLAlchemy WHERE condition that restricts a single-type source to events
    that come strictly AFTER the cursor in (timestamp DESC, type ASC, source_id ASC) order.

    For a fixed-type source:
    - source_type < cursor_type: events at cursor_ts come before the cursor → only ts < cursor_ts
    - source_type > cursor_type: events at cursor_ts come after the cursor → ts <= cursor_ts
    - source_type == cursor_type: ts < cursor_ts, OR (ts == cursor_ts AND id > cursor_source_id)
    """
    from sqlalchemy import or_, and_
    if source_type < cursor_type:
        return ts_col < cursor_ts
    elif source_type > cursor_type:
        return ts_col <= cursor_ts
    else:  # same type
        return or_(
            ts_col < cursor_ts,
            and_(ts_col == cursor_ts, id_col > cursor_source_id),
        )


# ---------------------------------------------------------------------------
# Per-source fetch functions
# ---------------------------------------------------------------------------

def _fetch_feedback_created(
    db: Session,
    org_id: int,
    email: str,
    limit: int,
    cursor_ts: Optional[datetime],
    cursor_type: Optional[str] = None,
    cursor_source_id: Optional[int] = None,
) -> List[TimelineEvent]:
    from src.models.feedback import FeedbackItem as FeedbackModel

    q = db.query(FeedbackModel).filter(
        FeedbackModel.organization_id == org_id,
        FeedbackModel.customer_email == email,
    )
    if cursor_ts is not None:
        q = q.filter(_sql_cursor_filter(
            FeedbackModel.created_at, FeedbackModel.id,
            "feedback_created", cursor_ts, cursor_type, cursor_source_id,
        ))
    rows = q.order_by(desc(FeedbackModel.created_at), asc(FeedbackModel.id)).limit(limit).all()

    return [
        TimelineEvent(
            type="feedback_created",
            timestamp=_to_naive_utc(row.created_at),
            description="New feedback submitted",
            source="feedback_items",
            source_id=row.id,
            feedback_id=row.id,
        )
        for row in rows
    ]


def _fetch_status_changed(
    db: Session,
    org_id: int,
    email: str,
    limit: int,
    cursor_ts: Optional[datetime],
    cursor_type: Optional[str] = None,
    cursor_source_id: Optional[int] = None,
) -> List[TimelineEvent]:
    from src.models.feedback import FeedbackItem as FeedbackModel
    from src.models.feedback_workflow_event import FeedbackWorkflowEvent

    # Subquery: IDs of all feedbacks for this customer in this org
    fb_ids_subq = db.query(FeedbackModel.id).filter(
        FeedbackModel.organization_id == org_id,
        FeedbackModel.customer_email == email,
    )

    q = db.query(FeedbackWorkflowEvent).filter(
        FeedbackWorkflowEvent.organization_id == org_id,
        FeedbackWorkflowEvent.feedback_id.in_(fb_ids_subq),
        FeedbackWorkflowEvent.event_type == "status_changed",
    )
    if cursor_ts is not None:
        q = q.filter(_sql_cursor_filter(
            FeedbackWorkflowEvent.created_at, FeedbackWorkflowEvent.id,
            "status_changed", cursor_ts, cursor_type, cursor_source_id,
        ))
    rows = q.order_by(desc(FeedbackWorkflowEvent.created_at), asc(FeedbackWorkflowEvent.id)).limit(limit).all()

    return [
        TimelineEvent(
            type="status_changed",
            timestamp=_to_naive_utc(row.created_at),
            description=f"Feedback #{row.feedback_id} moved to {row.new_value}",
            source="feedback_workflow_events",
            source_id=row.id,
            feedback_id=row.feedback_id,
        )
        for row in rows
    ]


def _fetch_health_score_changed(
    db: Session,
    org_id: int,
    email: str,
    limit: int,
    cursor_ts: Optional[datetime],
    cursor_type: Optional[str] = None,
    cursor_source_id: Optional[int] = None,
) -> List[TimelineEvent]:
    from src.models.customer_health import CustomerHealth
    from src.models.customer_health_history import CustomerHealthHistory

    health = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.customer_email == email,
    ).first()

    if not health:
        return []

    # Fetch limit+1 records so the last record can provide old_score for
    # the second-to-last record.  The merged sort will truncate to limit.
    q = db.query(CustomerHealthHistory).filter(
        CustomerHealthHistory.customer_health_id == health.id,
    )
    if cursor_ts is not None:
        q = q.filter(_sql_cursor_filter(
            CustomerHealthHistory.recorded_at, CustomerHealthHistory.id,
            "health_score_changed", cursor_ts, cursor_type, cursor_source_id,
        ))
    rows = q.order_by(desc(CustomerHealthHistory.recorded_at), asc(CustomerHealthHistory.id)).limit(limit + 1).all()

    events: List[TimelineEvent] = []
    for i, row in enumerate(rows):
        prev_score = rows[i + 1].health_score if i + 1 < len(rows) else None
        if prev_score is not None:
            desc_text = f"Health score changed from {prev_score} to {row.health_score}"
        else:
            desc_text = f"Health score changed to {row.health_score}"
        events.append(TimelineEvent(
            type="health_score_changed",
            timestamp=_to_naive_utc(row.recorded_at),
            description=desc_text,
            source="customer_health_history",
            source_id=row.id,
            old_score=prev_score,
            new_score=row.health_score,
            risk_level=row.risk_level,
        ))
    # Return all fetched (up to limit+1); the merged sort truncates to limit
    return events


def _fetch_llm_analysis_generated(
    db: Session,
    org_id: int,
    email: str,
    cursor_ts: Optional[datetime],
) -> List[TimelineEvent]:
    from src.models.customer_health import CustomerHealth

    health = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.customer_email == email,
    ).first()

    if not health or not health.llm_analyzed_at:
        return []

    ts = _to_naive_utc(health.llm_analyzed_at)
    # Apply cursor filter in Python for this singleton
    if cursor_ts is not None and ts > cursor_ts:
        return []

    return [TimelineEvent(
        type="llm_analysis_generated",
        timestamp=ts,
        description="AI analysis generated",
        source="customer_health_scores",
        source_id=health.id,
    )]


def _fetch_action_completed(
    db: Session,
    org_id: int,
    email: str,
    limit: int,
    cursor_ts: Optional[datetime],
    cursor_type: Optional[str] = None,
    cursor_source_id: Optional[int] = None,
) -> List[TimelineEvent]:
    from src.models.customer_health import CustomerHealth
    from src.models.customer_analysis_action import CustomerAnalysisAction

    health = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.customer_email == email,
    ).first()

    if not health:
        return []

    q = db.query(CustomerAnalysisAction).filter(
        CustomerAnalysisAction.customer_health_id == health.id,
        CustomerAnalysisAction.status.in_(["completed", "dismissed"]),
        CustomerAnalysisAction.completed_at.isnot(None),
    )
    if cursor_ts is not None:
        q = q.filter(_sql_cursor_filter(
            CustomerAnalysisAction.completed_at, CustomerAnalysisAction.id,
            "action_completed", cursor_ts, cursor_type, cursor_source_id,
        ))
    rows = q.order_by(desc(CustomerAnalysisAction.completed_at), asc(CustomerAnalysisAction.id)).limit(limit).all()

    events: List[TimelineEvent] = []
    for row in rows:
        verb = "completed" if row.status == "completed" else "dismissed"
        events.append(TimelineEvent(
            type="action_completed",
            timestamp=_to_naive_utc(row.completed_at),
            description=f"Action {verb}: {row.action_text[:60]}",
            source="customer_analysis_actions",
            source_id=row.id,
        ))
    return events


def _fetch_churn_events(
    db: Session,
    org_id: int,
    email: str,
) -> List[TimelineEvent]:
    """Churn events emit two types per row ('churned' and 'churn_recovered').
    Because multiple types come from the same table we cannot use the single-type
    SQL cursor filter; instead we fetch all churn rows (few per customer) and let
    build_timeline's Python _after_cursor filter handle cursor correctness.
    """
    from src.models.churn_event import CustomerChurnEvent

    rows = db.query(CustomerChurnEvent).filter(
        CustomerChurnEvent.organization_id == org_id,
        CustomerChurnEvent.customer_email == email,
    ).order_by(desc(CustomerChurnEvent.churned_at)).all()

    events: List[TimelineEvent] = []
    for row in rows:
        events.append(TimelineEvent(
            type="churned",
            timestamp=_to_naive_utc(row.churned_at),
            description=f"Customer churned (reason: {row.reason_code})",
            source="customer_churn_events",
            source_id=row.id,
            reason_code=row.reason_code,
        ))
        if row.recovered_at:
            events.append(TimelineEvent(
                type="churn_recovered",
                timestamp=_to_naive_utc(row.recovered_at),
                description="Customer recovered from churn",
                source="customer_churn_events",
                source_id=row.id,
            ))
    return events


def _fetch_crm_events(
    db: Session,
    org_id: int,
    email: str,
) -> List[TimelineEvent]:
    """Derive CRM timeline events from the current crm_enrichment snapshot.

    Returns crm_contact_synced (anchored at last_synced_at) and optionally
    crm_renewal_upcoming (when renewal_date is within CRM_RENEWAL_WINDOW_DAYS).
    Both events are anchored at last_synced_at (not future dates) to keep the
    timeline reverse-chronological and cursor-safe.

    crm_deal_stage_changed is DEFERRED to v2 — a single current-state snapshot
    cannot detect a stage change (no per-sync history table in v1).
    """
    try:
        from src.models.crm_enrichment import CrmEnrichment
    except ImportError:
        return []

    row = db.query(CrmEnrichment).filter(
        CrmEnrichment.organization_id == org_id,
        CrmEnrichment.customer_email == email,
    ).first()

    if not row or not row.last_synced_at:
        return []

    events: List[TimelineEvent] = []
    sync_ts = _to_naive_utc(row.last_synced_at)

    provider = row.provider or "hubspot"
    provider_label = _CRM_PROVIDER_DISPLAY_NAMES.get(provider, provider.title())

    events.append(TimelineEvent(
        type="crm_contact_synced",
        timestamp=sync_ts,
        description=f"CRM contact synced from {provider_label}"
                    + (f" — {row.company_name}" if row.company_name else ""),
        source=provider,
        source_id=row.id,
        company_name=row.company_name,
    ))

    if row.renewal_date:
        rd = _to_naive_utc(row.renewal_date)
        now = datetime.utcnow()
        if now <= rd <= now + timedelta(days=CRM_RENEWAL_WINDOW_DAYS):
            events.append(TimelineEvent(
                type="crm_renewal_upcoming",
                timestamp=sync_ts,  # anchored at detection time, not the future date
                description=f"Renewal upcoming on {rd.date().isoformat()}",
                source=provider,
                source_id=row.id,
                renewal_date=rd,
                deal_stage=row.deal_stage,
                arr=float(row.arr) if row.arr is not None else None,
            ))

    return events


def _derive_notable_usage_events(
    db: Session,
    org_id: int,
    email: str,
) -> List[TimelineEvent]:
    """Derive notable usage events from usage_events + customer_usage.

    Scans the full USAGE_SCAN_WINDOW_DAYS window — the 'before' cursor is NOT
    applied to the scan input so gap-detection and first-occurrence detection
    are accurate.  The caller applies the cursor after derivation.
    """
    from src.models.customer_usage import CustomerUsage
    from src.models.usage_event import UsageEvent

    events: List[TimelineEvent] = []

    # --- usage_first_seen from customer_usage.first_seen_at ---
    usage_rollup = db.query(CustomerUsage).filter(
        CustomerUsage.organization_id == org_id,
        CustomerUsage.customer_email == email,
    ).first()

    if usage_rollup and usage_rollup.first_seen_at:
        events.append(TimelineEvent(
            type="usage_first_seen",
            timestamp=_to_naive_utc(usage_rollup.first_seen_at),
            description="Customer first seen using the product",
            source="customer_usage",
            source_id=usage_rollup.id,
        ))

    # --- Scan raw usage_events (bounded window, ASC for gap detection) ---
    scan_from = datetime.utcnow() - timedelta(days=USAGE_SCAN_WINDOW_DAYS)
    raw_events = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.organization_id == org_id,
            UsageEvent.customer_email == email,
            UsageEvent.occurred_at.isnot(None),
            UsageEvent.event_name.isnot(None),
            UsageEvent.occurred_at >= scan_from,
        )
        .order_by(asc(UsageEvent.occurred_at))
        .all()
    )

    # --- usage_feature_adopted: first occurrence per distinct event_name ---
    seen_features: dict = {}
    for ue in raw_events:
        if ue.event_name and ue.event_name not in seen_features:
            seen_features[ue.event_name] = ue

    for feature_name, ue in seen_features.items():
        events.append(TimelineEvent(
            type="usage_feature_adopted",
            timestamp=_to_naive_utc(ue.occurred_at),
            description=f"Feature adopted: {feature_name}",
            source="usage_events",
            source_id=ue.id,
            feature_name=feature_name,
        ))

    # --- usage_reactivated: event after a ≥ DORMANCY_DAYS gap ---
    last_ts: Optional[datetime] = None
    for ue in raw_events:
        ts = _to_naive_utc(ue.occurred_at)
        if last_ts is not None:
            gap = ts - last_ts
            if gap.days >= DORMANCY_DAYS:
                events.append(TimelineEvent(
                    type="usage_reactivated",
                    timestamp=ts,
                    description=f"Customer reactivated after {gap.days} days of inactivity",
                    source="usage_events",
                    source_id=ue.id,
                    gap_days=gap.days,
                ))
        last_ts = ts

    return events


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_timeline(
    db: Session,
    org_id: int,
    email: str,
    before: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> Tuple[List[TimelineEvent], Optional[str]]:
    """Build a cursor-paged, reverse-chronological timeline for one customer.

    Args:
        db:     SQLAlchemy session (already scoped to a request).
        org_id: Organisation ID — all queries are scoped to this org.
        email:  Customer email.
        before: Opaque cursor from a previous response's next_cursor.
                Decoded as (timestamp, type, source_id) composite.
        limit:  Maximum events to return (1–MAX_LIMIT).  Caller is responsible
                for clamping; FastAPI Query(ge=1, le=100) handles that at the
                endpoint level.

    Returns:
        (events, next_cursor) where next_cursor is None on the last page.

    Raises:
        ValueError: if *before* is provided but cannot be decoded.
    """
    # Decode cursor
    cursor_ts: Optional[datetime] = None
    cursor_type: Optional[str] = None
    cursor_source_id: Optional[int] = None
    if before:
        cursor_ts, cursor_type, cursor_source_id = _decode_cursor(before)

    # Overfetch by 1 from bounded sources so we can detect additional pages
    fetch_limit = limit + 1

    # --- Gather from all sources ---
    all_events: List[TimelineEvent] = []

    all_events.extend(
        _fetch_feedback_created(db, org_id, email, fetch_limit, cursor_ts, cursor_type, cursor_source_id)
    )
    all_events.extend(
        _fetch_status_changed(db, org_id, email, fetch_limit, cursor_ts, cursor_type, cursor_source_id)
    )
    all_events.extend(
        _fetch_health_score_changed(db, org_id, email, fetch_limit, cursor_ts, cursor_type, cursor_source_id)
    )
    all_events.extend(
        _fetch_llm_analysis_generated(db, org_id, email, cursor_ts)
    )
    all_events.extend(
        _fetch_action_completed(db, org_id, email, fetch_limit, cursor_ts, cursor_type, cursor_source_id)
    )
    # Churn uses Python-only cursor filtering (multi-type from same table, few rows)
    all_events.extend(
        _fetch_churn_events(db, org_id, email)
    )

    # CRM uses Python-only cursor filtering (single snapshot row, few events)
    all_events.extend(
        _fetch_crm_events(db, org_id, email)
    )

    # Notable usage: always scan full window, cursor applied below
    usage_events = _derive_notable_usage_events(db, org_id, email)
    if cursor_ts is not None:
        usage_events = [e for e in usage_events if e.timestamp <= cursor_ts]
    all_events.extend(usage_events)

    # --- Sort: (timestamp DESC, type ASC, source_id ASC) ---
    all_events.sort(key=_sort_key)

    # --- Apply composite cursor filter ---
    if cursor_ts is not None:
        all_events = [
            e for e in all_events
            if _after_cursor(e, cursor_ts, cursor_type, cursor_source_id)
        ]

    # --- Determine page ---
    has_more = len(all_events) > limit
    result = all_events[:limit]

    next_cursor: Optional[str] = None
    if has_more and result:
        last = result[-1]
        next_cursor = _encode_cursor(last.timestamp, last.type, last.source_id)

    return result, next_cursor
