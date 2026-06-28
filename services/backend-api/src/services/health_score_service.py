"""
Customer health score computation service.
Computes a 0-100 health score per customer using churn-heavy weights.
Higher score = healthier customer.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Risk level ordering: lower index = healthier
RISK_LEVEL_ORDER = {"healthy": 0, "moderate": 1, "at_risk": 2, "critical": 3}

# Default alert thresholds
DEFAULT_ALERT_THRESHOLD = 50.0  # absolute threshold: alert when score drops below this
DEFAULT_DROP_THRESHOLD = 15     # point-drop threshold: alert when score drops by this many pts

# Weight distribution (churn-heavy as per PRD)
# Usage defaults to 0.0 — opt-in only; existing scores unchanged until re-weighted.
WEIGHTS = {
    "churn_risk": 0.35,
    "sentiment": 0.25,
    "resolution": 0.25,
    "frequency": 0.15,
    "usage": 0.0,
}


def _get_org_weights(org_id: int, db: Session) -> dict:
    """Return per-org health-score weights, falling back to module-level defaults."""
    try:
        from src.models.org_ai_config import OrgAIConfig
        config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
        if config is not None:
            return {
                "churn_risk": config.health_weight_churn / 100.0,
                "sentiment": config.health_weight_sentiment / 100.0,
                "resolution": config.health_weight_resolution / 100.0,
                "frequency": config.health_weight_frequency / 100.0,
                "usage": config.health_weight_usage / 100.0,
            }
    except Exception:
        pass
    return WEIGHTS


def _compute_usage_component(db: Session, org_id: int, customer_email: str, now: datetime) -> int:
    """
    Fetch the pre-computed usage_score from customer_usage rollup table.

    Returns 50 (neutral) when:
      - The customer_usage table does not yet exist (aspect usage-rollup-and-score
        creates it later in the feature chain).
      - No rollup row exists for this customer.
      - Any other error occurs during the query.

    Contract: this function NEVER raises; it is always safe to call.
    The actual usage_score is computed by aspect `usage-rollup-and-score`.
    """
    try:
        from sqlalchemy import text
        result = db.execute(
            text(
                "SELECT usage_score FROM customer_usage "
                "WHERE organization_id = :org_id AND customer_email = :email "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            {"org_id": org_id, "email": customer_email},
        ).fetchone()
        if result is not None and result[0] is not None:
            return int(result[0])
    except Exception:
        # Table does not exist yet or any other DB error — return neutral score
        pass
    return 50


def compute_health_score(org_id: int, customer_email: str, db: Session) -> dict:
    """Compute 0-100 health score (higher = healthier) for a customer."""
    from src.models.feedback import FeedbackItem

    now = datetime.utcnow()

    # Churn risk component (35% default): inverted avg churn_risk_score
    churn_component = _compute_churn_component(db, org_id, customer_email, now)

    # Sentiment component (25% default): avg sentiment mapped to 0-100
    sentiment_component = _compute_sentiment_component(db, org_id, customer_email, now)

    # Resolution component (25% default): faster resolution = higher score
    resolution_component = _compute_resolution_component(db, org_id, customer_email, now)

    # Frequency component (15% default): stable/declining frequency = healthy
    frequency_component = _compute_frequency_component(db, org_id, customer_email, now)

    # Usage component (0% default, opt-in): sourced from customer_usage rollup;
    # falls back to 50 (neutral) when no rollup exists.
    usage_component = _compute_usage_component(db, org_id, customer_email, now)

    # Weighted sum using per-org configured weights (or defaults)
    weights = _get_org_weights(org_id, db)
    health_score = int(
        churn_component * weights["churn_risk"] +
        sentiment_component * weights["sentiment"] +
        resolution_component * weights["resolution"] +
        frequency_component * weights["frequency"] +
        usage_component * weights["usage"]
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
        "usage_component": usage_component,
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
    from src.models.feedback import FeedbackItem

    result = compute_health_score(org_id, customer_email, db)
    new_score = result["health_score"]

    # Compute granular confidence score from volume + recency + topic diversity
    unique_pain_cats = db.query(func.count(func.distinct(FeedbackItem.pain_point_category))).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.pain_point_category.isnot(None),
    ).scalar() or 0

    unique_feature_cats = db.query(func.count(func.distinct(FeedbackItem.feature_request_category))).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.feature_request_category.isnot(None),
    ).scalar() or 0

    confidence = compute_confidence_score(
        feedback_count=result["feedback_count"],
        last_feedback_at=result["last_feedback_at"],
        unique_categories=unique_pain_cats + unique_feature_cats,
    )
    confidence_level = "low" if confidence <= 30 else ("medium" if confidence <= 60 else "high")

    existing = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.customer_email == customer_email,
    ).first()

    if existing:
        old_score = existing.health_score
        old_risk_level = existing.risk_level
        existing.health_score = new_score
        existing.churn_risk_component = result["churn_risk_component"]
        existing.sentiment_component = result["sentiment_component"]
        existing.resolution_component = result["resolution_component"]
        existing.frequency_component = result["frequency_component"]
        existing.usage_component = result["usage_component"]
        existing.risk_level = result["risk_level"]
        existing.feedback_count = result["feedback_count"]
        existing.last_feedback_at = result["last_feedback_at"]
        existing.customer_name = result["customer_name"]
        existing.confidence_level = confidence_level
        existing.confidence_score = confidence
        existing.is_archived = False  # Unarchive when new feedback arrives
        existing.updated_at = datetime.utcnow()

        # Record history if score changed by ≥ 2 points
        should_record = abs(new_score - old_score) >= 2

        # Check if health drop alert should fire
        _check_health_drop_alert(
            org_id=org_id,
            customer_email=customer_email,
            customer_name=result["customer_name"],
            old_score=old_score,
            new_score=new_score,
            old_risk_level=old_risk_level,
            new_risk_level=result["risk_level"],
            components={
                "churn_risk": result["churn_risk_component"],
                "sentiment": result["sentiment_component"],
                "resolution": result["resolution_component"],
                "frequency": result["frequency_component"],
            },
            db=db,
        )

        # Automation rules — health_score_threshold and churn_risk_level_change triggers
        try:
            from src.services.automation_engine import AutomationEngine
            engine = AutomationEngine(db)
            health_context = {
                "health_score": new_score,
                "new_risk_level": result["risk_level"],
                "old_risk_level": old_risk_level,
                "customer_email": customer_email,
                "feedback_id": None,
            }
            engine.evaluate(org_id, "health_score_threshold", health_context)
            engine.evaluate(org_id, "churn_risk_level_change", health_context)
        except Exception as _ae:
            logger.warning(
                "Automation engine dispatch failed after health score update for %s: %s",
                customer_email, _ae,
            )
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
            usage_component=result["usage_component"],
            feedback_count=result["feedback_count"],
            last_feedback_at=result["last_feedback_at"],
            risk_level=result["risk_level"],
            confidence_level=confidence_level,
            confidence_score=confidence,
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
            usage_component=result["usage_component"],
            risk_level=result["risk_level"],
        )
        db.add(history)


def compute_confidence_score(feedback_count: int, last_feedback_at, unique_categories: int) -> int:
    """
    Compute a 0-100 confidence score for customer health predictions.

    Three factors:
    - Volume (0-40): based on feedback_count
    - Recency (0-35): based on days since last feedback
    - Diversity (0-25): based on unique_categories (distinct pain/feature categories)
    """
    # Factor 1: Data volume (0-40 points)
    if feedback_count >= 20:
        volume_score = 40
    elif feedback_count >= 10:
        volume_score = 30
    elif feedback_count >= 5:
        volume_score = 20
    elif feedback_count >= 3:
        volume_score = 10
    else:
        volume_score = feedback_count * 3  # 0, 3, 6

    # Factor 2: Data recency (0-35 points)
    if last_feedback_at is None:
        recency_score = 0
    else:
        days_since = (datetime.utcnow() - last_feedback_at).days
        if days_since <= 7:
            recency_score = 35
        elif days_since <= 14:
            recency_score = 28
        elif days_since <= 30:
            recency_score = 20
        elif days_since <= 60:
            recency_score = 10
        else:
            recency_score = 5

    # Factor 3: Topic diversity (0-25 points)
    if unique_categories >= 5:
        diversity_score = 25
    elif unique_categories >= 3:
        diversity_score = 18
    elif unique_categories >= 2:
        diversity_score = 10
    else:
        diversity_score = 5

    return min(volume_score + recency_score + diversity_score, 100)


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


def _check_health_drop_alert(
    org_id: int,
    customer_email: str,
    customer_name: Optional[str],
    old_score: int,
    new_score: int,
    old_risk_level: str,
    new_risk_level: str,
    components: Dict[str, int],
    db: Session,
) -> None:
    """
    Check if a health drop alert should fire and dispatch it.

    Alert conditions (any one triggers):
    1. Score crosses below absolute threshold (default 50)
    2. Score drops by >= drop_threshold (default 15 points)
    3. Risk level downgrade (healthy→moderate, moderate→at_risk, at_risk→critical)
    4. Risk level upgrade (recovery alert)

    Called only for existing customers (not new ones).
    """
    old_order = RISK_LEVEL_ORDER.get(old_risk_level, 0)
    new_order = RISK_LEVEL_ORDER.get(new_risk_level, 0)

    is_risk_downgrade = new_order > old_order
    is_risk_upgrade = new_order < old_order

    # Recovery alert: risk level improved
    if is_risk_upgrade:
        try:
            _do_dispatch_health_drop_alert(
                org_id=org_id,
                customer_email=customer_email,
                customer_name=customer_name,
                old_score=old_score,
                new_score=new_score,
                old_risk_level=old_risk_level,
                new_risk_level=new_risk_level,
                components=components,
                is_recovery=True,
            )
        except Exception as e:
            logger.error(f"Failed to dispatch recovery alert for {customer_email}: {e}")
        return

    # Drop conditions
    threshold_crossed = new_score < DEFAULT_ALERT_THRESHOLD and old_score >= DEFAULT_ALERT_THRESHOLD
    large_drop = (old_score - new_score) >= DEFAULT_DROP_THRESHOLD

    should_alert = threshold_crossed or large_drop or is_risk_downgrade

    if should_alert:
        try:
            _do_dispatch_health_drop_alert(
                org_id=org_id,
                customer_email=customer_email,
                customer_name=customer_name,
                old_score=old_score,
                new_score=new_score,
                old_risk_level=old_risk_level,
                new_risk_level=new_risk_level,
                components=components,
                is_recovery=False,
            )
        except Exception as e:
            logger.error(f"Failed to dispatch health drop alert for {customer_email}: {e}")


def dispatch_health_drop_alert(
    org_id: int,
    customer_email: str,
    customer_name: Optional[str],
    old_score: int,
    new_score: int,
    old_risk_level: str,
    new_risk_level: str,
    components: Dict[str, int],
    is_recovery: bool = False,
) -> None:
    """
    Dispatch a health drop (or recovery) alert for a customer.

    Routes to the notification_dispatch_helpers backend implementation.
    Defined at module level so tests can mock it by patching
    src.services.health_score_service.dispatch_health_drop_alert.
    """
    from src.notification_dispatch_helpers import dispatch_health_drop_alert_impl
    dispatch_health_drop_alert_impl(
        org_id=org_id,
        customer_email=customer_email,
        customer_name=customer_name,
        old_score=old_score,
        new_score=new_score,
        old_risk_level=old_risk_level,
        new_risk_level=new_risk_level,
        components=components,
        is_recovery=is_recovery,
    )


def _do_dispatch_health_drop_alert(**kwargs) -> None:
    """
    Internal forwarder that calls dispatch_health_drop_alert.
    Using this indirection allows tests to patch dispatch_health_drop_alert
    at the module level while _check_health_drop_alert calls this function.
    """
    import src.services.health_score_service as _mod
    _mod.dispatch_health_drop_alert(**kwargs)
