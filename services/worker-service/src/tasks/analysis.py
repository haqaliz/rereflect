"""
Analysis tasks for processing customer feedback.
Migrated from APScheduler to Celery for distributed processing.
Supports LLM-powered categorization (OpenAI) with keyword fallback.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import redis
from celery import shared_task

from src.database import get_db_session
from src.config import settings, get_redis_url
from src.llm_client import categorize_feedback

# Redis client for distributed task locking
_redis_client = None


def _get_redis():
    """Get or create Redis client for task locking."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(get_redis_url(0))
    return _redis_client

logger = logging.getLogger(__name__)

# Redis client for cache invalidation (DB 2 = application cache)
_redis_cache_client = None


def _get_cache_redis():
    """Get or create Redis client for cache invalidation."""
    global _redis_cache_client
    if _redis_cache_client is None:
        _redis_cache_client = redis.from_url(get_redis_url(2))
    return _redis_cache_client


def _invalidate_org_cache(org_id: int):
    """Invalidate dashboard and analytics cache for an organization."""
    try:
        r = _get_cache_redis()
        for key in r.scan_iter(match=f"dashboard:{org_id}:*"):
            r.delete(key)
        for key in r.scan_iter(match=f"analytics:{org_id}:*"):
            r.delete(key)
    except Exception as e:
        logger.warning(f"Cache invalidation failed for org {org_id}: {e}")


def get_sentiment_analyzer():
    """Get SentimentAnalyzer with lazy import."""
    from analyzer.sentiment import SentimentAnalyzer
    return SentimentAnalyzer()


def get_tag_extractor():
    """Get TagExtractor with lazy import."""
    from analyzer.tag_extractor import TagExtractor
    return TagExtractor()


def get_categorizers():
    """Get categorizers with lazy import."""
    from analyzer.categorizer import PainPointCategorizer, FeatureRequestCategorizer, UrgentCategorizer
    return PainPointCategorizer(), FeatureRequestCategorizer(), UrgentCategorizer()


def is_feature_request(text: str) -> bool:
    """Check if text contains a feature request."""
    text_lower = text.lower()
    request_patterns = [
        'wish', 'hope', 'want', 'would like', 'would love',
        'please add', 'please include', 'need', 'require',
        'could you add', 'can you add', 'should add', 'should have',
        'missing', 'no way to', "doesn't have", 'feature request'
    ]
    return any(pattern in text_lower for pattern in request_patterns)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def analyze_single_feedback(self, feedback_id: int) -> dict:
    """
    Analyze a single feedback item.
    Called immediately when new feedback is created.

    Args:
        feedback_id: ID of the feedback item to analyze

    Returns:
        dict with status and analysis results
    """
    # Import here to avoid circular imports
    from src.models import FeedbackItem

    with get_db_session() as db:
        feedback = db.query(FeedbackItem).filter(FeedbackItem.id == feedback_id).first()

        if not feedback:
            logger.warning(f"Feedback {feedback_id} not found")
            return {"status": "not_found", "feedback_id": feedback_id}

        if feedback.sentiment_label is not None:
            logger.info(f"Feedback {feedback_id} already analyzed")
            return {"status": "already_analyzed", "feedback_id": feedback_id}

        try:
            _analyze_feedback_item(feedback, db)
            db.commit()

            # Invalidate dashboard/analytics cache after analysis
            _invalidate_org_cache(feedback.organization_id)

            # Auto-assign after analysis (so category-based rules can match)
            org_id = feedback.organization_id
            from src.tasks.workflow import auto_assign_feedback_batch
            auto_assign_feedback_batch.delay(org_id, [feedback_id])

            logger.info(f"Successfully analyzed feedback {feedback_id}")
            return {
                "status": "success",
                "feedback_id": feedback_id,
                "sentiment": feedback.sentiment_label,
                "is_urgent": feedback.is_urgent,
            }
        except Exception as e:
            logger.error(f"Failed to analyze feedback {feedback_id}: {e}")
            raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def analyze_feedback_batch(self, org_id: int, feedback_ids: List[int]) -> dict:
    """
    Analyze a batch of feedback items.
    Used for CSV imports and bulk operations.

    Args:
        org_id: Organization ID (for security/isolation)
        feedback_ids: List of feedback item IDs to analyze

    Returns:
        dict with success/failure counts
    """
    from src.models import FeedbackItem

    with get_db_session() as db:
        # Verify organization ownership
        feedback_items = db.query(FeedbackItem).filter(
            FeedbackItem.id.in_(feedback_ids),
            FeedbackItem.organization_id == org_id,
            FeedbackItem.sentiment_label == None,  # Only unanalyzed
        ).all()

        if not feedback_items:
            return {"status": "no_items", "analyzed": 0, "failed": 0}

        success_count = 0
        failed_count = 0

        for feedback in feedback_items:
            try:
                _analyze_feedback_item(feedback, db)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to analyze feedback {feedback.id}: {e}")
                failed_count += 1

        db.commit()

        # Invalidate dashboard/analytics cache after batch analysis
        if success_count > 0:
            _invalidate_org_cache(org_id)

        # Auto-assign after analysis (so category-based rules can match)
        if success_count > 0:
            from src.tasks.workflow import auto_assign_feedback_batch
            auto_assign_feedback_batch.delay(org_id, feedback_ids)

        return {
            "status": "complete",
            "analyzed": success_count,
            "failed": failed_count,
            "total": len(feedback_ids),
        }


