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
# Usage and CRM default to 0.0 — opt-in only; existing scores unchanged until re-weighted.
WEIGHTS = {
    "churn_risk": 0.35,
    "sentiment": 0.25,
    "resolution": 0.25,
    "frequency": 0.15,
    "usage": 0.0,
    "crm": 0.0,   # Opt-in CRM component; existing scores unchanged at weight 0
}

# CRM component — renewal-proximity heuristic constants.
# This is a documented heuristic, NOT a trained model. Operators opt in by
# setting health_weight_crm > 0. Tune thresholds here without a schema change.
CRM_RENEWAL_DAYS_WARN   = 30    # <= this many days to renewal -> risk territory
CRM_RENEWAL_DAYS_HIGH   = 14    # <= this many days -> higher risk
CRM_RENEWAL_DAYS_CRIT   = 7     # <= this many days -> critical risk
CRM_SCORE_NEUTRAL       = 50.0  # No enrichment row / no renewal date -> neutral
CRM_SCORE_WARN          = 35.0  # Renewal within 30 days
CRM_SCORE_HIGH          = 25.0  # Renewal within 14 days
CRM_SCORE_CRIT          = 15.0  # Renewal within 7 days


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
                "crm": config.health_weight_crm / 100.0,
            }
    except Exception:
        pass
    return WEIGHTS


