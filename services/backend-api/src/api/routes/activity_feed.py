"""Activity feed endpoint — aggregates recent events across the organization."""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.audit_log import AuditLog
from src.models.anomaly import SentimentAnomaly
from src.models.organization import Organization
from src.api.dependencies import get_current_org
from src.services.cache_service import cache_get, cache_set

router = APIRouter(prefix="/api/v1/activity-feed", tags=["activity-feed"])


# Schemas
class ActivityItem(BaseModel):
    id: int
    type: str  # feedback_received, urgent_flagged, anomaly_detected, team_action
    title: str
    subtitle: Optional[str] = None
    severity: str  # info, warning, critical
    created_at: datetime
    link: Optional[str] = None


class ActivityFeedResponse(BaseModel):
    items: List[ActivityItem]
    last_updated: datetime


# Severity mapping
SEVERITY_MAP = {
    "feedback_received": "info",
    "urgent_flagged": "critical",
    "anomaly_detected": "warning",
    "team_action": "info",
}


def _build_feedback_items(db: Session, org_id: int, since: Optional[datetime], limit: int) -> List[dict]:
    """Query recent non-urgent feedback items."""
    query = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.is_urgent == False,
    )
    if since:
        query = query.filter(FeedbackItem.created_at > since)
    rows = query.order_by(desc(FeedbackItem.created_at)).limit(limit).all()

    results = []
    for row in rows:
        source_label = f"via {row.source}" if row.source else "via manual entry"
        customer = row.customer_email or "anonymous"
        results.append({
            "id": row.id,
            "type": "feedback_received",
            "title": f"New feedback from {customer}",
            "subtitle": source_label,
            "severity": SEVERITY_MAP["feedback_received"],
            "created_at": row.created_at,
            "link": f"/feedbacks/{row.id}",
        })
    return results


def _build_urgent_items(db: Session, org_id: int, since: Optional[datetime], limit: int) -> List[dict]:
    """Query recent urgent-flagged feedback."""
    query = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.is_urgent == True,
    )
    if since:
        query = query.filter(FeedbackItem.created_at > since)
    rows = query.order_by(desc(FeedbackItem.created_at)).limit(limit).all()

    results = []
    for row in rows:
        category_label = row.urgent_category.replace("_", " ").title() if row.urgent_category else "Urgent"
        results.append({
            "id": row.id,
            "type": "urgent_flagged",
            "title": f"{category_label} flagged",
            "subtitle": row.text[:80] + ("..." if len(row.text) > 80 else ""),
            "severity": SEVERITY_MAP["urgent_flagged"],
            "created_at": row.created_at,
            "link": f"/feedbacks/{row.id}",
        })
    return results


def _build_anomaly_items(db: Session, org_id: int, since: Optional[datetime], limit: int) -> List[dict]:
    """Query recent sentiment anomalies."""
    query = db.query(SentimentAnomaly).filter(
        SentimentAnomaly.organization_id == org_id,
    )
    if since:
        query = query.filter(SentimentAnomaly.detected_at > since)
    rows = query.order_by(desc(SentimentAnomaly.detected_at)).limit(limit).all()

    results = []
    for row in rows:
        anomaly_label = row.anomaly_type.replace("_", " ").title()
        results.append({
            "id": row.id,
            "type": "anomaly_detected",
            "title": f"Sentiment anomaly: {anomaly_label}",
            "subtitle": f"{row.deviation_pct:+.1f}% deviation over {row.time_window_hours}h window",
            "severity": SEVERITY_MAP["anomaly_detected"],
            "created_at": row.detected_at,
            "link": "/dashboard",
        })
    return results


def _build_team_action_items(db: Session, org_id: int, since: Optional[datetime], limit: int) -> List[dict]:
    """Query recent audit log entries (team actions)."""
    query = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
    )
    if since:
        query = query.filter(AuditLog.created_at > since)
    rows = query.order_by(desc(AuditLog.created_at)).limit(limit).all()

    results = []
    for row in rows:
        action_label = row.action.replace("_", " ").title()
        results.append({
            "id": row.id,
            "type": "team_action",
            "title": f"{action_label} by {row.user_email}",
            "subtitle": None,
            "severity": SEVERITY_MAP["team_action"],
            "created_at": row.created_at,
            "link": None,
        })
    return results


@router.get("/", response_model=ActivityFeedResponse)
def get_activity_feed(
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    since: Optional[datetime] = Query(None, description="Only return items after this timestamp"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get recent activity feed for the current organization.

    Aggregates events from feedback, urgent flags, anomalies, and team actions,
    ordered by most recent first.
    """
    cache_key = f"activity_feed:{current_org.id}:{limit}:{since.isoformat() if since else 'all'}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Fetch from each source (fetch more than needed, then merge & trim)
    all_items: List[dict] = []
    all_items.extend(_build_feedback_items(db, current_org.id, since, limit))
    all_items.extend(_build_urgent_items(db, current_org.id, since, limit))
    all_items.extend(_build_anomaly_items(db, current_org.id, since, limit))
    all_items.extend(_build_team_action_items(db, current_org.id, since, limit))

    # Sort by created_at descending, take top `limit`
    all_items.sort(key=lambda x: x["created_at"], reverse=True)
    all_items = all_items[:limit]

    items = [ActivityItem(**item) for item in all_items]

    result = ActivityFeedResponse(
        items=items,
        last_updated=datetime.utcnow(),
    )

    cache_set(cache_key, result.dict(), ttl_seconds=5)  # Short TTL — polled every 30s
    return result