def _analyze_single_by_id(feedback_id: int) -> dict:
    """
    Analyze a single feedback item by ID in its own DB session.
    Designed to run inside a thread pool — each thread gets an independent session.
    """
    with get_db_session() as db:
        from src.models import FeedbackItem

        feedback = db.query(FeedbackItem).filter(
            FeedbackItem.id == feedback_id,
            FeedbackItem.sentiment_label == None,
        ).first()

        if not feedback:
            return {"id": feedback_id, "status": "skipped"}

        try:
            _analyze_feedback_item(feedback, db)
            db.commit()
            return {"id": feedback_id, "status": "success"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to analyze feedback {feedback_id}: {e}")
            return {"id": feedback_id, "status": "failed", "error": str(e)}


# Max parallel OpenAI calls (keep reasonable to avoid rate limits)
ANALYSIS_WORKERS = 8


@shared_task
def process_unanalyzed_feedback() -> dict:
    """
    Periodic task: Process all unanalyzed feedback items.
    Runs every 30 seconds via Celery Beat.
    Uses a Redis lock to prevent concurrent execution across workers.
    Processes items in parallel using a thread pool for ~5-8x speedup.

    Returns:
        dict with processing results
    """
    from src.models import FeedbackItem

    r = _get_redis()
    lock = r.lock("lock:process_unanalyzed_feedback", timeout=600, blocking=False)

    if not lock.acquire(blocking=False):
        logger.debug("process_unanalyzed_feedback already running, skipping")
        return {"status": "skipped", "processed": 0}

    try:
        # Collect IDs in main thread, then process in parallel
        with get_db_session() as db:
            feedback_ids = [
                row.id for row in db.query(FeedbackItem.id).filter(
                    FeedbackItem.sentiment_label == None
                ).limit(settings.analysis_batch_size).all()
            ]

        if not feedback_ids:
            logger.debug("No unanalyzed feedback found")
            return {"status": "idle", "processed": 0}

        logger.info(f"Processing {len(feedback_ids)} unanalyzed feedback items ({ANALYSIS_WORKERS} workers)")

        success_count = 0
        failed_count = 0

        with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as executor:
            futures = {
                executor.submit(_analyze_single_by_id, fid): fid
                for fid in feedback_ids
            }

            for future in as_completed(futures):
                result = future.result()
                if result["status"] == "success":
                    success_count += 1
                elif result["status"] == "failed":
                    failed_count += 1

        # Invalidate cache for affected orgs
        if success_count > 0:
            with get_db_session() as db:
                org_ids = db.query(FeedbackItem.organization_id).filter(
                    FeedbackItem.id.in_(feedback_ids),
                ).distinct().all()
                for (org_id,) in org_ids:
                    _invalidate_org_cache(org_id)

        logger.info(f"Analysis complete: {success_count} successful, {failed_count} failed")

        return {
            "status": "complete",
            "processed": success_count,
            "failed": failed_count,
        }
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass


def _analyze_feedback_item(feedback, db=None) -> None:
    """
    Core analysis logic for a single feedback item.
    Tries LLM-powered analysis first, falls back to keyword-based.
    Updates the feedback object in place.

    Args:
        feedback: FeedbackItem ORM object to analyze
        db: SQLAlchemy session (needed for org lookup and custom categories)
    """
    from src.models import Organization, CustomCategory

    # Check if org has AI analysis enabled
    org = None
    use_llm = False
    custom_categories = []

    if db is not None:
        org = db.query(Organization).filter(Organization.id == feedback.organization_id).first()
        if org and org.ai_analysis_enabled:
            use_llm = True
            # Fetch active custom categories for this org
            custom_cats = db.query(CustomCategory).filter(
                CustomCategory.organization_id == feedback.organization_id,
                CustomCategory.is_active == True,
            ).all()
            custom_categories = [
                {"name": c.name, "category_type": c.category_type}
                for c in custom_cats
            ]

    llm_result = None
    if use_llm:
        llm_result = categorize_feedback(
            text=feedback.text,
            custom_categories=custom_categories if custom_categories else None,
            org_id=feedback.organization_id,
            db=db,
        )

    if llm_result:
        _apply_llm_result(feedback, llm_result)
        # Also compute heuristic factors for explainability (LLM doesn't return factor breakdown)
        _, churn_factors = _compute_heuristic_churn_risk(feedback, db)
        feedback.churn_risk_factors = churn_factors
    else:
        _apply_keyword_analysis(feedback, db)
        # Mark for LLM retry if org has AI enabled but LLM failed
        if use_llm:
            feedback.llm_analysis_pending = True

    # Extract and set customer_email from source_metadata
    if not feedback.customer_email:
        email = _extract_customer_email(feedback)
        if email:
            feedback.customer_email = email

    # Update customer health score after analysis
    if feedback.customer_email and db is not None:
        try:
            from src.services.health_score_service import update_customer_health
            update_customer_health(feedback.organization_id, feedback.customer_email, db)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to update customer health for {feedback.customer_email}: {e}")


def _apply_llm_result(feedback, result: dict) -> None:
    """Apply LLM categorization result to a feedback item."""
    feedback.sentiment_label = result.get("sentiment_label", "neutral")
    feedback.sentiment_score = result.get("sentiment_score", 0.0)
    feedback.is_urgent = result.get("is_urgent", False)

    feedback.pain_point_category = result.get("pain_point_category")
    feedback.pain_point_severity = result.get("pain_point_severity")
    if feedback.pain_point_category:
        feedback.extracted_issue = feedback.text[:100] + ('...' if len(feedback.text) > 100 else '')
        feedback.pain_point_text = feedback.text[:200]

    feedback.feature_request_category = result.get("feature_request_category")
    feedback.feature_request_priority = result.get("feature_request_priority")
    if feedback.feature_request_category:
        feedback.feature_request_text = feedback.text[:200]

    feedback.urgent_category = result.get("urgent_category")
    feedback.urgent_response_time = result.get("urgent_response_time")

    feedback.categorization_confidence = result.get("confidence", 0.5)
    feedback.tags = result.get("tags", [])
    feedback.churn_risk_score = result.get("churn_risk_score", 0)
    feedback.suggested_action = result.get("suggested_action")

    # Store which LLM provider/model was used
    feedback.llm_provider = result.get("_llm_provider")
    feedback.llm_model = result.get("_llm_model")

    feedback.llm_analyzed = True
    feedback.llm_analysis_pending = False


def _apply_keyword_analysis(feedback, db=None) -> None:
    """Apply traditional keyword-based analysis to a feedback item (fallback)."""
    sentiment_analyzer = get_sentiment_analyzer()
    tag_extractor = get_tag_extractor()
    pain_categorizer, feature_categorizer, urgent_categorizer = get_categorizers()

    # Sentiment analysis
    sentiment = sentiment_analyzer.analyze(feedback.text)
    text_lower = feedback.text.lower()

    # Override sentiment for strong negative keywords
    strong_negative_keywords = [
        'crash', 'broken', 'bug', 'error', 'fail', 'cannot', "can't",
        "won't", "doesn't work", 'not working', 'terrible', 'awful'
    ]
    has_strong_negative = any(keyword in text_lower for keyword in strong_negative_keywords)

    if has_strong_negative and sentiment['label'] == 'neutral':
        feedback.sentiment_label = 'negative'
        feedback.sentiment_score = min(sentiment['compound'], -0.1)
    else:
        feedback.sentiment_score = sentiment['compound']
        feedback.sentiment_label = sentiment['label']

    # Urgency detection
    urgent_keywords = [
        'urgent', 'critical', 'broken', 'crash', 'bug', 'error',
        'failing', 'down', 'cannot', "can't", "won't", "doesn't"
    ]
    has_urgent_keyword = any(keyword in text_lower for keyword in urgent_keywords)
    is_very_negative = feedback.sentiment_score < -0.5

    feedback.is_urgent = has_urgent_keyword and is_very_negative

    # Pain point extraction
    pain_keywords = [
        'bug', 'error', 'broken', 'crash', 'issue', 'problem', 'fail',
        'not working', "doesn't work", "can't", 'cannot', "won't",
        'terrible', 'awful', 'slow', 'confusing', 'frustrating'
    ]
    is_pain_point = any(keyword in text_lower for keyword in pain_keywords) or feedback.sentiment_score < -0.3

    if is_pain_point:
        feedback.extracted_issue = feedback.text[:100] + ('...' if len(feedback.text) > 100 else '')
        pain_result = pain_categorizer.categorize(feedback.text)
        feedback.pain_point_category = pain_result.category
        feedback.pain_point_severity = pain_result.level
        feedback.pain_point_text = pain_result.text
        feedback.categorization_confidence = pain_result.confidence

    # Feature request detection
    if is_feature_request(feedback.text):
        feature_result = feature_categorizer.categorize(feedback.text)
        feedback.feature_request_category = feature_result.category
        feedback.feature_request_priority = feature_result.level
        feedback.feature_request_text = feature_result.text
        if feedback.categorization_confidence is None or feature_result.confidence > feedback.categorization_confidence:
            feedback.categorization_confidence = feature_result.confidence

    # Urgent feedback categorization
    if feedback.is_urgent:
        urgent_result = urgent_categorizer.categorize(feedback.text, sentiment_score=feedback.sentiment_score)
        feedback.urgent_category = urgent_result.category
        feedback.urgent_response_time = urgent_result.level
        if feedback.categorization_confidence is None or urgent_result.confidence > feedback.categorization_confidence:
            feedback.categorization_confidence = urgent_result.confidence

    # Tag extraction
    feedback.tags = tag_extractor.extract_tags(feedback.text)

    # Keyword fallback: compute heuristic churn risk score (9-factor with db)
    churn_score, churn_factors = _compute_heuristic_churn_risk(feedback, db)
    feedback.churn_risk_score = churn_score
    feedback.churn_risk_factors = churn_factors
    feedback.suggested_action = _compute_heuristic_suggestion(feedback)

    # Keyword fallback doesn't set LLM fields
    feedback.llm_analyzed = False


def _extract_customer_email(feedback) -> Optional[str]:
    """Extract customer email from source_metadata."""
    if feedback.customer_email:
        return feedback.customer_email
    meta = feedback.source_metadata
    if not meta or not isinstance(meta, dict):
        return None
    for key in ['author_email', 'email', 'sender_email', 'from_email', 'user_email']:
        val = meta.get(key)
        if val and isinstance(val, str) and '@' in val:
            return val.lower().strip()
    return None


def _compute_heuristic_churn_risk(feedback, db=None):
    """
    Compute a churn risk score (0-100) using 9-factor heuristics.
    Original 4 factors (50pts) + 5 new customer-level factors (50pts).
    New factors require customer_email + db session; graceful fallback to 4-factor.

    Returns:
        Tuple[int, Dict]: (composite_score, factors_dict) where factors_dict contains
        per-factor breakdown with score, max, and label for each of the 9 factors.
    """
    from datetime import timedelta
    from sqlalchemy import func as sa_func

    text_lower = feedback.text.lower()

    # Initialize all 9 factor scores and labels
    sentiment_score_pts = 0
    sentiment_label = "Neutral/positive sentiment"

    urgency_score_pts = 0
    urgency_label = "Not urgent"

    churn_keywords_score_pts = 0
    churn_keywords_label = "No churn keywords"

    frustration_score_pts = 0
    frustration_label = "No frustration keywords"

    # Customer-level factors — defaults (no db or no email)
    sentiment_trend_score_pts = 0
    sentiment_trend_label = "Insufficient data for trend"

    frequency_score_pts = 0
    frequency_label = "Normal frequency"

    resolution_score_pts = 0
    resolution_label = "Insufficient resolution data"

    pain_score_pts = 0
    pain_label = "No critical pain points"

    feature_density_score_pts = 0
    feature_density_label = "Low feature request ratio"

    # --- Original 4 factors (50 pts) ---

    # Sentiment (0-15 pts)
    if feedback.sentiment_score is not None:
        if feedback.sentiment_score < -0.5:
            sentiment_score_pts = 15
            sentiment_label = "Very negative sentiment"
        elif feedback.sentiment_score < -0.2:
            sentiment_score_pts = 10
            sentiment_label = "Moderately negative sentiment"
        elif feedback.sentiment_score < 0:
            sentiment_score_pts = 5
            sentiment_label = "Slightly negative sentiment"
        else:
            sentiment_score_pts = 0
            sentiment_label = "Neutral/positive sentiment"

    # Urgency (0-10 pts)
    if feedback.is_urgent:
        urgency_score_pts = 10
        urgency_label = "Marked as urgent"

    # Churn keywords (0-15 pts)
    churn_keywords = [
        'cancel', 'canceling', 'cancellation',
        'switch', 'switching', 'alternative', 'competitor',
        'leave', 'leaving', 'quit', 'done with',
        'refund', 'money back', 'waste of money',
        'unsubscribe', 'downgrade', 'not renewing',
    ]
    churn_matches = sum(1 for kw in churn_keywords if kw in text_lower)
    churn_keywords_score_pts = min(churn_matches * 5, 15)
    if churn_matches > 0:
        matched_kws = [kw for kw in churn_keywords if kw in text_lower]
        sample = ', '.join(matched_kws[:3])
        churn_keywords_label = f"{churn_matches} churn keyword{'s' if churn_matches != 1 else ''} found: {sample}"
    else:
        churn_keywords_label = "No churn keywords"

    # Frustration keywords (0-10 pts)
    frustration_keywords = [
        'frustrated', 'frustrating', 'terrible', 'awful', 'horrible',
        'worst', 'useless', 'waste', 'disappointed', 'unacceptable',
    ]
    frustration_matches = sum(1 for kw in frustration_keywords if kw in text_lower)
    frustration_score_pts = min(frustration_matches * 5, 10)
    if frustration_matches > 0:
        matched_fkws = [kw for kw in frustration_keywords if kw in text_lower]
        sample_f = ', '.join(matched_fkws[:3])
        frustration_label = f"{frustration_matches} frustration keyword{'s' if frustration_matches != 1 else ''}: {sample_f}"
    else:
        frustration_label = "No frustration keywords"

    # --- New 5 factors (50 pts) — require customer_email + db ---
    customer_email = getattr(feedback, 'customer_email', None)
    if customer_email and db is not None:
        from src.models import FeedbackItem
        from datetime import datetime
        now = datetime.utcnow()
        org_id = feedback.organization_id

        # Sentiment trend (0-15 pts) — declining over last 5 feedbacks
        try:
            recent_scores = db.query(FeedbackItem.sentiment_score).filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
                FeedbackItem.sentiment_score.isnot(None),
                FeedbackItem.id != feedback.id,
            ).order_by(FeedbackItem.created_at.desc()).limit(5).all()

            if len(recent_scores) >= 2:
                scores_list = [r.sentiment_score for r in recent_scores]
                if scores_list[0] < scores_list[-1]:
                    decline = scores_list[-1] - scores_list[0]
                    if decline > 0.5:
                        sentiment_trend_score_pts = 15
                        sentiment_trend_label = f"Sentiment declining sharply (-{decline:.1f})"
                    elif decline > 0.3:
                        sentiment_trend_score_pts = 10
                        sentiment_trend_label = f"Sentiment declining moderately (-{decline:.1f})"
                    elif decline > 0.1:
                        sentiment_trend_score_pts = 5
                        sentiment_trend_label = f"Sentiment declining slightly (-{decline:.1f})"
                    else:
                        sentiment_trend_label = "Stable sentiment trend"
                else:
                    sentiment_trend_label = "Stable sentiment trend"
            else:
                sentiment_trend_label = "Insufficient data for trend"
        except Exception:
            pass

        # Feedback frequency (0-10 pts) — more complaints recently
        try:
            last_7d = db.query(sa_func.count(FeedbackItem.id)).filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
                FeedbackItem.created_at >= now - timedelta(days=7),
            ).scalar() or 0

            last_30d = db.query(sa_func.count(FeedbackItem.id)).filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
                FeedbackItem.created_at >= now - timedelta(days=30),
            ).scalar() or 0

            avg_weekly = (last_30d / 4.0) if last_30d > 0 else 0
            if avg_weekly > 0 and last_7d > avg_weekly * 2:
                frequency_score_pts = 10
                frequency_label = f"Complaint frequency spiking ({last_7d} this week vs {avg_weekly:.1f} avg)"
            elif avg_weekly > 0 and last_7d > avg_weekly * 1.5:
                frequency_score_pts = 5
                frequency_label = f"Complaint frequency increasing ({last_7d} this week vs {avg_weekly:.1f} avg)"
            else:
                frequency_label = "Normal frequency"
        except Exception:
            pass

        # Resolution time (0-10 pts) — slow resolution
        try:
            from src.models.feedback_workflow_event import FeedbackWorkflowEvent
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

            if resolved_events:
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
                if count > 0:
                    avg_days = total_days / count
                    if avg_days > 7:
                        resolution_score_pts = 10
                        resolution_label = f"Average resolution > 7 days ({avg_days:.1f} days avg)"
                    elif avg_days > 3:
                        resolution_score_pts = 5
                        resolution_label = f"Average resolution > 3 days ({avg_days:.1f} days avg)"
                    else:
                        resolution_label = f"Resolved within {avg_days:.1f} days avg"
            else:
                resolution_label = "No resolved issues in 60 days"
        except Exception:
            pass

        # Pain point severity (0-10 pts)
        try:
            critical_count = db.query(sa_func.count(FeedbackItem.id)).filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
                FeedbackItem.pain_point_severity.in_(["critical", "major"]),
                FeedbackItem.created_at >= now - timedelta(days=30),
            ).scalar() or 0
            if critical_count >= 3:
                pain_score_pts = 10
                pain_label = f"{critical_count} critical pain points in 30 days"
            elif critical_count >= 1:
                pain_score_pts = 5
                pain_label = f"{critical_count} critical pain point{'s' if critical_count != 1 else ''} in 30 days"
            else:
                pain_label = "No critical pain points"
        except Exception:
            pass

        # Feature request density (0-5 pts)
        try:
            total_30d = db.query(sa_func.count(FeedbackItem.id)).filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
                FeedbackItem.created_at >= now - timedelta(days=30),
            ).scalar() or 0

            feature_count = db.query(sa_func.count(FeedbackItem.id)).filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
                FeedbackItem.feature_request_category.isnot(None),
                FeedbackItem.created_at >= now - timedelta(days=30),
            ).scalar() or 0

            if total_30d > 0 and (feature_count / total_30d) > 0.5:
                feature_density_score_pts = 5
                pct = int((feature_count / total_30d) * 100)
                feature_density_label = f"High feature request ratio ({pct}%)"
            else:
                feature_density_label = "Low feature request ratio"
        except Exception:
            pass

    # Build factors dict
    factors = {
        "sentiment": {"score": sentiment_score_pts, "max": 15, "label": sentiment_label},
        "churn_keywords": {"score": churn_keywords_score_pts, "max": 15, "label": churn_keywords_label},
        "frustration_keywords": {"score": frustration_score_pts, "max": 10, "label": frustration_label},
        "urgency": {"score": urgency_score_pts, "max": 10, "label": urgency_label},
        "sentiment_trend": {"score": sentiment_trend_score_pts, "max": 15, "label": sentiment_trend_label},
        "feedback_frequency": {"score": frequency_score_pts, "max": 10, "label": frequency_label},
        "resolution_time": {"score": resolution_score_pts, "max": 10, "label": resolution_label},
        "pain_severity": {"score": pain_score_pts, "max": 10, "label": pain_label},
        "feature_density": {"score": feature_density_score_pts, "max": 5, "label": feature_density_label},
    }

    total = sum(v["score"] for v in factors.values())
    return min(total, 100), factors


