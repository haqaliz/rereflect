"""
GET /api/v1/settings/ai/classifier/accuracy (settings-api-and-accuracy-card
aspect, M5.2 disclosure layer).

Read-only surface over OrgClassifierModel + OrgClassifierEvalRun, org-scoped.
No require_feature gate: mirrors sentiment_accuracy.py's disclosure/
self-hosting-transparency posture, not a premium analytics feature.

MIN_CLASSIFIER_LABELS is defined here as the single source of truth for this
card's readiness threshold. It is asserted equal to
analyzer.corrections_classifier.labels.MIN_LABELS by
tests/test_classifier_accuracy_route.py::TestMinLabelsParity — we do NOT
import the analysis-engine package directly in this request path (it would
pull sklearn/numpy into every settings-page load for a single integer).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_admin_or_owner
from src.api.routes.ai_settings import _get_or_create_config
from src.database.session import get_db
from src.models.org_ai_config import OrgAIConfig
from src.models.org_classifier import OrgClassifierEvalRun, OrgClassifierModel
from src.models.organization import Organization
from src.models.user import User
from src.schemas.classifier_accuracy import (
    ClassifierAccuracyResponse,
    ClassifierEvalRunSummary,
    ClassifierVersionsResponse,
    ClassifierVersionSummary,
)
from src.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/settings/ai", tags=["classifier-accuracy"])

# Single source of truth for this card's readiness threshold — see module
# docstring for why this isn't an analysis-engine import.
MIN_CLASSIFIER_LABELS = 20

DEFAULT_CLASSIFIER_TYPE = "sentiment"
_HISTORY_LIMIT = 4

# M8: whitelist of valid classifier_type values, shared by versions/rollback/resume.
VALID_CLASSIFIER_TYPES = {"sentiment", "category", "urgency", "churn"}

# classifier_type -> OrgAIConfig autopromote-hold column name.
_HOLD_COLUMN_BY_TYPE = {
    "sentiment": "sentiment_autopromote_hold",
    "category": "category_autopromote_hold",
    "urgency": "urgency_autopromote_hold",
    "churn": "churn_autopromote_hold",
}


def _validate_classifier_type(classifier_type: str) -> None:
    """M8: whitelist classifier_type; unknown -> 400 (defense in depth, mirrors
    resolve_classifier's NULL/unrecognized-treated-as-off posture but at the
    API boundary this must be a loud 400, not a silent fallback)."""
    if classifier_type not in VALID_CLASSIFIER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown classifier_type '{classifier_type}'. Must be one of {sorted(VALID_CLASSIFIER_TYPES)}.",
        )


def _get_hold(org_id: int, classifier_type: str, db: Session) -> bool:
    """Read the current autopromote-hold flag for (org, type), defaulting to
    False when no OrgAIConfig row exists yet for this org."""
    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    if config is None:
        return False
    return bool(getattr(config, _HOLD_COLUMN_BY_TYPE[classifier_type]))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_active_model(
    org_id: int, classifier_type: str, db: Session
) -> Optional[OrgClassifierModel]:
    """Return the org's active classifier model of the given type, if any."""
    return (
        db.query(OrgClassifierModel)
        .filter(
            OrgClassifierModel.organization_id == org_id,
            OrgClassifierModel.classifier_type == classifier_type,
            OrgClassifierModel.is_active.is_(True),
        )
        .first()
    )


def _collect_history(
    org_id: int, classifier_type: str, limit: int, db: Session
) -> List[OrgClassifierEvalRun]:
    """Return the most recent `limit` eval runs for org_id, newest first."""
    return (
        db.query(OrgClassifierEvalRun)
        .filter(
            OrgClassifierEvalRun.organization_id == org_id,
            OrgClassifierEvalRun.classifier_type == classifier_type,
        )
        .order_by(OrgClassifierEvalRun.created_at.desc())
        .limit(limit)
        .all()
    )


