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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user
from src.database.session import get_db
from src.models.org_classifier import OrgClassifierEvalRun, OrgClassifierModel
from src.models.organization import Organization
from src.models.user import User
from src.schemas.classifier_accuracy import ClassifierAccuracyResponse, ClassifierEvalRunSummary

router = APIRouter(prefix="/api/v1/settings/ai", tags=["classifier-accuracy"])

# Single source of truth for this card's readiness threshold — see module
# docstring for why this isn't an analysis-engine import.
MIN_CLASSIFIER_LABELS = 20

DEFAULT_CLASSIFIER_TYPE = "sentiment"
_HISTORY_LIMIT = 4


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
    return _build_response(current_org.id, classifier_type, db)