def _compute_heuristic_suggestion(feedback) -> Optional[str]:
    """Generate a simple suggested action based on heuristics."""
    if not feedback.churn_risk_score or feedback.churn_risk_score < 40:
        return None

    if feedback.churn_risk_score >= 70:
        if feedback.is_urgent:
            return "High churn risk with urgent issue. Prioritize immediate outreach to understand and resolve the customer's concern."
        return "High churn risk detected. Consider proactive outreach to address the customer's frustration before they leave."

    return "Moderate churn risk. Monitor this customer and address their feedback in the next sprint."


@shared_task
def retry_llm_analysis() -> dict:
    """
    Periodic task: Retry LLM analysis for items that got keyword fallback.
    Runs every 5 minutes via Celery Beat.
    Uses a Redis lock to prevent concurrent execution across workers.

    Returns:
        dict with retry results
    """
    from src.models import FeedbackItem, Organization, CustomCategory

    r = _get_redis()
    lock = r.lock("lock:retry_llm_analysis", timeout=600, blocking=False)

    if not lock.acquire(blocking=False):
        logger.debug("retry_llm_analysis already running, skipping")
        return {"status": "skipped", "retried": 0}

    try:
        with get_db_session() as db:
            pending = db.query(FeedbackItem).filter(
                FeedbackItem.llm_analysis_pending == True,
            ).limit(50).all()

            if not pending:
                return {"status": "idle", "retried": 0}

            logger.info(f"Retrying LLM analysis for {len(pending)} items")

            success_count = 0
            failed_count = 0

            # Group by org to minimize duplicate lookups
            org_cache = {}
            cat_cache = {}

            for feedback in pending:
                org_id = feedback.organization_id

                if org_id not in org_cache:
                    org_cache[org_id] = db.query(Organization).filter(
                        Organization.id == org_id
                    ).first()
                    custom_cats = db.query(CustomCategory).filter(
                        CustomCategory.organization_id == org_id,
                        CustomCategory.is_active == True,
                    ).all()
                    cat_cache[org_id] = [
                        {"name": c.name, "category_type": c.category_type}
                        for c in custom_cats
                    ]

                org = org_cache[org_id]
                if not org or not org.ai_analysis_enabled:
                    feedback.llm_analysis_pending = False
                    db.commit()
                    continue

                llm_result = categorize_feedback(
                    text=feedback.text,
                    custom_categories=cat_cache[org_id] if cat_cache[org_id] else None,
                    org_id=org_id,
                    db=db,
                )

                if llm_result:
                    _apply_llm_result(feedback, llm_result)
                    success_count += 1
                else:
                    failed_count += 1

                db.commit()

            logger.info(f"LLM retry: {success_count} upgraded, {failed_count} still pending")

            return {
                "status": "complete",
                "retried": success_count,
                "failed": failed_count,
            }
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass
