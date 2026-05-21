"""
Pydantic response schemas for the churn cohort analytics endpoint (M4.1 Phase 4).
"""

from typing import Optional
from pydantic import BaseModel


class CohortBucket(BaseModel):
    """One cohort row — e.g. 'Slack', '2026-03', or 'Light (1-3)'."""

    label: str
    total_customers: int
    churned_customers: int
    churn_rate: float                   # 0.0 – 1.0
    avg_probability: Optional[float]    # avg churn_probability; None when no rows have a value
    top_reason_codes: list[dict]        # [{"code": "price", "count": 5}, ...] — top 3


class CohortGridCell(BaseModel):
    """One cell in the 2-D heatmap (cohort × time-bucket)."""

    cohort_label: str
    time_bucket: str      # ISO month ("2026-03") for "all"; "Week N" for 30d/90d
    churn_rate: float
    churned_count: int


class CohortAnalyticsResponse(BaseModel):
    """Full response for GET /api/v1/analytics/churn-cohorts."""

    dimension: str              # echoed back
    range: str
    cohorts: list[CohortBucket]
    grid: list[CohortGridCell]
    overall_churn_rate: float
    total_customers: int
    total_churned: int
