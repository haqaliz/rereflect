"""
Pydantic schema for the AI training-readiness report (M5.0).

Covers:
  - GET /api/v1/analytics/ai-readiness (org-level, any authenticated role)
"""

from datetime import datetime
from typing import Dict

from pydantic import BaseModel


class AIReadinessResponse(BaseModel):
    """Response for GET /api/v1/analytics/ai-readiness.

    Flat, no deep nesting — mirrors AccuracyCardResponse. `corrections_by_type`,
    `churn_labels_by_reason`, and `churn_labels_by_source` are dynamic dicts
    (only observed keys, never a pre-populated fixed key set) — see
    docs/planning/local-analyzer-sentiment-model/m5.0-readiness-report/spec.md
    "Data model grounding".
    """

    organization_id: int
    generated_at: datetime

    # Feedback volume
    feedback_volume: int

    # AICorrection counts (M3.3 flywheel)
    corrections_total: int
    corrections_by_type: Dict[str, int]

    # Churn labels (M4.1 CustomerChurnEvent)
    churn_labels_total: int
    # Excludes source='auto_suggested', mirroring the calibrator's own filter
    # (worker-service tasks/churn_calibration.py:50,125,
    # services/calibration_refit.py:64,191). `churn_labels_ready` gates on
    # this field, never on `churn_labels_total`.
    churn_labels_trainable: int
    churn_labels_recovered: int
    churn_labels_by_reason: Dict[str, int]
    churn_labels_by_source: Dict[str, int]

    # Activation thresholds this report exists to inform (M5.0 exit criterion)
    correction_volume_target: int
    churn_label_target: int
    correction_volume_ready: bool
    churn_labels_ready: bool

    class Config:
        from_attributes = True
