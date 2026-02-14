"""
Analysis tasks for processing customer feedback.
Migrated from APScheduler to Celery for distributed processing.
Supports LLM-powered categorization (OpenAI) with keyword fallback.
"""

import logging
from typing import List, Optional

import redis
from celery import shared_task

from src.database import get_db_session
from src.config import settings, get_redis_url
from src.openai_client import categorize_feedback

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


@shared_task
def process_unanalyzed_feedback() -> dict:
    """
    Periodic task: Process all unanalyzed feedback items.
    Runs every 30 seconds via Celery Beat.
    Uses a Redis lock to prevent concurrent execution across workers.
    Commits after each item so overlapping tasks skip already-analyzed items.

    Returns:
        dict with processing results
    """
    from src.models import FeedbackItem

    r = _get_redis()
    lock = r.lock("lock:process_unanalyzed_feedback", timeout=300, blocking=False)

    if not lock.acquire(blocking=False):
        logger.debug("process_unanalyzed_feedback already running, skipping")
        return {"status": "skipped", "processed": 0}

    try:
        with get_db_session() as db:
            # Find unanalyzed feedback
            unanalyzed = db.query(FeedbackItem).filter(
                FeedbackItem.sentiment_label == None
            ).limit(settings.analysis_batch_size).all()

            if not unanalyzed:
                logger.debug("No unanalyzed feedback found")
                return {"status": "idle", "processed": 0}

            logger.info(f"Processing {len(unanalyzed)} unanalyzed feedback items")

            success_count = 0
            failed_count = 0

            for feedback in unanalyzed:
                try:
                    _analyze_feedback_item(feedback, db)
                    db.commit()
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to analyze feedback {feedback.id}: {e}")
                    db.rollback()
                    failed_count += 1

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
        org_api_key = org.openai_api_key if org else None
        llm_result = categorize_feedback(
            text=feedback.text,
            custom_categories=custom_categories if custom_categories else None,
            org_api_key=org_api_key,
        )

    if llm_result:
        _apply_llm_result(feedback, llm_result)
    else:
        _apply_keyword_analysis(feedback)
        # Mark for LLM retry if org has AI enabled but LLM failed
        if use_llm:
            feedback.llm_analysis_pending = True


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

    feedback.llm_analyzed = True
    feedback.llm_analysis_pending = False


def _apply_keyword_analysis(feedback) -> None:
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

    # Keyword fallback: compute heuristic churn risk score
    feedback.churn_risk_score = _compute_heuristic_churn_risk(feedback)
    feedback.suggested_action = _compute_heuristic_suggestion(feedback)

    # Keyword fallback doesn't set LLM fields
    feedback.llm_analyzed = False


def _compute_heuristic_churn_risk(feedback) -> int:
    """Compute a churn risk score (0-100) using heuristics when LLM is unavailable."""
    score = 0
    text_lower = feedback.text.lower()

    # Sentiment-based scoring (0-40 points)
    if feedback.sentiment_score is not None:
        if feedback.sentiment_score < -0.7:
            score += 40
        elif feedback.sentiment_score < -0.5:
            score += 30
        elif feedback.sentiment_score < -0.3:
            score += 20
        elif feedback.sentiment_score < 0:
            score += 10

    # Urgency (0-20 points)
    if feedback.is_urgent:
        score += 20

    # Churn-signal keywords (0-25 points)
    churn_keywords = [
        'cancel', 'canceling', 'cancellation',
        'switch', 'switching', 'alternative', 'competitor',
        'leave', 'leaving', 'quit', 'done with',
        'refund', 'money back', 'waste of money',
        'unsubscribe', 'downgrade', 'not renewing',
    ]
    churn_matches = sum(1 for kw in churn_keywords if kw in text_lower)
    score += min(churn_matches * 10, 25)

    # Frustration keywords (0-15 points)
    frustration_keywords = [
        'frustrated', 'frustrating', 'terrible', 'awful', 'horrible',
        'worst', 'useless', 'waste', 'disappointed', 'unacceptable',
    ]
    frustration_matches = sum(1 for kw in frustration_keywords if kw in text_lower)
    score += min(frustration_matches * 5, 15)

    return min(score, 100)


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
                    org_api_key=org.openai_api_key,
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
