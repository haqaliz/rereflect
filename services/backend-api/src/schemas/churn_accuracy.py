"""
Pydantic schemas for churn accuracy API endpoints (M4.1 Phase 6.2a).

Covers:
  - GET /api/v1/analytics/churn-accuracy   (org-level, Business+)
  - GET /api/v1/system/churn-accuracy      (system admin only)
  - GET /api/v1/system/churn-accuracy/{org_id}/history  (system admin only)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class BacktestRunSummary(BaseModel):
    """Compact summary of one ChurnBacktestRun row for trend display."""

    run_at: datetime
    label_count: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    auc: Optional[float] = None

    class Config:
        from_attributes = True


class AccuracyCardResponse(BaseModel):
    """Response for GET /api/v1/analytics/churn-accuracy (org-level card)."""

    model_id: Optional[int] = None
    label_count: int
    positive_count: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    auc: Optional[float] = None
    fit_at: Optional[datetime] = None
    is_global_fallback: bool
    history: List[BacktestRunSummary]


class OrgAccuracyRow(BaseModel):
    """One row in the system-wide cross-org accuracy table."""

    organization_id: int
    organization_name: str
    label_count: int
    f1: Optional[float] = None
    last_refit_at: Optional[datetime] = None
    is_using_global_fallback: bool


class SystemAccuracyResponse(BaseModel):
    """Response for GET /api/v1/system/churn-accuracy (admin overview)."""

    orgs: List[OrgAccuracyRow]
    global_model_id: Optional[int] = None
    global_f1: Optional[float] = None
    global_label_count: int
    total_orgs_using_global: int
    total_orgs_with_dedicated_model: int


class ModelVersionSummary(BaseModel):
    """One row in the per-org model version history."""

    id: int
    is_active: bool
    label_count: int
    positive_count: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    auc: Optional[float] = None
    fit_at: datetime
    threshold_bands: Dict[str, Any]

    class Config:
        from_attributes = True


class OrgHistoryResponse(BaseModel):
    """Response for GET /api/v1/system/churn-accuracy/{org_id}/history."""

    organization_id: int
    organization_name: str
    models: List[ModelVersionSummary]
    backtest_runs: List[BacktestRunSummary]
