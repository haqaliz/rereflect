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
from src.models.churn_label_suggestion import CHURN_SUGGESTION_STATUSES, ChurnLabelSuggestion
from src.models.customer_usage import CustomerUsage
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.schemas.ai_readiness import AIReadinessResponse
from src.services.usage_score_service import TREND_STATE_INSUFFICIENT_HISTORY

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
    # `trainable` mirrors the calibrator's own filter verbatim — the four sites
    # that exclude source='auto_suggested' when fitting: worker-service's
    # tasks/churn_calibration.py:50 (per-org gate count), :125 (global fit —
    # auto rows are dropped, not just uncounted), and
    # services/calibration_refit.py:64 (_MIN_LABELS gate), :191 (label join).
    # The worker cannot import backend code, so this is coupling by convention,
    # not by shared constant — if a fifth copy of this filter appears anywhere
    # and disagrees with `!= "auto_suggested"`, that drift is the bug to catch.
    trainable = (
        db.query(func.count(CustomerChurnEvent.id))
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.source != "auto_suggested",
        )
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
        "trainable": trainable,
        "recovered": recovered,
        "by_reason": {code: cnt for code, cnt in reason_rows},
        "by_source": {src: cnt for src, cnt in source_rows},
    }


def _usage_trend_counts(org_id: int, db: Session) -> dict:
    """SM1 (usage-trend-automation-trigger PRD): breakdown of the org's
    `customer_usage.usage_trend_state` values, plus the "addressable"
    count/flag the trigger's discoverability depends on.

    "Addressable" == holds any state other than
    `TREND_STATE_INSUFFICIENT_HISTORY` ("we don't know yet" — not a real
    classification, per M2's baseline-seed rule). A fresh install with zero
    `customer_usage` rows (no usage events ever ingested via
    `POST /api/v1/webhooks/usage`) naturally reports 0 / {} / False here —
    there is no separate "no data" branch to get wrong.
    """
    rows = (
        db.query(CustomerUsage.usage_trend_state, func.count(CustomerUsage.id))
        .filter(CustomerUsage.organization_id == org_id)
        .group_by(CustomerUsage.usage_trend_state)
        .all()
    )
    by_state: Dict[str, int] = {state: cnt for state, cnt in rows}
    total = sum(by_state.values())
    addressable = sum(
        cnt for state, cnt in by_state.items() if state != TREND_STATE_INSUFFICIENT_HISTORY
    )
    return {
        "total": total,
        "addressable": addressable,
        "by_state": by_state,
    }


def _pending_suggestion_count(org_id: int, db: Session) -> int:
    """Count of the org's ChurnLabelSuggestion rows awaiting review.

    A SEPARATE number — never added to `total`, `trainable`, or
    `churn_labels_ready`. Status is derived from CHURN_SUGGESTION_STATUSES
    (the model's single source of truth: `["pending", "confirmed",
    "rejected"]`, "pending" is index 0 — the model's own default) rather
    than a hardcoded string here.
    """
    pending_status = CHURN_SUGGESTION_STATUSES[0]
    return (
        db.query(func.count(ChurnLabelSuggestion.id))
        .filter(
            ChurnLabelSuggestion.organization_id == org_id,
            ChurnLabelSuggestion.status == pending_status,
        )
        .scalar()
        or 0
    )


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
    `correction_volume_ready` is a v1 proxy using the *total* correction count,
    not a per-type gate; `corrections_by_type` is exposed precisely so a human
    can see whether the total is concentrated in one type or spread thin.

    `churn_labels_total` is what exists: every `CustomerChurnEvent` regardless
    of source (the `by_source`/`by_reason` breakdowns keep showing
    `auto_suggested`). `churn_labels_trainable` is what trains: the same count
    with `source == 'auto_suggested'` excluded, mirroring the calibrator's own
    filter (see the comment in `_churn_label_counts`). `churn_labels_ready`
    gates on `trainable`, not `total` — the gap between the two numbers is the
    honesty; a report that gated on `total` could say "ready" on rows the fit
    drops or trains as negatives.

    `usage_trend_*` fields (SM1, usage-trend-automation-trigger): the
    addressable population for the `usage_trend` automation trigger — how
    many of the org's `customer_usage` rows hold a real classification
    (anything other than `insufficient_history`, which means "no verdict
    yet", not "healthy"). `usage_trend_addressable_ready` is a plain
    `addressable > 0` flag, same honest-count spirit as
    `correction_volume_ready`/`churn_labels_ready` above: it answers "can
    this trigger fire for me at all?" rather than asserting it does. An org
    that has never ingested a usage event via `POST /api/v1/webhooks/usage`
    reports 0 / {} / False here, not an error.
    """
    org_id = current_org.id
    feedback_volume = _feedback_volume(org_id, db)
    corrections_total, corrections_by_type = _correction_counts(org_id, db)
    churn = _churn_label_counts(org_id, db)
    pending_suggestions = _pending_suggestion_count(org_id, db)
    usage_trend = _usage_trend_counts(org_id, db)
    return AIReadinessResponse(
        organization_id=org_id,
        generated_at=datetime.utcnow(),
        feedback_volume=feedback_volume,
        corrections_total=corrections_total,
        corrections_by_type=corrections_by_type,
        churn_labels_total=churn["total"],
        churn_labels_trainable=churn["trainable"],
        churn_labels_recovered=churn["recovered"],
        churn_labels_by_reason=churn["by_reason"],
        churn_labels_by_source=churn["by_source"],
        pending_suggestions=pending_suggestions,
        correction_volume_target=CORRECTION_VOLUME_TARGET,
        churn_label_target=CHURN_LABEL_TARGET,
        correction_volume_ready=corrections_total >= CORRECTION_VOLUME_TARGET,
        churn_labels_ready=churn["trainable"] >= CHURN_LABEL_TARGET,
        usage_trend_customers_total=usage_trend["total"],
        usage_trend_addressable=usage_trend["addressable"],
        usage_trend_addressable_ready=usage_trend["addressable"] > 0,
        usage_trend_by_state=usage_trend["by_state"],
    )
