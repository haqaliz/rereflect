"""
Analytics trends API endpoint.
Provides time-series data, sentiment/source distributions, and top items.
"""
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text
from pydantic import BaseModel

from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.api.dependencies import get_current_org, get_current_user
from src.config.plans import plan_includes
from src.models.user import User

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# ─── Schemas ────────────────────────────────────────────────────────

class TrendDataPoint(BaseModel):
    date: str
    feedback_count: int
    avg_sentiment_score: Optional[float]
    positive_count: int
    neutral_count: int
    negative_count: int
    urgent_count: int
    pain_points_count: int
    feature_requests_count: int


class SentimentDistribution(BaseModel):
    positive: int
    neutral: int
    negative: int


class SourceDistributionItem(BaseModel):
    source: str
    count: int
    percentage: float


class TopItem(BaseModel):
    name: str
    count: int
    trend: str  # "up", "down", "stable"
    avg_sentiment: Optional[float]


class AnalyticsTrendsResponse(BaseModel):
    data_points: List[TrendDataPoint]
    sentiment_distribution: SentimentDistribution
    source_distribution: List[SourceDistributionItem]
    top_pain_points: List[TopItem]
    top_feature_requests: List[TopItem]
    total_feedback: int
    date_range: str
    granularity: str  # "daily" or "weekly"


# ─── Helper ─────────────────────────────────────────────────────────

RANGE_CONFIG = {
    "7d": {"days": 7, "granularity": "daily", "min_plan": "free"},
    "30d": {"days": 30, "granularity": "daily", "min_plan": "pro"},
    "90d": {"days": 90, "granularity": "weekly", "min_plan": "pro"},
}


def _compute_trend(first_half_count: int, second_half_count: int) -> str:
    """Compare second half vs first half — >10 % diff = up/down."""
    if first_half_count == 0 and second_half_count == 0:
        return "stable"
    if first_half_count == 0:
        return "up"
    ratio = (second_half_count - first_half_count) / first_half_count
    if ratio > 0.10:
        return "up"
    elif ratio < -0.10:
        return "down"
    return "stable"


# ─── Endpoint ───────────────────────────────────────────────────────

