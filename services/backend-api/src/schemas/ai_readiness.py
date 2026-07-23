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

    # CRM-sourced churn label suggestions awaiting operator review
    # (churn_label_suggestions, M4 table). A SEPARATE count — never folded
    # into churn_labels_total, churn_labels_trainable, or churn_labels_ready.
    pending_suggestions: int

    # Activation thresholds this report exists to inform (M5.0 exit criterion)
    correction_volume_target: int
    churn_label_target: int
    correction_volume_ready: bool
    churn_labels_ready: bool

    # Usage-trend addressable population (usage-trend-automation-trigger, SM1).
    # "Addressable" == the `usage_trend` automation trigger could in principle
    # fire for this customer, i.e. the customer holds a real classification
    # rather than the "we don't know yet" placeholder. `usage_trend_by_state`
    # is a dynamic dict of ONLY observed states (mirrors corrections_by_type /
    # churn_labels_by_reason) — a fresh install with zero CustomerUsage rows
    # (no usage events ever ingested) reports every field as 0 / {} / False,
    # never an error.
    usage_trend_customers_total: int
    usage_trend_addressable: int
    usage_trend_addressable_ready: bool
    usage_trend_by_state: Dict[str, int]

    class Config:
        from_attributes = True
