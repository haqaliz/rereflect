#!/usr/bin/env python3
"""
Script to re-analyze all existing feedback items.
Use this after updating the analysis logic to apply it to existing data.
"""

import sys
import os

# Add the project to path
sys.path.insert(0, os.path.dirname(__file__))

from src.database.session import SessionLocal
from src.models.feedback import FeedbackItem

# Add analysis-engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../analysis-engine/src"))
from analyzer.sentiment import SentimentAnalyzer


def analyze_single_feedback(feedback: FeedbackItem) -> None:
    """Analyze a single feedback item."""
    try:
        sentiment_analyzer = SentimentAnalyzer()
        sentiment = sentiment_analyzer.analyze(feedback.text)

        feedback.sentiment_score = sentiment['compound']
        feedback.sentiment_label = sentiment['label']

        # Simple urgency detection based on keywords and negative sentiment
        urgent_keywords = ['urgent', 'critical', 'broken', 'crash', 'bug', 'error', 'failing', 'down', 'cannot', 'can\'t', 'won\'t', 'doesn\'t']
        text_lower = feedback.text.lower()
        has_urgent_keyword = any(keyword in text_lower for keyword in urgent_keywords)
        is_very_negative = sentiment['compound'] < -0.5

        feedback.is_urgent = has_urgent_keyword and is_very_negative

        # Extract pain points (problems, bugs, complaints)
        pain_keywords = ['bug', 'error', 'broken', 'crash', 'issue', 'problem', 'fail', 'not working', 'doesn\'t work', 'can\'t', 'cannot', 'won\'t', 'terrible', 'awful', 'slow', 'confusing', 'frustrating']
        if any(keyword in text_lower for keyword in pain_keywords) or sentiment['compound'] < -0.3:
            # Extract a short issue description from the text
            feedback.extracted_issue = feedback.text[:100] + ('...' if len(feedback.text) > 100 else '')

    except Exception as e:
        print(f"Failed to analyze feedback {feedback.id}: {str(e)}")


def main():
    """Re-analyze all feedback items."""
    db = SessionLocal()

    try:
        # Get all feedback items
        all_feedback = db.query(FeedbackItem).all()
        total = len(all_feedback)

        print(f"Found {total} feedback items to re-analyze...")

        for i, feedback in enumerate(all_feedback, 1):
            print(f"Analyzing {i}/{total}: ID={feedback.id}")
            analyze_single_feedback(feedback)

        # Commit all changes
        db.commit()
        print(f"\n✅ Successfully re-analyzed {total} feedback items!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
