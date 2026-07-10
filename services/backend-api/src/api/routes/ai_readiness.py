"""
AI training-readiness report API (M5.0 — Data & Model Readiness Assessment).

GET /api/v1/analytics/ai-readiness — per-org, read-only aggregation over
FeedbackItem / AICorrection / CustomerChurnEvent. No ML, no mutations, no new tables.

See docs/planning/local-analyzer-sentiment-model/m5.0-readiness-report/spec.md.
"""

from datetime import datetime
from typing import Dict, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org
from src.config.readiness_thresholds import CHURN_LABEL_TARGET, CORRECTION_VOLUME_TARGET
from src.database.session import get_db
from src.models.ai_correction import AICorrection
from src.models.churn_event import CustomerChurnEvent
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.schemas.ai_readiness import AIReadinessResponse

analytics_router = APIRouter(prefix="/api/v1/analytics", tags=["ai-readiness"])
router = analytics_router  # match churn_accuracy.py's `router = analytics_router` export convention


# ---------------------------------------------------------------------------
# Internal helpers — each a single filtered query, org-scoped
# ---------------------------------------------------------------------------


def _feedback_volume(org_id: int, db: Session) -> int:
    """Total FeedbackItem rows for org_id."""
    return (
        db.query(func.count(FeedbackItem.id))
        .filter(FeedbackItem.organization_id == org_id)
        .scalar()
        or 0
    )


def _correction_counts(org_id: int, db: Session) -> Tuple[int, Dict[str, int]]:
    """Total AICorrection count + dynamic breakdown by correction_type for org_id.

    `correction_type` is a free string (not a DB enum) — the breakdown dict only
    contains observed keys, never a pre-populated fixed set.
    """
    total = (
        db.query(func.count(AICorrection.id))
        .filter(AICorrection.organization_id == org_id)
        .scalar()
        or 0
    )
    rows = (
        db.query(AICorrection.correction_type, func.count(AICorrection.id))
        .filter(AICorrection.organization_id == org_id)
        .group_by(AICorrection.correction_type)
        .all()
    )
    by_type: Dict[str, int] = {ct: cnt for ct, cnt in rows}
    return total, by_type


def _churn_label_counts(org_id: int, db: Session) -> dict:
    """Total/recovered CustomerChurnEvent counts + breakdowns by reason_code/source for org_id.

    A recovered event (recovered_at set) still counts toward `total` and its
    reason/source bucket — recovery doesn't erase that the customer did churn
    at some point; only `recovered` distinguishes it.
    """
    total = (
        db.query(func.count(CustomerChurnEvent.id))
        .filter(CustomerChurnEvent.organization_id == org_id)
        .scalar()
        or 0
    )
    recovered = (
        db.query(func.count(CustomerChurnEvent.id))
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.recovered_at.isnot(None),
        )
        .scalar()
        or 0
    )
    reason_rows = (
        db.query(CustomerChurnEvent.reason_code, func.count(CustomerChurnEvent.id))
        .filter(CustomerChurnEvent.organization_id == org_id)
        .group_by(CustomerChurnEvent.reason_code)
        .all()
    )
    source_rows = (
        db.query(CustomerChurnEvent.source, func.count(CustomerChurnEvent.id))
        .filter(CustomerChurnEvent.organization_id == org_id)
        .group_by(CustomerChurnEvent.source)
        .all()
    )
    return {
        "total": total,
        "recovered": recovered,
        "by_reason": {code: cnt for code, cnt in reason_rows},
        "by_source": {src: cnt for src, cnt in source_rows},
    }


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/ai-readiness
# ---------------------------------------------------------------------------


@analytics_router.get("/ai-readiness", response_model=AIReadinessResponse)
def get_ai_readiness(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> AIReadinessResponse:
    """Per-org AI training-readiness snapshot (M5.0, no ML).

    Read-only, no plan/feature gate, no role gate — any authenticated user in
    the org can view this (matches RBAC "View dashboard & analytics — all roles").

    Thresholds (`correction_volume_target`, `churn_label_target`) are v1 planning
    targets, not validated ML requirements — see
    docs/planning/local-analyzer-sentiment-model/m5.0-readiness-report/spec.md.
    `correction_volume_ready`/`churn_labels_ready` are v1 proxies using the
    *total* count, not a per-type gate; `corrections_by_type` is exposed
    precisely so a human can see whether the total is concentrated in one type
    or spread thin.
    """
    org_id = current_org.id
    feedback_volume = _feedback_volume(org_id, db)
    corrections_total, corrections_by_type = _correction_counts(org_id, db)
    churn = _churn_label_counts(org_id, db)
    return AIReadinessResponse(
        organization_id=org_id,
        generated_at=datetime.utcnow(),
        feedback_volume=feedback_volume,
        corrections_total=corrections_total,
        corrections_by_type=corrections_by_type,
        churn_labels_total=churn["total"],
        churn_labels_recovered=churn["recovered"],
        churn_labels_by_reason=churn["by_reason"],
        churn_labels_by_source=churn["by_source"],
        correction_volume_target=CORRECTION_VOLUME_TARGET,
        churn_label_target=CHURN_LABEL_TARGET,
        correction_volume_ready=corrections_total >= CORRECTION_VOLUME_TARGET,
        churn_labels_ready=churn["total"] >= CHURN_LABEL_TARGET,
    )