def _run_to_summary(run: OrgClassifierEvalRun) -> ClassifierEvalRunSummary:
    return ClassifierEvalRunSummary(
        incumbent_macro_f1=float(run.incumbent_macro_f1) if run.incumbent_macro_f1 is not None else None,
        challenger_macro_f1=float(run.challenger_macro_f1) if run.challenger_macro_f1 is not None else None,
        macro_f1_delta=float(run.macro_f1_delta) if run.macro_f1_delta is not None else None,
        decision=run.decision,
        n=run.n,
        created_at=run.created_at,
    )


def _build_response(
    org_id: int, classifier_type: str, db: Session
) -> ClassifierAccuracyResponse:
    model = _get_active_model(org_id, classifier_type, db)
    hold = _get_hold(org_id, classifier_type, db)

    if model is None:
        return ClassifierAccuracyResponse(
            classifier_type=classifier_type,
            has_model=False,
            label_count=0,
            macro_f1=None,
            fit_at=None,
            is_ready=False,
            min_labels=MIN_CLASSIFIER_LABELS,
            history=[],
            hold=hold,
        )

    history_runs = _collect_history(org_id, classifier_type, limit=_HISTORY_LIMIT, db=db)

    return ClassifierAccuracyResponse(
        classifier_type=classifier_type,
        has_model=True,
        label_count=model.label_count,
        macro_f1=float(model.macro_f1) if model.macro_f1 is not None else None,
        fit_at=model.fit_at,
        is_ready=model.label_count >= MIN_CLASSIFIER_LABELS,
        min_labels=MIN_CLASSIFIER_LABELS,
        history=[_run_to_summary(r) for r in history_runs],
        hold=hold,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/settings/ai/classifier/accuracy
# ---------------------------------------------------------------------------


@router.get("/classifier/accuracy", response_model=ClassifierAccuracyResponse)
def get_classifier_accuracy(
    classifier_type: str = DEFAULT_CLASSIFIER_TYPE,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ClassifierAccuracyResponse:
    """Return the caller org's active per-org corrections-classifier state.

    Never raises to the caller for the "no model yet" case — has_model=False
    is an honest empty state, not an error (mirrors get_sentiment_accuracy /
    get_embeddings_status).
    """
    _validate_classifier_type(classifier_type)
    return _build_response(current_org.id, classifier_type, db)


# ---------------------------------------------------------------------------
# GET /api/v1/settings/ai/classifier/versions
# ---------------------------------------------------------------------------


@router.get("/classifier/versions", response_model=ClassifierVersionsResponse)
def get_classifier_versions(
    classifier_type: str = DEFAULT_CLASSIFIER_TYPE,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ClassifierVersionsResponse:
    """Return every OrgClassifierModel version for (current_org, type),
    newest-first by fit_at. Read access: any authenticated org user — no
    admin gate, this mirrors GET .../accuracy's read posture (M6).
    """
    _validate_classifier_type(classifier_type)

    versions = (
        db.query(OrgClassifierModel)
        .filter(
            OrgClassifierModel.organization_id == current_org.id,
            OrgClassifierModel.classifier_type == classifier_type,
        )
        .order_by(OrgClassifierModel.fit_at.desc())
        .all()
    )

    return ClassifierVersionsResponse(
        classifier_type=classifier_type,
        hold=_get_hold(current_org.id, classifier_type, db),
        versions=[
            ClassifierVersionSummary(
                id=v.id,
                fit_at=v.fit_at,
                macro_f1=float(v.macro_f1) if v.macro_f1 is not None else None,
                label_count=v.label_count,
                is_active=v.is_active,
            )
            for v in versions
        ],
    )


# ---------------------------------------------------------------------------
# POST /api/v1/settings/ai/classifier/rollback
# ---------------------------------------------------------------------------


@router.post(
    "/classifier/rollback",
    response_model=ClassifierAccuracyResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def rollback_classifier(
    request: Request,
    classifier_type: str = DEFAULT_CLASSIFIER_TYPE,
    to_version_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ClassifierAccuracyResponse:
    """Deactivate the org's active model and reactivate a prior (inactive)
    version. Admin/owner only.

    - `to_version_id` given: reactivate exactly that version. It must belong
      to this org + classifier_type and currently be inactive, else 404 (no
      cross-org/cross-type leakage).
    - `to_version_id` absent: today's behavior — reactivate the most recent
      prior (inactive) version, or disable-only if none exists.

    404 if the org has no active model of this type to roll back (nothing to
    do, and re-calling after a successful disable-only rollback is a safe
    no-op path that also 404s — idempotent-safe, never a 500).

    Ordered deactivate -> flush -> activate -> commit in one transaction so
    the partial-unique "one active per (org, type)" index never sees two
    active rows for this org+type at once.

    Engages the per-type autopromote hold (OrgAIConfig.<type>_autopromote_hold)
    in the SAME transaction, but ONLY when a prior/target version is actually
    reactivated — a disable-only rollback (no prior available) must NOT
    engage the hold (PRD R5).
    """
    _validate_classifier_type(classifier_type)

    active = _get_active_model(current_org.id, classifier_type, db)
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active '{classifier_type}' classifier model to roll back for this organization.",
        )

    if to_version_id is not None:
        prior = (
            db.query(OrgClassifierModel)
            .filter(
                OrgClassifierModel.id == to_version_id,
                OrgClassifierModel.organization_id == current_org.id,
                OrgClassifierModel.classifier_type == classifier_type,
                OrgClassifierModel.is_active.is_(False),
            )
            .first()
        )
        if prior is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No inactive '{classifier_type}' classifier version {to_version_id} found for this organization.",
            )
    else:
        prior = (
            db.query(OrgClassifierModel)
            .filter(
                OrgClassifierModel.organization_id == current_org.id,
                OrgClassifierModel.classifier_type == classifier_type,
                OrgClassifierModel.is_active.is_(False),
                OrgClassifierModel.id != active.id,
            )
            .order_by(OrgClassifierModel.fit_at.desc())
            .first()
        )

    from_model_id = active.id

    # Deactivate first (and flush) so the partial-unique index is never asked
    # to hold two active rows for this (org, type) pair, even momentarily.
    active.is_active = False
    db.flush()

    held = False
    if prior is not None:
        prior.is_active = True
        config = _get_or_create_config(current_org.id, db)
        setattr(config, _HOLD_COLUMN_BY_TYPE[classifier_type], True)
        held = True

    db.commit()

    log_action(
        db=db,
        org_id=current_org.id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="classifier_rolled_back",
        target_type="org_classifier_model",
        target_id=prior.id if prior is not None else None,
        details={
            "classifier_type": classifier_type,
            "from_model_id": from_model_id,
            "to_model_id": prior.id if prior is not None else None,
            "held": held,
        },
        request=request,
    )

    return _build_response(current_org.id, classifier_type, db)


# ---------------------------------------------------------------------------
# POST /api/v1/settings/ai/classifier/resume
# ---------------------------------------------------------------------------


@router.post(
    "/classifier/resume",
    response_model=ClassifierAccuracyResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def resume_classifier(
    request: Request,
    classifier_type: str = DEFAULT_CLASSIFIER_TYPE,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ClassifierAccuracyResponse:
    """Clear the per-type autopromote hold, letting the weekly retrain job
    resume auto-promotion. Idempotent — 200 even if the hold was already
    False. Admin/owner only (M5).
    """
    _validate_classifier_type(classifier_type)

    config = _get_or_create_config(current_org.id, db)
    setattr(config, _HOLD_COLUMN_BY_TYPE[classifier_type], False)
    db.commit()

    log_action(
        db=db,
        org_id=current_org.id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="classifier_autopromote_resumed",
        target_type="org_classifier_model",
        target_id=None,
        details={"classifier_type": classifier_type},
        request=request,
    )

    return _build_response(current_org.id, classifier_type, db)
