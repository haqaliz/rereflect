"""
Anomaly detection tasks for sentiment spike detection.
Runs hourly via Celery Beat to detect negative sentiment spikes.
"""

import logging
import math
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)


@shared_task
def detect_sentiment_anomalies() -> dict:
    """
    Periodic task: Detect negative sentiment spikes for each organization.
    Runs every hour via Celery Beat.

    Algorithm:
    - For each org, compare last 24h negative sentiment % vs 30-day rolling average
    - If deviation > 2 standard deviations → create warning anomaly
    - If deviation > 3 standard deviations → create critical anomaly

    Returns:
        dict with detection results
    """
    from sqlalchemy import func, case
    from src.models import FeedbackItem, Organization, SentimentAnomaly

    with get_db_session() as db:
        organizations = db.query(Organization).all()

        if not organizations:
            return {"status": "no_organizations", "anomalies_created": 0}

        anomalies_created = 0
        orgs_checked = 0

        for org in organizations:
            try:
                result = _check_org_for_anomaly(db, org)
                if result:
                    anomalies_created += 1
                orgs_checked += 1
            except Exception as e:
                logger.error(f"Error checking anomalies for org {org.id}: {e}")

        db.commit()

        logger.info(f"Anomaly check: {orgs_checked} orgs checked, {anomalies_created} anomalies created")

        return {
            "status": "complete",
            "orgs_checked": orgs_checked,
            "anomalies_created": anomalies_created,
        }


def _check_org_for_anomaly(db, org) -> bool:
    """
    Check a single organization for sentiment anomalies.
    Returns True if an anomaly was created.
    """
    from sqlalchemy import func, case
    from src.models import FeedbackItem, SentimentAnomaly

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_30d = now - timedelta(days=30)

    # Skip if there's already an unresolved anomaly for this org in the last 24h
    recent_anomaly = db.query(SentimentAnomaly).filter(
        SentimentAnomaly.organization_id == org.id,
        SentimentAnomaly.is_resolved == False,
        SentimentAnomaly.detected_at >= last_24h,
    ).first()

    if recent_anomaly:
        return False

    # Get 30-day baseline: count negative per day
    daily_stats = db.query(
        func.date(FeedbackItem.created_at).label("day"),
        func.count(FeedbackItem.id).label("total"),
        func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("negative"),
    ).filter(
        FeedbackItem.organization_id == org.id,
        FeedbackItem.created_at >= last_30d,
        FeedbackItem.sentiment_label.isnot(None),
    ).group_by(
        func.date(FeedbackItem.created_at)
    ).all()

    if len(daily_stats) < 7:
        # Not enough data to establish baseline
        return False

    # Calculate daily negative percentages
    daily_neg_pcts = []
    for day_stat in daily_stats:
        total = int(day_stat.total or 0)
        negative = int(day_stat.negative or 0)
        if total > 0:
            daily_neg_pcts.append(negative / total * 100)

    if not daily_neg_pcts:
        return False

    # Calculate mean and standard deviation
    mean_neg_pct = sum(daily_neg_pcts) / len(daily_neg_pcts)
    if len(daily_neg_pcts) < 2:
        return False

    variance = sum((x - mean_neg_pct) ** 2 for x in daily_neg_pcts) / (len(daily_neg_pcts) - 1)
    std_dev = math.sqrt(variance)

    if std_dev < 1.0:
        # Very low variance, set minimum threshold
        std_dev = 5.0

    # Get last 24h stats
    recent_stats = db.query(
        func.count(FeedbackItem.id).label("total"),
        func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("negative"),
    ).filter(
        FeedbackItem.organization_id == org.id,
        FeedbackItem.created_at >= last_24h,
        FeedbackItem.sentiment_label.isnot(None),
    ).first()

    recent_total = int(recent_stats.total or 0)
    recent_negative = int(recent_stats.negative or 0)

    if recent_total < 5:
        # Not enough recent feedback to detect anomaly
        return False

    current_neg_pct = (recent_negative / recent_total) * 100
    deviation = (current_neg_pct - mean_neg_pct) / std_dev

    if deviation < 2.0:
        # No anomaly
        return False

    # Determine severity
    severity = "critical" if deviation >= 3.0 else "warning"
    deviation_pct = round(current_neg_pct - mean_neg_pct, 1)

    anomaly = SentimentAnomaly(
        organization_id=org.id,
        detected_at=now,
        anomaly_type="negative_spike",
        severity=severity,
        baseline_negative_pct=round(mean_neg_pct, 1),
        current_negative_pct=round(current_neg_pct, 1),
        deviation_pct=deviation_pct,
        time_window_hours=24,
        feedback_count=recent_total,
        is_resolved=False,
    )
    db.add(anomaly)

    # Dispatch alerts
    _dispatch_anomaly_alerts(db, org, anomaly)

    logger.warning(
        f"Anomaly detected for org {org.id}: {severity} - "
        f"{current_neg_pct:.1f}% negative vs {mean_neg_pct:.1f}% baseline "
        f"({deviation:.1f} sigma)"
    )

    return True


def _dispatch_anomaly_alerts(db, org, anomaly):
    """Dispatch anomaly alerts via the new per-user preference system."""
    from src.notification_dispatch import dispatch_alert

    severity_label = anomaly.severity.upper()
    dispatch_alert(
        org_id=org.id,
        alert_type="sentiment_spike",
        title=f"Sentiment Anomaly ({severity_label}): {anomaly.current_negative_pct:.0f}% negative",
        message=(
            f"Negative sentiment spiked to {anomaly.current_negative_pct:.0f}% "
            f"(baseline: {anomaly.baseline_negative_pct:.0f}%, "
            f"+{anomaly.deviation_pct:.0f}pp). "
            f"Based on {anomaly.feedback_count} feedback items in the last 24h."
        ),
        link="/dashboard",
        metadata={
            "anomaly_id": anomaly.id if hasattr(anomaly, 'id') and anomaly.id else None,
            "severity": anomaly.severity,
            "current_negative_pct": anomaly.current_negative_pct,
            "baseline_negative_pct": anomaly.baseline_negative_pct,
        },
    )
