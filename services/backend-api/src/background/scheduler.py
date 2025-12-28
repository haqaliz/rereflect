"""
Background scheduler for periodic tasks.
Handles automatic analysis of unprocessed feedback.
"""

import sys
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging

# Add analysis-engine to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../analysis-engine/src")))

from src.database.session import SessionLocal
from src.models.feedback import FeedbackItem

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def get_sentiment_analyzer():
    """Get SentimentAnalyzer with lazy import."""
    from analyzer.sentiment import SentimentAnalyzer
    return SentimentAnalyzer()


def get_tag_extractor():
    """Get TagExtractor with lazy import."""
    from analyzer.tag_extractor import TagExtractor
    return TagExtractor()


def analyze_feedback_item(feedback: FeedbackItem, db) -> bool:
    """
    Analyze a single feedback item.
    Returns True if successful, False otherwise.
    """
    try:
        sentiment_analyzer = get_sentiment_analyzer()
        tag_extractor = get_tag_extractor()

        sentiment = sentiment_analyzer.analyze(feedback.text)
        text_lower = feedback.text.lower()

        # Override sentiment for strong negative keywords
        # VADER doesn't understand domain-specific negative words like "crash", "broken", "bug"
        strong_negative_keywords = ['crash', 'broken', 'bug', 'error', 'fail', 'cannot', 'can\'t', 'won\'t', 'doesn\'t work', 'not working', 'terrible', 'awful']
        has_strong_negative = any(keyword in text_lower for keyword in strong_negative_keywords)

        if has_strong_negative and sentiment['label'] == 'neutral':
            # Override neutral to negative when strong negative keywords are present
            feedback.sentiment_label = 'negative'
            # Keep the original score but ensure it's at least slightly negative
            feedback.sentiment_score = min(sentiment['compound'], -0.1)
        else:
            feedback.sentiment_score = sentiment['compound']
            feedback.sentiment_label = sentiment['label']

        # Simple urgency detection based on keywords and negative sentiment
        urgent_keywords = ['urgent', 'critical', 'broken', 'crash', 'bug', 'error', 'failing', 'down', 'cannot', 'can\'t', 'won\'t', 'doesn\'t']
        has_urgent_keyword = any(keyword in text_lower for keyword in urgent_keywords)
        is_very_negative = feedback.sentiment_score < -0.5

        feedback.is_urgent = has_urgent_keyword and is_very_negative

        # Extract pain points (problems, bugs, complaints)
        pain_keywords = ['bug', 'error', 'broken', 'crash', 'issue', 'problem', 'fail', 'not working', 'doesn\'t work', 'can\'t', 'cannot', 'won\'t', 'terrible', 'awful', 'slow', 'confusing', 'frustrating']
        if any(keyword in text_lower for keyword in pain_keywords) or feedback.sentiment_score < -0.3:
            # Extract a short issue description from the text
            feedback.extracted_issue = feedback.text[:100] + ('...' if len(feedback.text) > 100 else '')

        # Extract category tags
        feedback.tags = tag_extractor.extract_tags(feedback.text)

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Failed to analyze feedback {feedback.id}: {str(e)}")
        db.rollback()
        return False


def process_unanalyzed_feedback():
    """
    Background job that processes all unanalyzed feedback items.
    Runs every 30 seconds to ensure timely analysis.
    """
    db = SessionLocal()

    try:
        # Find feedback items that haven't been analyzed yet
        # (sentiment_label is None means not analyzed)
        unanalyzed = db.query(FeedbackItem).filter(
            FeedbackItem.sentiment_label == None
        ).limit(100).all()  # Process max 100 at a time

        if not unanalyzed:
            logger.debug("No unanalyzed feedback found")
            return

        logger.info(f"Processing {len(unanalyzed)} unanalyzed feedback items...")

        success_count = 0
        failed_count = 0

        for feedback in unanalyzed:
            if analyze_feedback_item(feedback, db):
                success_count += 1
            else:
                failed_count += 1

        logger.info(f"Analysis complete: {success_count} successful, {failed_count} failed")

    except Exception as e:
        logger.error(f"Error in background analysis job: {str(e)}")
        db.rollback()

    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already running")
        return scheduler

    scheduler = BackgroundScheduler()

    # Add job to process unanalyzed feedback every 30 seconds
    scheduler.add_job(
        func=process_unanalyzed_feedback,
        trigger=IntervalTrigger(seconds=30),
        id='analyze_feedback',
        name='Process unanalyzed feedback',
        replace_existing=True,
        max_instances=1  # Ensure only one instance runs at a time
    )

    scheduler.start()
    logger.info("Background scheduler started - processing feedback every 30 seconds")

    return scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("Background scheduler stopped")


def get_scheduler_status():
    """Get the current status of the scheduler."""
    if scheduler is None:
        return {
            "running": False,
            "jobs": []
        }

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None
        })

    return {
        "running": scheduler.running,
        "jobs": jobs
    }