def _compute_usage_component(db: Session, org_id: int, customer_email: str, now: datetime) -> int:
    """
    Fetch the pre-computed usage_score from customer_usage rollup table and
    apply the bounded usage-trend penalty (trend-detection-and-health
    aspect) — health-component-only; the stored customer_usage.usage_score
    itself is never mutated here (segment_service.py's power_user rule must
    see the unpenalised score).

    Returns 50 (neutral) when:
      - The customer_usage table does not yet exist (aspect usage-rollup-and-score
        creates it later in the feature chain).
      - No rollup row exists for this customer.
      - Any other error occurs during the query.
    The 50 fallback is returned UNPENALISED — the trend penalty only ever
    applies when a real rollup row was read (AC 8).

    Contract: this function NEVER raises; it is always safe to call.
    The actual usage_score is computed by aspect `usage-rollup-and-score`.

    Args:
        now: Timestamp of the computation; not used in this function but kept
             to match the _compute_* calling convention shared across all
             component functions (all receive the same timestamp from the caller).
    """
    from sqlalchemy import text

    from src.services.usage_score_service import apply_trend_penalty

    try:
        sp = db.begin_nested()  # SAVEPOINT — isolates this read from the outer transaction
        row = db.execute(
            text(
                "SELECT usage_score, usage_trend_state FROM customer_usage "
                "WHERE organization_id = :org_id AND customer_email = :email "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            {"org_id": org_id, "email": customer_email},
        ).fetchone()
        sp.commit()
        if row is not None and row[0] is not None:
            usage_score = int(row[0])
            trend_state = row[1]
            penalised = apply_trend_penalty(usage_score, trend_state)
            return max(0, min(100, penalised))
    except Exception:
        # Table does not exist yet or any other DB error — roll back only the
        # SAVEPOINT so the outer transaction remains usable (avoids
        # PendingRollbackError on the next query in the same request).
        try:
            sp.rollback()
        except Exception:
            pass
    return 50


def _compute_crm_component(
    db: Session, org_id: int, customer_email: str, now: datetime
) -> float:
    """
    Read renewal_date from crm_enrichment for (org, email) and return a
    0-100 float encoding renewal-proximity risk (lower = more risk).

    Renewal-proximity heuristic (documented constants at module top):
      - No row / no renewal_date -> 50.0 (neutral, same as no data)
      - Renewal date already passed -> 50.0 (not actionable in v1)
      - days_to_renewal <= CRM_RENEWAL_DAYS_CRIT (7)  -> CRM_SCORE_CRIT  (15.0)
      - days_to_renewal <= CRM_RENEWAL_DAYS_HIGH (14) -> CRM_SCORE_HIGH  (25.0)
      - days_to_renewal <= CRM_RENEWAL_DAYS_WARN (30) -> CRM_SCORE_WARN  (35.0)
      - Otherwise                                     -> CRM_SCORE_NEUTRAL (50.0)

    This is a HEURISTIC, not a trained model. See module-level constants for
    threshold/score values. Operators set health_weight_crm > 0 to opt in.

    Contract: this function NEVER raises. It uses a SAVEPOINT so a missing
    crm_enrichment table cannot abort the outer SQLAlchemy transaction.

    Args:
        now: Computation timestamp (passed by caller for consistency with
             other _compute_* functions; used for days_to_renewal arithmetic).
    """
    from sqlalchemy import text
    try:
        sp = db.begin_nested()  # SAVEPOINT — isolates this read from the outer transaction
        row = db.execute(
            text(
                "SELECT renewal_date FROM crm_enrichment "
                "WHERE organization_id = :org_id AND customer_email = :email "
                "LIMIT 1"
            ),
            {"org_id": org_id, "email": customer_email},
        ).fetchone()
        sp.commit()
        if row is not None and row[0] is not None:
            renewal_date = row[0]
            # Normalize to datetime. SQLAlchemy+SQLite returns datetime objects
            # (via native_datetime mode) or ISO8601 strings. Handle both.
            if isinstance(renewal_date, str):
                # Python 3.9's date.fromisoformat() only accepts "YYYY-MM-DD";
                # datetime.fromisoformat() accepts full datetime strings.
                # Strip microseconds suffix if present, then parse.
                raw = renewal_date.strip()
                try:
                    renewal_date = datetime.fromisoformat(raw)
                except ValueError:
                    # Fallback: try parsing just the date portion
                    renewal_date = datetime.strptime(raw[:10], "%Y-%m-%d")
            elif not isinstance(renewal_date, datetime):
                # date object
                renewal_date = datetime(
                    renewal_date.year, renewal_date.month, renewal_date.day
                )
            days_to_renewal = (renewal_date - now).days
            if days_to_renewal < 0:
                return CRM_SCORE_NEUTRAL        # past renewal — not actionable in v1
            if days_to_renewal <= CRM_RENEWAL_DAYS_CRIT:
                return max(0.0, min(100.0, CRM_SCORE_CRIT))
            if days_to_renewal <= CRM_RENEWAL_DAYS_HIGH:
                return max(0.0, min(100.0, CRM_SCORE_HIGH))
            if days_to_renewal <= CRM_RENEWAL_DAYS_WARN:
                return max(0.0, min(100.0, CRM_SCORE_WARN))
    except Exception:
        # Table does not exist yet or any other DB error — roll back only the
        # SAVEPOINT so the outer transaction remains usable (avoids
        # PendingRollbackError on the next query in the same request).
        try:
            sp.rollback()
        except Exception:
            pass
    return CRM_SCORE_NEUTRAL


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

    # CRM component (0% default, opt-in): renewal-proximity risk from crm_enrichment;
    # falls back to 50.0 (neutral) when no enrichment row exists.
    crm_component = _compute_crm_component(db, org_id, customer_email, now)

    # Weighted sum using per-org configured weights (or defaults)
    weights = _get_org_weights(org_id, db)
    health_score = int(
        churn_component * weights["churn_risk"] +
        sentiment_component * weights["sentiment"] +
        resolution_component * weights["resolution"] +
        frequency_component * weights["frequency"] +
        usage_component * weights["usage"] +
        crm_component * weights["crm"]
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
        "crm_component": crm_component,
        "risk_level": risk_level,
        "feedback_count": feedback_count,
        "last_feedback_at": last_feedback,
        "customer_name": customer_name,
        "confidence_level": confidence_level,
    }


def _maybe_enqueue_writeback(
    org_id: int,
    customer_email: str,
    old_score: int,
    new_score: int,
    db: Session,
) -> None:
    """
    Enqueue a CRM health-score writeback push when the score changes
    meaningfully (>= 2 pts) and the org has an active, writeback-enabled CRM
    integration.

    push-task-trigger (Phase 3): generalized to also dispatch a Salesforce
    push, in parallel with the (unchanged) HubSpot dispatch below. The
    one-CRM guard means an org only ever has one active integration in
    practice, so at most one of the two blocks below actually enqueues
    anything for a given org.

    This function must NEVER raise: `update_customer_health` runs both in the
    backend (in-request, e.g. the CRM disconnect recompute path) and in the
    worker (analysis/sync tasks), where the backend's Celery client may not be
    importable. `get_celery_app` is imported lazily inside each try block so
    an ImportError is swallowed the same as any other enqueue failure —
    logged, never propagated.
    """
    if abs(new_score - old_score) < 2:
        return

    # --- HubSpot dispatch (unchanged) ---------------------------------------
    # Wrapped in its own nested function so a bare `return` (used to skip
    # when no/inactive/disabled integration is found) only exits this
    # provider's check, never the Salesforce check below it.
    def _dispatch_hubspot() -> None:
        try:
            from src.models.hubspot_integration import HubSpotIntegration

            integ = (
                db.query(HubSpotIntegration)
                .filter(
                    HubSpotIntegration.organization_id == org_id,
                    HubSpotIntegration.is_active.is_(True),
                    HubSpotIntegration.writeback_enabled.is_(True),
                )
                .first()
            )
            if not integ:
                return

            from src.background.celery_client import get_celery_app

            get_celery_app().send_task(
                "src.tasks.hubspot_writeback.push_health_to_hubspot",
                args=[org_id, customer_email],
            )
        except Exception as exc:
            logger.warning(
                "health_score_service: failed to enqueue HubSpot writeback for "
                "org=%s email=%s: %s",
                org_id, customer_email, exc,
            )

    _dispatch_hubspot()

    # --- Salesforce dispatch (parallel check, push-task-trigger Phase 3) ---
    def _dispatch_salesforce() -> None:
        try:
            from src.models.salesforce_integration import SalesforceIntegration

            sf_integ = (
                db.query(SalesforceIntegration)
                .filter(
                    SalesforceIntegration.organization_id == org_id,
                    SalesforceIntegration.is_active.is_(True),
                    SalesforceIntegration.writeback_enabled.is_(True),
                )
                .first()
            )
            if not sf_integ:
                return

            from src.background.celery_client import get_celery_app

            get_celery_app().send_task(
                "src.tasks.salesforce_writeback.push_health_to_salesforce",
                args=[org_id, customer_email],
            )
        except Exception as exc:
            logger.warning(
                "health_score_service: failed to enqueue Salesforce writeback for "
                "org=%s email=%s: %s",
                org_id, customer_email, exc,
            )

    _dispatch_salesforce()


def resolve_segment(
    org_id: int,
    customer_email: str,
    db: Session,
    *,
    result: dict,
    created_at: Optional[datetime],
    churn_probability,
) -> str:
    """
    Compute the customer segment slug for (org_id, customer_email).

    Builds the pure ``UsageSignals`` input (or ``None`` when no
    ``CustomerUsage`` row exists), fetches the sentiment trend direction, and
    delegates to ``segment_service.classify_segment``. Callers are
    responsible for wrapping this in a try/except — see
    ``update_customer_health`` — so a failure here never breaks the health
    upsert.
    """
    from src.models.customer_usage import CustomerUsage
    from src.services.segment_service import UsageSignals, classify_segment

    usage_row = db.query(CustomerUsage).filter(
        CustomerUsage.organization_id == org_id,
        CustomerUsage.customer_email == customer_email,
    ).first()

    usage = None
    if usage_row is not None:
        usage = UsageSignals(
            last_active_at=usage_row.last_active_at,
            active_days_30d=usage_row.active_days_30d,
            distinct_feature_count=usage_row.distinct_feature_count,
            usage_score=usage_row.usage_score,
            first_seen_at=usage_row.first_seen_at,
        )

    direction = compute_sentiment_trend(org_id, customer_email, db)["direction"]

    return classify_segment(
        health_score=result["health_score"],
        risk_level=result["risk_level"],
        churn_probability=churn_probability,
        feedback_count=result["feedback_count"],
        last_feedback_at=result["last_feedback_at"],
        created_at=created_at,
        usage=usage,
        sentiment_direction=direction,
        now=datetime.utcnow(),
    )


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
        existing.crm_component = result["crm_component"]
        existing.risk_level = result["risk_level"]
        existing.feedback_count = result["feedback_count"]
        existing.last_feedback_at = result["last_feedback_at"]
        existing.customer_name = result["customer_name"]
        existing.confidence_level = confidence_level
        existing.confidence_score = confidence
        existing.is_archived = False  # Unarchive when new feedback arrives
        existing.updated_at = datetime.utcnow()

        # Segment classification (customer-segments aspect): never break the
        # health upsert if segment resolution fails — log and leave
        # unchanged.
        try:
            existing.segment = resolve_segment(
                org_id,
                customer_email,
                db,
                result=result,
                created_at=existing.created_at,
                churn_probability=existing.churn_probability,
            )
        except Exception as _seg_exc:
            logger.warning(
                "Segment resolution failed for org=%s email=%s: %s",
                org_id, customer_email, _seg_exc,
            )

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

        # CRM writeback (writeback-task-trigger aspect): enqueue a push to
        # HubSpot when the score changes meaningfully and the org has opted
        # in. Never raises — see _maybe_enqueue_writeback docstring.
        _maybe_enqueue_writeback(
            org_id=org_id,
            customer_email=customer_email,
            old_score=old_score,
            new_score=new_score,
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
        new_customer_now = datetime.utcnow()

        # Segment classification (customer-segments aspect): a brand-new
        # customer has no churn_probability yet and created_at is "now" (so
        # the `new` rule can fire). Never break the health upsert if segment
        # resolution fails — log and leave unset (None).
        segment_value = None
        try:
            segment_value = resolve_segment(
                org_id,
                customer_email,
                db,
                result=result,
                created_at=new_customer_now,
                churn_probability=None,
            )
        except Exception as _seg_exc:
            logger.warning(
                "Segment resolution failed for org=%s email=%s: %s",
                org_id, customer_email, _seg_exc,
            )

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
            crm_component=result["crm_component"],
            feedback_count=result["feedback_count"],
            last_feedback_at=result["last_feedback_at"],
            risk_level=result["risk_level"],
            segment=segment_value,
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
            crm_component=result["crm_component"],
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