@router.get("/trends", response_model=AnalyticsTrendsResponse)
def get_trends(
    range: str = Query("7d", pattern="^(7d|30d|90d)$", description="Date range"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return time-series analytics for the organization."""

    cfg = RANGE_CONFIG[range]
    org_plan = current_org.plan or "free"

    # Plan gating — free users can only request 7d
    if not plan_includes(org_plan, cfg["min_plan"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_not_available",
                "feature": "extended_analytics_range",
                "current_plan": org_plan,
                "required_plan": cfg["min_plan"],
                "message": f"The {range} range requires the {cfg['min_plan'].title()} plan or higher.",
                "upgrade_url": "/settings/billing",
            },
        )

    days = cfg["days"]
    granularity = cfg["granularity"]
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    mid_date = end_date - timedelta(days=days // 2)

    # Base query
    base_q = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id,
        FeedbackItem.created_at >= start_date,
    )

    total_feedback = base_q.count()

    # ── Time-series data points ──────────────────────────────────
    trunc_expr = func.date_trunc("day" if granularity == "daily" else "week", FeedbackItem.created_at)

    ts_rows = (
        base_q.with_entities(
            trunc_expr.label("bucket"),
            func.count(FeedbackItem.id).label("cnt"),
            func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
            func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("pos"),
            func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neu"),
            func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("neg"),
            func.sum(case((FeedbackItem.is_urgent == True, 1), else_=0)).label("urg"),
            func.sum(case((FeedbackItem.pain_point_category.isnot(None), 1), else_=0)).label("pp"),
            func.sum(case((FeedbackItem.feature_request_category.isnot(None), 1), else_=0)).label("fr"),
        )
        .group_by(text("bucket"))
        .order_by(text("bucket"))
        .all()
    )

    def _format_bucket(bucket) -> str:
        if bucket is None:
            return ""
        if isinstance(bucket, str):
            return bucket[:10]  # "YYYY-MM-DD" from SQLite polyfill
        return bucket.strftime("%Y-%m-%d")

    data_points = [
        TrendDataPoint(
            date=_format_bucket(row.bucket),
            feedback_count=int(row.cnt or 0),
            avg_sentiment_score=round(float(row.avg_sent), 3) if row.avg_sent is not None else None,
            positive_count=int(row.pos or 0),
            neutral_count=int(row.neu or 0),
            negative_count=int(row.neg or 0),
            urgent_count=int(row.urg or 0),
            pain_points_count=int(row.pp or 0),
            feature_requests_count=int(row.fr or 0),
        )
        for row in ts_rows
    ]

    # ── Sentiment distribution ───────────────────────────────────
    sent_stats = base_q.with_entities(
        func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("positive"),
        func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neutral"),
        func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("negative"),
    ).first()

    sentiment_distribution = SentimentDistribution(
        positive=int(sent_stats.positive or 0),
        neutral=int(sent_stats.neutral or 0),
        negative=int(sent_stats.negative or 0),
    )

    # ── Source distribution ──────────────────────────────────────
    src_rows = (
        base_q.with_entities(
            FeedbackItem.source,
            func.count(FeedbackItem.id).label("cnt"),
        )
        .group_by(FeedbackItem.source)
        .order_by(func.count(FeedbackItem.id).desc())
        .all()
    )

    source_distribution = [
        SourceDistributionItem(
            source=row.source or "unknown",
            count=int(row.cnt),
            percentage=round(int(row.cnt) / total_feedback * 100, 1) if total_feedback else 0,
        )
        for row in src_rows
    ]

    # ── Top pain points (top 10) ─────────────────────────────────
    pp_rows = (
        base_q.filter(FeedbackItem.pain_point_category.isnot(None))
        .with_entities(
            FeedbackItem.pain_point_category.label("name"),
            func.count(FeedbackItem.id).label("cnt"),
            func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
        )
        .group_by(FeedbackItem.pain_point_category)
        .order_by(func.count(FeedbackItem.id).desc())
        .limit(10)
        .all()
    )

    # Compute trend per pain point by comparing first half vs second half
    top_pain_points: List[TopItem] = []
    for row in pp_rows:
        first_half = (
            base_q.filter(
                FeedbackItem.pain_point_category == row.name,
                FeedbackItem.created_at < mid_date,
            ).count()
        )
        second_half = int(row.cnt) - first_half
        top_pain_points.append(
            TopItem(
                name=row.name,
                count=int(row.cnt),
                trend=_compute_trend(first_half, second_half),
                avg_sentiment=round(float(row.avg_sent), 3) if row.avg_sent is not None else None,
            )
        )

    # ── Top feature requests (top 10) ────────────────────────────
    fr_rows = (
        base_q.filter(FeedbackItem.feature_request_category.isnot(None))
        .with_entities(
            FeedbackItem.feature_request_category.label("name"),
            func.count(FeedbackItem.id).label("cnt"),
            func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
        )
        .group_by(FeedbackItem.feature_request_category)
        .order_by(func.count(FeedbackItem.id).desc())
        .limit(10)
        .all()
    )

    top_feature_requests: List[TopItem] = []
    for row in fr_rows:
        first_half = (
            base_q.filter(
                FeedbackItem.feature_request_category == row.name,
                FeedbackItem.created_at < mid_date,
            ).count()
        )
        second_half = int(row.cnt) - first_half
        top_feature_requests.append(
            TopItem(
                name=row.name,
                count=int(row.cnt),
                trend=_compute_trend(first_half, second_half),
                avg_sentiment=round(float(row.avg_sent), 3) if row.avg_sent is not None else None,
            )
        )

    return AnalyticsTrendsResponse(
        data_points=data_points,
        sentiment_distribution=sentiment_distribution,
        source_distribution=source_distribution,
        top_pain_points=top_pain_points,
        top_feature_requests=top_feature_requests,
        total_feedback=total_feedback,
        date_range=f"Last {days} days",
        granularity=granularity,
    )
