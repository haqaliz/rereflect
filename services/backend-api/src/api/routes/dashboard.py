from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.api.dependencies import get_current_org
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# Schemas
class SentimentStats(BaseModel):
    positive_count: int
    neutral_count: int
    negative_count: int
    total_count: int
    average_score: float | None


class PainPoint(BaseModel):
    issue: str
    count: int


class FeatureRequest(BaseModel):
    feature: str
    count: int


class TopCategory(BaseModel):
    tag: str
    count: int


class UrgentFeedback(BaseModel):
    id: int
    text: str
    sentiment_label: str | None
    created_at: datetime


class DashboardResponse(BaseModel):
    sentiment: SentimentStats
    pain_points: List[PainPoint]
    feature_requests: List[FeatureRequest]
    top_categories: List[TopCategory]
    urgent_items: List[UrgentFeedback]
    total_feedback: int
    date_range: str


# Endpoints
@router.get("/", response_model=DashboardResponse)
def get_dashboard(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get dashboard analytics for the current organization."""

    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Base query for date range
    base_query = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id,
        FeedbackItem.created_at >= start_date
    )

    # Total feedback count
    total_feedback = base_query.count()

    # Sentiment statistics
    from sqlalchemy import case
    sentiment_stats = base_query.with_entities(
        func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("positive"),
        func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neutral"),
        func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("negative"),
        func.avg(FeedbackItem.sentiment_score).label("avg_score")
    ).first()

    positive_count = int(sentiment_stats.positive or 0)
    neutral_count = int(sentiment_stats.neutral or 0)
    negative_count = int(sentiment_stats.negative or 0)
    avg_score = float(sentiment_stats.avg_score) if sentiment_stats.avg_score else None

    # Pain points (group by extracted_issue)
    pain_points_query = base_query.filter(
        FeedbackItem.extracted_issue.isnot(None),
        FeedbackItem.sentiment_label == "negative"
    ).with_entities(
        FeedbackItem.extracted_issue,
        func.count(FeedbackItem.id).label("count")
    ).group_by(
        FeedbackItem.extracted_issue
    ).order_by(
        func.count(FeedbackItem.id).desc()
    ).limit(10)

    pain_points = [
        PainPoint(issue=row.extracted_issue, count=row.count)
        for row in pain_points_query.all()
    ]

    # Feature requests - positive feedback with tags
    positive_with_tags = base_query.filter(
        FeedbackItem.sentiment_label == "positive",
        FeedbackItem.tags.isnot(None)
    ).all()

    # Count unique combinations of feedback text for feature requests
    from collections import Counter
    feature_counter = Counter()
    for item in positive_with_tags:
        if item.tags:
            # Use the first 100 chars of text as the feature description
            feature_text = item.text[:100] + "..." if len(item.text) > 100 else item.text
            feature_counter[feature_text] += 1

    feature_requests = [
        FeatureRequest(feature=feature, count=count)
        for feature, count in feature_counter.most_common(10)
    ]

    # Top categories (count tags across all feedback)
    from collections import Counter
    all_feedback_with_tags = base_query.filter(
        FeedbackItem.tags.isnot(None)
    ).all()

    tag_counter = Counter()
    for item in all_feedback_with_tags:
        if item.tags:
            tag_counter.update(item.tags)

    top_categories = [
        TopCategory(tag=tag, count=count)
        for tag, count in tag_counter.most_common(10)
    ]

    # Urgent items (show only last 5)
    urgent_query = base_query.filter(
        FeedbackItem.is_urgent == True
    ).order_by(
        FeedbackItem.created_at.desc()
    ).limit(5)

    urgent_items = [
        UrgentFeedback(
            id=item.id,
            text=item.text,
            sentiment_label=item.sentiment_label,
            created_at=item.created_at
        )
        for item in urgent_query.all()
    ]

    return DashboardResponse(
        sentiment=SentimentStats(
            positive_count=positive_count,
            neutral_count=neutral_count,
            negative_count=negative_count,
            total_count=total_feedback,
            average_score=avg_score
        ),
        pain_points=pain_points,
        feature_requests=feature_requests,
        top_categories=top_categories,
        urgent_items=urgent_items,
        total_feedback=total_feedback,
        date_range=f"Last {days} days"
    )
