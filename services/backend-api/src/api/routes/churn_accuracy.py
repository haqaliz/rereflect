"""
Churn accuracy API endpoints (M4.1 Phase 6.2a).

GET /api/v1/analytics/churn-accuracy          — org-level accuracy card (Business+)
GET /api/v1/system/churn-accuracy             — cross-org admin overview (system admin)
GET /api/v1/system/churn-accuracy/{org_id}/history — per-org model history (system admin)

Pure read endpoints — no mutations.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_feature,
    require_system_admin,
)
from src.database.session import get_db
from src.models.churn_calibration import ChurnBacktestRun, ChurnCalibrationModel
from src.models.organization import Organization
from src.models.user import User
from src.schemas.churn_accuracy import (
    AccuracyCardResponse,
    BacktestRunSummary,
    ModelVersionSummary,
    OrgAccuracyRow,
    OrgHistoryResponse,
    SystemAccuracyResponse,
)

# ---------------------------------------------------------------------------
# Routers — two separate routers for the two URL prefixes
# ---------------------------------------------------------------------------

analytics_router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["churn-accuracy"],
)

system_router = APIRouter(
    prefix="/api/v1/system",
    tags=["churn-accuracy-admin"],
)

# Unified export for main.py to include
router = analytics_router  # system_router is included separately below


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_active_model(
    org_id: Optional[int], db: Session
) -> Optional[ChurnCalibrationModel]:
    """Return the active calibration model for org_id (or the global model if org_id is None)."""
    return (
        db.query(ChurnCalibrationModel)
        .filter(
            ChurnCalibrationModel.organization_id == org_id,
            ChurnCalibrationModel.is_active.is_(True),
        )
        .first()
    )


def _collect_history(
    org_id: Optional[int], limit: int, db: Session
) -> List[ChurnBacktestRun]:
    """Return the most recent `limit` backtest runs for org_id, newest first."""
    return (
        db.query(ChurnBacktestRun)
        .filter(ChurnBacktestRun.organization_id == org_id)
        .order_by(ChurnBacktestRun.run_at.desc())
        .limit(limit)
        .all()
    )


def _run_to_summary(run: ChurnBacktestRun) -> BacktestRunSummary:
    """Convert a ChurnBacktestRun ORM row to a BacktestRunSummary schema."""
    return BacktestRunSummary(
        run_at=run.run_at,
        label_count=run.label_count,
        precision=float(run.precision) if run.precision is not None else None,
        recall=float(run.recall) if run.recall is not None else None,
        f1=float(run.f1) if run.f1 is not None else None,
        auc=float(run.auc) if run.auc is not None else None,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/churn-accuracy
# ---------------------------------------------------------------------------


@analytics_router.get(
    "/churn-accuracy",
    response_model=AccuracyCardResponse,
    dependencies=[Depends(require_feature("churn_accuracy_card"))],
)
def get_org_accuracy_card(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> AccuracyCardResponse:
    """Return the caller org's current model accuracy state.

    Falls back to the global model when the org has no active dedicated model.
    """
    org_id: int = current_org.id

    # Try org-specific active model first
    model = _get_active_model(org_id, db)
    is_global_fallback = False

    if model is None:
        # Fall back to global model (organization_id IS NULL)
        model = _get_active_model(None, db)
        is_global_fallback = True

    if model is None:
        # No model anywhere — return null state
        return AccuracyCardResponse(
            model_id=None,
            label_count=0,
            positive_count=0,
            precision=None,
            recall=None,
            f1=None,
            auc=None,
            fit_at=None,
            is_global_fallback=True,
            history=[],
        )

    history_runs = _collect_history(org_id, limit=4, db=db)

    return AccuracyCardResponse(
        model_id=model.id,
        label_count=model.label_count,
        positive_count=model.positive_count,
        precision=float(model.precision) if model.precision is not None else None,
        recall=float(model.recall) if model.recall is not None else None,
        f1=float(model.f1) if model.f1 is not None else None,
        auc=float(model.auc) if model.auc is not None else None,
        fit_at=model.fit_at,
        is_global_fallback=is_global_fallback,
        history=[_run_to_summary(r) for r in history_runs],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/system/churn-accuracy
# ---------------------------------------------------------------------------


@system_router.get(
    "/churn-accuracy",
    response_model=SystemAccuracyResponse,
)
def get_system_accuracy(
    _admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> SystemAccuracyResponse:
    """Cross-org accuracy overview for system admins.

    Lists every org that has an active model with ≥ 1 label, sorted by
    label_count descending.  Includes a global model summary.
    """
    # Fetch all active org models (organization_id IS NOT NULL)
    org_models: List[ChurnCalibrationModel] = (
        db.query(ChurnCalibrationModel)
        .filter(
            ChurnCalibrationModel.organization_id.isnot(None),
            ChurnCalibrationModel.is_active.is_(True),
            ChurnCalibrationModel.label_count > 0,
        )
        .all()
    )

    # Build org rows
    rows: List[OrgAccuracyRow] = []
    for model in org_models:
        org = db.query(Organization).filter(Organization.id == model.organization_id).first()
        if org is None:
            continue
        rows.append(
            OrgAccuracyRow(
                organization_id=org.id,
                organization_name=org.name,
                label_count=model.label_count,
                f1=float(model.f1) if model.f1 is not None else None,
                last_refit_at=model.fit_at,
                is_using_global_fallback=False,
            )
        )

    # Sort by label_count descending
    rows.sort(key=lambda r: r.label_count, reverse=True)

    # Fetch global model (organization_id IS NULL)
    global_model = _get_active_model(None, db)

    # Count orgs using global vs dedicated
    # Dedicated = those appearing in org_models list above
    dedicated_org_ids = {m.organization_id for m in org_models}
    total_orgs_with_dedicated = len(dedicated_org_ids)

    # All orgs in the DB with plan != 'free' that have no dedicated model
    all_orgs = db.query(Organization).all()
    orgs_using_global = sum(
        1 for o in all_orgs if o.id not in dedicated_org_ids
    )

    return SystemAccuracyResponse(
        orgs=rows,
        global_model_id=global_model.id if global_model else None,
        global_f1=float(global_model.f1) if global_model and global_model.f1 is not None else None,
        global_label_count=global_model.label_count if global_model else 0,
        total_orgs_using_global=orgs_using_global,
        total_orgs_with_dedicated_model=total_orgs_with_dedicated,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/system/churn-accuracy/{org_id}/history
# ---------------------------------------------------------------------------


@system_router.get(
    "/churn-accuracy/{org_id}/history",
    response_model=OrgHistoryResponse,
)
def get_org_accuracy_history(
    org_id: int,
    _admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> OrgHistoryResponse:
    """Full model version + backtest run history for a specific org (system admin only).

    Returns all model versions (newest first) and last 30 backtest runs.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )

    # All model versions for this org, newest first
    models: List[ChurnCalibrationModel] = (
        db.query(ChurnCalibrationModel)
        .filter(ChurnCalibrationModel.organization_id == org_id)
        .order_by(ChurnCalibrationModel.fit_at.desc())
        .all()
    )

    backtest_runs = _collect_history(org_id, limit=30, db=db)

    return OrgHistoryResponse(
        organization_id=org.id,
        organization_name=org.name,
        models=[
            ModelVersionSummary(
                id=m.id,
                is_active=m.is_active,
                label_count=m.label_count,
                positive_count=m.positive_count,
                precision=float(m.precision) if m.precision is not None else None,
                recall=float(m.recall) if m.recall is not None else None,
                f1=float(m.f1) if m.f1 is not None else None,
                auc=float(m.auc) if m.auc is not None else None,
                fit_at=m.fit_at,
                threshold_bands=m.threshold_bands or {},
            )
            for m in models
        ],
        backtest_runs=[_run_to_summary(r) for r in backtest_runs],
    )
