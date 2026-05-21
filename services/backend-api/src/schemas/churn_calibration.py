"""
Pydantic schemas for ChurnCalibrationModel and ChurnBacktestRun (M4.1).
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChurnCalibrationModelResponse(BaseModel):
    """Schema for serializing a ChurnCalibrationModel row."""

    id: int
    organization_id: Optional[int] = None
    model_json: Dict[str, Any]
    label_count: int
    positive_count: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    auc: Optional[float] = None
    threshold_bands: Dict[str, float]
    fit_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class ChurnBacktestRunResponse(BaseModel):
    """Schema for serializing a ChurnBacktestRun row."""

    id: int
    organization_id: Optional[int] = None
    calibration_model_id: int
    run_at: datetime
    label_count: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    auc: Optional[float] = None
    optimal_threshold: Optional[float] = None
    duration_ms: Optional[int] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True
