"""
WeeklyInsight model for storing AI-generated weekly insight summaries.
"""

from sqlalchemy import Column, Integer, String, DateTime, JSON, Index
from datetime import datetime

from src.models.base import Base


class WeeklyInsight(Base):
    """AI-generated weekly insight summaries per organization."""
    __tablename__ = "weekly_insights"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    insights = Column(JSON, nullable=False)  # Array of {title, description, category, priority}
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_weekly_insight_org_week', 'organization_id', 'week_start'),
    )
