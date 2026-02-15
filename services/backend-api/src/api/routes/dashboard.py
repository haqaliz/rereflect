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
    is_urgent: bool = True
    category: Optional[str] = None
    response_time: Optional[str] = None


class ChurnRiskSummary(BaseModel):
    high_count: int  # score > 70
    medium_count: int  # score 40-70
    low_count: int  # score < 40
    total_at_risk: int  # high + medium


class ChurnRiskItem(BaseModel):
    id: int
    text: str
    churn_risk_score: int
    sentiment_label: Optional[str] = None
    suggested_action: Optional[str] = None
    created_at: datetime


class CustomerHealthSummary(BaseModel):
    customer_email: str
    customer_name: Optional[str] = None
    health_score: int
    risk_level: str
    feedback_count: int
    last_feedback_at: Optional[datetime] = None
    churn_risk_component: int
    sentiment_component: int
    resolution_component: int
    frequency_component: int
    llm_analysis: Optional[str] = None
    llm_analyzed_at: Optional[datetime] = None


class DashboardResponse(BaseModel):
    sentiment: SentimentStats
    pain_points: List[PainPoint]
    feature_requests: List[FeatureRequest]
    top_categories: List[TopCategory]
    urgent_items: List[UrgentFeedback]
    pain_point_categories: List[CategoryCount]
    feature_request_categories: List[CategoryCount]
    urgent_categories: List[CategoryCount]
    churn_risk_summary: ChurnRiskSummary
    top_churn_risks: List[ChurnRiskItem]
    at_risk_customers: List[CustomerHealthSummary]
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
    from src.services.cache_service import cache_get, cache_set

    cache_key = f"dashboard:{current_org.id}:{days}"
    cached = cache_get(cache_key)
    if cached:
        return cached

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
    # Use SQL aggregation where possible, fall back to Python for non-PostgreSQL
    top_categories = []
    try:
        tag_subquery = db.query(
            func.json_array_elements_text(FeedbackItem.tags).label('tag'),
        ).filter(
            FeedbackItem.organization_id == current_org.id,
            FeedbackItem.created_at >= start_date,
            FeedbackItem.tags.isnot(None),
        ).subquery()

        tag_rows = db.query(
            tag_subquery.c.tag,
            func.count().label('cnt'),
        ).group_by(
            tag_subquery.c.tag,
        ).order_by(
            func.count().desc(),
        ).limit(10).all()

        top_categories = [
            TopCategory(tag=row.tag, count=row.cnt)
            for row in tag_rows
        ]
    except Exception:
        db.rollback()
        # Fallback for non-PostgreSQL databases (e.g., SQLite in tests)
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
            is_urgent=item.is_urgent,
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

    # Churn risk summary
    churn_stats = base_query.filter(
        FeedbackItem.churn_risk_score.isnot(None)
    ).with_entities(
        func.sum(case((FeedbackItem.churn_risk_score > 70, 1), else_=0)).label("high"),
        func.sum(case((FeedbackItem.churn_risk_score.between(40, 70), 1), else_=0)).label("medium"),
        func.sum(case((FeedbackItem.churn_risk_score < 40, 1), else_=0)).label("low"),
    ).first()

    high_count = int(churn_stats.high or 0) if churn_stats else 0
    medium_count = int(churn_stats.medium or 0) if churn_stats else 0
    low_count = int(churn_stats.low or 0) if churn_stats else 0

    churn_risk_summary = ChurnRiskSummary(
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        total_at_risk=high_count + medium_count,
    )

    # Top 5 highest churn risk items
    top_churn_query = base_query.filter(
        FeedbackItem.churn_risk_score.isnot(None),
        FeedbackItem.churn_risk_score > 0,
    ).order_by(
        FeedbackItem.churn_risk_score.desc()
    ).limit(5)

    top_churn_risks = [
        ChurnRiskItem(
            id=item.id,
            text=item.text,
            churn_risk_score=item.churn_risk_score,
            sentiment_label=item.sentiment_label,
            suggested_action=item.suggested_action,
            created_at=item.created_at,
        )
        for item in top_churn_query.all()
    ]

    # At-risk customers (top 5 lowest health scores) — Pro+ only
    from src.config.plans import has_feature
    at_risk_customers = []
    if has_feature(current_org.plan or "free", "customer_health_scores"):
        from src.models.customer_health import CustomerHealth
        at_risk_query = db.query(CustomerHealth).filter(
            CustomerHealth.organization_id == current_org.id,
        ).order_by(CustomerHealth.health_score.asc()).limit(5).all()

        at_risk_customers = [
            CustomerHealthSummary(
                customer_email=c.customer_email,
                customer_name=c.customer_name,
                health_score=c.health_score,
                risk_level=c.risk_level,
                feedback_count=c.feedback_count,
                last_feedback_at=c.last_feedback_at,
                churn_risk_component=c.churn_risk_component,
                sentiment_component=c.sentiment_component,
                resolution_component=c.resolution_component,
                frequency_component=c.frequency_component,
                llm_analysis=c.llm_analysis,
                llm_analyzed_at=c.llm_analyzed_at,
            )
            for c in at_risk_query
        ]

    result = DashboardResponse(
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
        churn_risk_summary=churn_risk_summary,
        top_churn_risks=top_churn_risks,
        at_risk_customers=at_risk_customers,
        total_feedback=total_feedback,
        date_range=f"Last {days} days"
    )

    cache_set(cache_key, result.dict(), ttl_seconds=300)  # 5 min TTL
    return result
