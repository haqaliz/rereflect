#!/usr/bin/env python3
"""
Re-analyze all existing feedback to extract pain points.
This is needed because the pain point extraction was added after initial analysis.
"""

import sys
import os

# Add paths
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)  # Add backend-api to path
sys.path.insert(0, os.path.join(os.path.dirname(script_dir), "analysis-engine"))  # Add analysis-engine to path

from src.database.session import SessionLocal
from src.models.feedback import FeedbackItem
from analyzer.sentiment import SentimentAnalyzer


def main():
    db = SessionLocal()
    sentiment_analyzer = SentimentAnalyzer()

    try:
        # Get ALL feedback items (even those already analyzed)
        all_feedback = db.query(FeedbackItem).all()

        print(f"Re-analyzing {len(all_feedback)} feedback items for pain points and urgency...")

        updated_count = 0
        for feedback in all_feedback:
            # Re-analyze sentiment
            sentiment = sentiment_analyzer.analyze(feedback.text)

            # Update sentiment (in case the analyzer improved)
            feedback.sentiment_score = sentiment['compound']
            feedback.sentiment_label = sentiment['label']

            # Urgency detection
            urgent_keywords = ['urgent', 'critical', 'broken', 'crash', 'bug', 'error', 'failing', 'down', 'cannot', 'can\'t', 'won\'t', 'doesn\'t']
            text_lower = feedback.text.lower()
            has_urgent_keyword = any(keyword in text_lower for keyword in urgent_keywords)
            is_very_negative = sentiment['compound'] < -0.5

            feedback.is_urgent = has_urgent_keyword and is_very_negative

            # Pain point extraction
            pain_keywords = ['bug', 'error', 'broken', 'crash', 'issue', 'problem', 'fail', 'not working', 'doesn\'t work', 'can\'t', 'cannot', 'won\'t', 'terrible', 'awful', 'slow', 'confusing', 'frustrating']
            if any(keyword in text_lower for keyword in pain_keywords) or sentiment['compound'] < -0.3:
                # Extract a short issue description from the text
                feedback.extracted_issue = feedback.text[:100] + ('...' if len(feedback.text) > 100 else '')
                updated_count += 1
            else:
                feedback.extracted_issue = None

        db.commit()
        print(f"✓ Re-analysis complete!")
        print(f"  - Total items: {len(all_feedback)}")
        print(f"  - Pain points extracted: {updated_count}")
        print(f"  - Urgent items: {sum(1 for f in all_feedback if f.is_urgent)}")

    except Exception as e:
        print(f"Error: {str(e)}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
