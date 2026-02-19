"""
Customer health score computation service.
Computes a 0-100 health score per customer using churn-heavy weights.
Higher score = healthier customer.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Weight distribution (churn-heavy as per PRD)
WEIGHTS = {
    "churn_risk": 0.35,
    "sentiment": 0.25,
    "resolution": 0.25,
    "frequency": 0.15,
}


def compute_health_score(org_id: int, customer_email: str, db: Session) -> dict:
    """Compute 0-100 health score (higher = healthier) for a customer."""
    from src.models.feedback import FeedbackItem

    now = datetime.utcnow()

    # Churn risk component (35%): inverted avg churn_risk_score
    churn_component = _compute_churn_component(db, org_id, customer_email, now)

    # Sentiment component (25%): avg sentiment mapped to 0-100
    sentiment_component = _compute_sentiment_component(db, org_id, customer_email, now)

    # Resolution component (25%): faster resolution = higher score
    resolution_component = _compute_resolution_component(db, org_id, customer_email, now)

    # Frequency component (15%): stable/declining frequency = healthy
    frequency_component = _compute_frequency_component(db, org_id, customer_email, now)

    # Weighted sum
    health_score = int(
        churn_component * WEIGHTS["churn_risk"] +
        sentiment_component * WEIGHTS["sentiment"] +
        resolution_component * WEIGHTS["resolution"] +
        frequency_component * WEIGHTS["frequency"]
    )
    health_score = max(0, min(100, health_score))

    # Risk level
    if health_score >= 70:
        risk_level = "healthy"
    elif health_score >= 50:
        risk_level = "moderate"
    elif health_score >= 30:
        risk_level = "at_risk"
    else:
        risk_level = "critical"

    # Get feedback count and last feedback date
    from src.models.feedback import FeedbackItem
    feedback_count = db.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
    ).scalar() or 0

    last_feedback = db.query(func.max(FeedbackItem.created_at)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
    ).scalar()

    # Try to get customer name from most recent feedback
    customer_name = None
    latest = db.query(FeedbackItem.source_metadata).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.source_metadata.isnot(None),
    ).order_by(FeedbackItem.created_at.desc()).first()
    if latest and latest.source_metadata and isinstance(latest.source_metadata, dict):
        customer_name = latest.source_metadata.get('author_name') or latest.source_metadata.get('name')

    # Confidence level based on feedback count
    if feedback_count <= 2:
        confidence_level = "low"
    elif feedback_count <= 9:
        confidence_level = "medium"
    else:
        confidence_level = "high"

    return {
        "health_score": health_score,
        "churn_risk_component": churn_component,
        "sentiment_component": sentiment_component,
        "resolution_component": resolution_component,
        "frequency_component": frequency_component,
        "risk_level": risk_level,
        "feedback_count": feedback_count,
        "last_feedback_at": last_feedback,
        "customer_name": customer_name,
        "confidence_level": confidence_level,
    }


def update_customer_health(org_id: int, customer_email: str, db: Session) -> None:
    """Compute and upsert customer health score, recording history on significant changes."""
    from src.models.customer_health import CustomerHealth
    from src.models.customer_health_history import CustomerHealthHistory

    result = compute_health_score(org_id, customer_email, db)
    new_score = result["health_score"]

    existing = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.customer_email == customer_email,
    ).first()

    if existing:
        old_score = existing.health_score
        existing.health_score = new_score
        existing.churn_risk_component = result["churn_risk_component"]
        existing.sentiment_component = result["sentiment_component"]
        existing.resolution_component = result["resolution_component"]
        existing.frequency_component = result["frequency_component"]
        existing.risk_level = result["risk_level"]
        existing.feedback_count = result["feedback_count"]
        existing.last_feedback_at = result["last_feedback_at"]
        existing.customer_name = result["customer_name"]
        existing.confidence_level = result["confidence_level"]
        existing.is_archived = False  # Unarchive when new feedback arrives
        existing.updated_at = datetime.utcnow()

        # Record history if score changed by ≥ 2 points
        should_record = abs(new_score - old_score) >= 2
    else:
        health = CustomerHealth(
            organization_id=org_id,
            customer_email=customer_email,
            customer_name=result["customer_name"],
            health_score=new_score,
            churn_risk_component=result["churn_risk_component"],
            sentiment_component=result["sentiment_component"],
            resolution_component=result["resolution_component"],
            frequency_component=result["frequency_component"],
            feedback_count=result["feedback_count"],
            last_feedback_at=result["last_feedback_at"],
            risk_level=result["risk_level"],
            confidence_level=result["confidence_level"],
            is_archived=False,
        )
        db.add(health)
        db.flush()  # Get the id before creating history
        existing = health
        should_record = True  # Always record first entry

    # Insert history record if warranted
    if should_record:
        history = CustomerHealthHistory(
            customer_health_id=existing.id,
            organization_id=org_id,
            health_score=new_score,
            churn_risk_component=result["churn_risk_component"],
            sentiment_component=result["sentiment_component"],
            resolution_component=result["resolution_component"],
            frequency_component=result["frequency_component"],
            risk_level=result["risk_level"],
        )
        db.add(history)


def compute_sentiment_trend(org_id: int, customer_email: str, db: Session) -> dict:
    """Compare avg sentiment last 7d vs previous 7d to determine trend direction."""
    from src.models.feedback import FeedbackItem

    now = datetime.utcnow()

    recent = db.query(func.avg(FeedbackItem.sentiment_score)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.sentiment_score.isnot(None),
        FeedbackItem.created_at >= now - timedelta(days=7),
    ).scalar()

    previous = db.query(func.avg(FeedbackItem.sentiment_score)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.sentiment_score.isnot(None),
        FeedbackItem.created_at >= now - timedelta(days=14),
        FeedbackItem.created_at < now - timedelta(days=7),
    ).scalar()

    # If no data in either period, return stable
    if previous is None or previous == 0:
        return {"direction": "stable", "change_percent": 0}

    if recent is None:
        recent = 0.0

    change = ((recent - previous) / abs(previous)) * 100
    if change > 5:
        direction = "improving"
    elif change < -5:
        direction = "declining"
    else:
        direction = "stable"

    return {"direction": direction, "change_percent": round(change, 1)}


def _compute_churn_component(db, org_id, customer_email, now) -> int:
    """Churn risk component: inverted avg churn_risk_score (0-100)."""
    from src.models.feedback import FeedbackItem
    avg_churn = db.query(func.avg(FeedbackItem.churn_risk_score)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.churn_risk_score.isnot(None),
        FeedbackItem.created_at >= now - timedelta(days=30),
    ).scalar()
    if avg_churn is None:
        return 50  # No data = neutral
    return max(0, int(100 - avg_churn))


def _compute_sentiment_component(db, org_id, customer_email, now) -> int:
    """Sentiment component: avg sentiment score mapped to 0-100."""
    from src.models.feedback import FeedbackItem
    avg_sentiment = db.query(func.avg(FeedbackItem.sentiment_score)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.sentiment_score.isnot(None),
        FeedbackItem.created_at >= now - timedelta(days=30),
    ).scalar()
    if avg_sentiment is None:
        return 50
    # Map -1.0..1.0 to 0..100
    return max(0, min(100, int((avg_sentiment + 1) * 50)))


def _compute_resolution_component(db, org_id, customer_email, now) -> int:
    """Resolution component: faster resolution = higher score."""
    from src.models.feedback import FeedbackItem
    from src.models.feedback_workflow_event import FeedbackWorkflowEvent

    try:
        resolved_events = db.query(
            FeedbackWorkflowEvent.feedback_id,
            FeedbackWorkflowEvent.created_at,
        ).filter(
            FeedbackWorkflowEvent.organization_id == org_id,
            FeedbackWorkflowEvent.event_type == 'status_changed',
            FeedbackWorkflowEvent.new_value == 'resolved',
        ).join(
            FeedbackItem, FeedbackItem.id == FeedbackWorkflowEvent.feedback_id,
        ).filter(
            FeedbackItem.customer_email == customer_email,
            FeedbackItem.created_at >= now - timedelta(days=60),
        ).all()

        if not resolved_events:
            return 50  # No data = neutral

        feedback_ids = [e.feedback_id for e in resolved_events]
        create_dates = {
            row.id: row.created_at
            for row in db.query(FeedbackItem.id, FeedbackItem.created_at).filter(
                FeedbackItem.id.in_(feedback_ids),
            ).all()
        }

        total_days = 0
        count = 0
        for event in resolved_events:
            created = create_dates.get(event.feedback_id)
            if created:
                delta = (event.created_at - created).total_seconds() / 86400
                total_days += delta
                count += 1

        if count == 0:
            return 50

        avg_days = total_days / count
        # Map: 0 days = 100, 1 day = 90, 3 days = 70, 7 days = 40, 14+ days = 10
        if avg_days <= 0.5:
            return 100
        elif avg_days <= 1:
            return 90
        elif avg_days <= 3:
            return 70
        elif avg_days <= 7:
            return 40
        else:
            return 10
    except Exception:
        return 50


def _compute_frequency_component(db, org_id, customer_email, now) -> int:
    """Frequency component: stable/declining complaint frequency = healthier."""
    from src.models.feedback import FeedbackItem

    last_7d = db.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.created_at >= now - timedelta(days=7),
    ).scalar() or 0

    last_30d = db.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.created_at >= now - timedelta(days=30),
    ).scalar() or 0

    if last_30d == 0:
        return 50  # No data

    avg_weekly = last_30d / 4.0

    if avg_weekly == 0:
        return 80  # Very infrequent = healthy

    ratio = last_7d / avg_weekly
    # ratio < 0.5 = declining (great), 0.5-1.5 = stable (good), 1.5-2 = increasing (warning), 2+ = spiking (bad)
    if ratio <= 0.5:
        return 100
    elif ratio <= 1.0:
        return 80
    elif ratio <= 1.5:
        return 60
    elif ratio <= 2.0:
        return 30
    else:
        return 10
