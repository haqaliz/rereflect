from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.api.dependencies import get_current_org
from pydantic import BaseModel
from typing import List
import sys
import os

# Add analysis-engine to path
analysis_engine_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..", "..", "analysis-engine", "src"))
sys.path.insert(0, analysis_engine_path)

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])


# Schemas
class AnalyzeFeedbackRequest(BaseModel):
    feedback_ids: List[int]


class AnalyzeFeedbackResponse(BaseModel):
    analyzed_count: int
    message: str


# Endpoints
@router.post("/", response_model=AnalyzeFeedbackResponse)
def analyze_feedback(
    data: AnalyzeFeedbackRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Analyze feedback items using the analysis engine."""

    if not data.feedback_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No feedback IDs provided"
        )

    # Get feedback items (with multi-tenant filtering)
    feedback_items = db.query(FeedbackItem).filter(
        FeedbackItem.id.in_(data.feedback_ids),
        FeedbackItem.organization_id == current_org.id  # Multi-tenant isolation
    ).all()

    if not feedback_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback items found"
        )

    try:
        # Import analysis engine
        from analyzer import FeedbackAnalyzer, FeedbackInput, FeedbackItem as AnalyzerFeedbackItem
        from analyzer.sentiment import SentimentAnalyzer

        # Prepare data for analyzer
        analyzer_items = [
            AnalyzerFeedbackItem(
                id=str(item.id),
                text=item.text,
                date=item.created_at.isoformat(),
                source=item.source or "manual"
            )
            for item in feedback_items
        ]

        analyzer_input = FeedbackInput(feedback=analyzer_items)

        # Run analysis
        analyzer = FeedbackAnalyzer()
        result = analyzer.analyze(analyzer_input)

        # Analyze sentiment for each individual item
        sentiment_analyzer = SentimentAnalyzer()

        # Update database with results
        for item in feedback_items:
            item_id = str(item.id)

            # Get individual sentiment
            sentiment = sentiment_analyzer.analyze(item.text)
            item.sentiment_score = sentiment['compound']
            item.sentiment_label = sentiment['label']

            # Check if item is in urgent list
            urgent_ids = [u.id for u in result.urgent_feedback]
            item.is_urgent = item_id in urgent_ids

            # Find extracted issue from pain points
            for pain_point in result.common_pain_points:
                if item_id in pain_point.examples:
                    item.extracted_issue = pain_point.issue
                    break

            # Check feature requests too
            if not item.extracted_issue:
                for feature in result.feature_requests:
                    if item_id in feature.examples:
                        item.extracted_issue = feature.feature
                        break

        db.commit()

        return AnalyzeFeedbackResponse(
            analyzed_count=len(feedback_items),
            message=f"Successfully analyzed {len(feedback_items)} feedback items"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post("/batch", response_model=AnalyzeFeedbackResponse)
def analyze_all_unanalyzed(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Analyze all unanalyzed feedback for the current organization."""

    # Get all feedback without sentiment
    unanalyzed = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id,
        FeedbackItem.sentiment_label.is_(None)
    ).all()

    if not unanalyzed:
        return AnalyzeFeedbackResponse(
            analyzed_count=0,
            message="No unanalyzed feedback found"
        )

    feedback_ids = [item.id for item in unanalyzed]

    # Reuse the main analyze endpoint logic
    return analyze_feedback(
        data=AnalyzeFeedbackRequest(feedback_ids=feedback_ids),
        current_org=current_org,
        db=db
    )
