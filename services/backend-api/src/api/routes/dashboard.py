from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.api.dependencies import get_current_org
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# Schemas
class SentimentStats(BaseModel):
    positive_count: int
    neutral_count: int
    negative_count: int
    total_count: int
    average_score: Optional[float]


class PainPoint(BaseModel):
    issue: str
    count: int
    category: Optional[str] = None
    severity: Optional[str] = None


class FeatureRequest(BaseModel):
    feature: str
    count: int
    category: Optional[str] = None
    priority: Optional[str] = None


class CategoryCount(BaseModel):
    category: str
    count: int
    severity: Optional[str] = None  # For pain points
    priority: Optional[str] = None  # For feature requests
    response_time: Optional[str] = None  # For urgent items


class TopCategory(BaseModel):
    tag: str
    count: int


class UrgentFeedback(BaseModel):
    id: int
    text: str
    sentiment_label: Optional[str]
    created_at: datetime
    category: Optional[str] = None
    response_time: Optional[str] = None


class DashboardResponse(BaseModel):
    sentiment: SentimentStats
    pain_points: List[PainPoint]
    feature_requests: List[FeatureRequest]
    top_categories: List[TopCategory]
    urgent_items: List[UrgentFeedback]
    pain_point_categories: List[CategoryCount]
    feature_request_categories: List[CategoryCount]
    urgent_categories: List[CategoryCount]
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

    # Pain points (group by extracted_issue) - include category info
    pain_points_query = base_query.filter(
        FeedbackItem.extracted_issue.isnot(None),
        FeedbackItem.sentiment_label == "negative"
    ).order_by(
        FeedbackItem.created_at.desc()
    ).limit(10)

    pain_points = [
        PainPoint(
            issue=item.extracted_issue,
            count=1,
            category=item.pain_point_category,
            severity=item.pain_point_severity
        )
        for item in pain_points_query.all()
    ]

    # Pain point categories aggregation
    pain_point_cat_query = base_query.filter(
        FeedbackItem.pain_point_category.isnot(None)
    ).with_entities(
        FeedbackItem.pain_point_category,
        FeedbackItem.pain_point_severity,
        func.count(FeedbackItem.id).label("count")
    ).group_by(
        FeedbackItem.pain_point_category,
        FeedbackItem.pain_point_severity
    ).order_by(
        func.count(FeedbackItem.id).desc()
    ).limit(12)

    pain_point_categories = [
        CategoryCount(
            category=row.pain_point_category,
            count=row.count,
            severity=row.pain_point_severity
        )
        for row in pain_point_cat_query.all()
    ]

    # Feature requests - positive feedback with feature_request_category or tags
    feature_request_items = base_query.filter(
        FeedbackItem.sentiment_label == "positive",
        FeedbackItem.tags.isnot(None)
    ).order_by(
        FeedbackItem.created_at.desc()
    ).limit(10).all()

    feature_requests = [
        FeatureRequest(
            feature=item.text[:100] + "..." if len(item.text) > 100 else item.text,
            count=1,
            category=item.feature_request_category,
            priority=item.feature_request_priority
        )
        for item in feature_request_items
    ]

    # Feature request categories aggregation
    feature_cat_query = base_query.filter(
        FeedbackItem.feature_request_category.isnot(None)
    ).with_entities(
        FeedbackItem.feature_request_category,
        FeedbackItem.feature_request_priority,
        func.count(FeedbackItem.id).label("count")
    ).group_by(
        FeedbackItem.feature_request_category,
        FeedbackItem.feature_request_priority
    ).order_by(
        func.count(FeedbackItem.id).desc()
    ).limit(10)

    feature_request_categories = [
        CategoryCount(
            category=row.feature_request_category,
            count=row.count,
            priority=row.feature_request_priority
        )
        for row in feature_cat_query.all()
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

    # Urgent items (show only last 5) - include category info
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
            created_at=item.created_at,
            category=item.urgent_category,
            response_time=item.urgent_response_time
        )
        for item in urgent_query.all()
    ]

    # Urgent categories aggregation
    urgent_cat_query = base_query.filter(
        FeedbackItem.urgent_category.isnot(None)
    ).with_entities(
        FeedbackItem.urgent_category,
        FeedbackItem.urgent_response_time,
        func.count(FeedbackItem.id).label("count")
    ).group_by(
        FeedbackItem.urgent_category,
        FeedbackItem.urgent_response_time
    ).order_by(
        func.count(FeedbackItem.id).desc()
    ).limit(10)

    urgent_categories = [
        CategoryCount(
            category=row.urgent_category,
            count=row.count,
            response_time=row.urgent_response_time
        )
        for row in urgent_cat_query.all()
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
        pain_point_categories=pain_point_categories,
        feature_request_categories=feature_request_categories,
        urgent_categories=urgent_categories,
        total_feedback=total_feedback,
        date_range=f"Last {days} days"
    )
