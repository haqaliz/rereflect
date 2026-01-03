"""
Analysis tasks for processing customer feedback.
Migrated from APScheduler to Celery for distributed processing.
"""

import logging
from typing import List, Optional

from celery import shared_task

from src.database import get_db_session
from src.config import settings

logger = logging.getLogger(__name__)


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
            _analyze_feedback_item(feedback)
            db.commit()
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
                _analyze_feedback_item(feedback)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to analyze feedback {feedback.id}: {e}")
                failed_count += 1

        db.commit()

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
    Replaces the APScheduler job.

    Returns:
        dict with processing results
    """
    from src.models import FeedbackItem

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
                _analyze_feedback_item(feedback)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to analyze feedback {feedback.id}: {e}")
                failed_count += 1

        db.commit()

        logger.info(f"Analysis complete: {success_count} successful, {failed_count} failed")

        return {
            "status": "complete",
            "processed": success_count,
            "failed": failed_count,
        }


def _analyze_feedback_item(feedback) -> None:
    """
    Core analysis logic for a single feedback item.
    Updates the feedback object in place.

    Args:
        feedback: FeedbackItem ORM object to analyze
    """
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
