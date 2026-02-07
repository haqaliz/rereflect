"""
Weekly insights API endpoints.
Provides access to AI-generated weekly insight summaries.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.weekly_insight import WeeklyInsight
from src.models.organization import Organization
from src.api.dependencies import get_current_org

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


# Schemas
class InsightItem(BaseModel):
    title: str
    description: str
    category: str
    priority: str


class WeeklyInsightResponse(BaseModel):
    id: int
    organization_id: int
    week_start: datetime
    week_end: datetime
    insights: List[InsightItem]
    generated_at: datetime

    class Config:
        from_attributes = True


class WeeklyInsightListResponse(BaseModel):
    items: List[WeeklyInsightResponse]
    total: int


# Endpoints
@router.get("/weekly", response_model=Optional[WeeklyInsightResponse])
def get_latest_weekly_insight(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get the most recent weekly insight for the current organization."""
    insight = db.query(WeeklyInsight).filter(
        WeeklyInsight.organization_id == current_org.id,
    ).order_by(WeeklyInsight.generated_at.desc()).first()

    if not insight:
        return None

    return WeeklyInsightResponse.model_validate(insight)


@router.get("/weekly/history", response_model=WeeklyInsightListResponse)
def get_weekly_insight_history(
    limit: int = Query(10, ge=1, le=52),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get historical weekly insights for the current organization."""
    query = db.query(WeeklyInsight).filter(
        WeeklyInsight.organization_id == current_org.id,
    )

    total = query.count()
    items = query.order_by(WeeklyInsight.generated_at.desc()).limit(limit).all()

    return WeeklyInsightListResponse(
        items=[WeeklyInsightResponse.model_validate(item) for item in items],
        total=total,
    )
