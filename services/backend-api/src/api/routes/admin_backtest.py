"""
Admin Backtest API endpoint.
Evaluates churn prediction accuracy against historical data.
Requires system admin access.
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.api.dependencies import require_system_admin
from src.models.feedback import FeedbackItem
from src.models.customer_health import CustomerHealth

router = APIRouter(prefix="/api/v1/admin", tags=["admin-backtest"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    churn_days: int = 30
    organization_id: Optional[int] = None


class PredictionMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    accuracy: float
    threshold: float = 50.0


class HealthScoreMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    accuracy: float


class BacktestResponse(BaseModel):
    period_days: int
    customers_evaluated: int
    churn_risk_metrics: PredictionMetrics
    health_score_metrics: HealthScoreMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_precision_recall_f1_accuracy(tp: int, fp: int, fn: int, tn: int):
    """Compute precision, recall, F1, and accuracy from confusion matrix counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    return precision, recall, f1, accuracy


def _compute_backtest_metrics(
    db: Session,
    churn_days: int,
    organization_id: Optional[int],
) -> BacktestResponse:
    """
    Evaluate churn prediction vs actual churn proxy:
    - 'Predicted at risk' = churn_risk_score >= 50 (threshold)
    - 'Actually churned' proxy = customer had NO feedback in the following churn_days window
      (i.e. last_feedback_at is older than (now - churn_days)).

    We use CustomerHealth records as the evaluation set.
    """
    CHURN_THRESHOLD = 50
    HEALTH_SCORE_THRESHOLD = 50  # below 50 = "at risk" prediction

    now = datetime.utcnow()
    cutoff = now - timedelta(days=churn_days)

    query = db.query(CustomerHealth)
    if organization_id is not None:
        query = query.filter(CustomerHealth.organization_id == organization_id)

    records = query.all()

    if not records:
        return BacktestResponse(
            period_days=churn_days,
            customers_evaluated=0,
            churn_risk_metrics=PredictionMetrics(
                precision=0.0, recall=0.0, f1=0.0, accuracy=0.0, threshold=float(CHURN_THRESHOLD)
            ),
            health_score_metrics=HealthScoreMetrics(
                precision=0.0, recall=0.0, f1=0.0, accuracy=0.0
            ),
        )

    # Churn risk confusion matrix
    cr_tp = cr_fp = cr_fn = cr_tn = 0
    # Health score confusion matrix
    hs_tp = hs_fp = hs_fn = hs_tn = 0

    for record in records:
        # Actual churn proxy: no feedback since cutoff
        last_fb = record.last_feedback_at
        actually_churned = last_fb is None or last_fb < cutoff

        # Churn risk prediction
        cr_score = record.churn_risk_component or 0
        cr_predicted_at_risk = cr_score >= CHURN_THRESHOLD

        if actually_churned and cr_predicted_at_risk:
            cr_tp += 1
        elif not actually_churned and cr_predicted_at_risk:
            cr_fp += 1
        elif actually_churned and not cr_predicted_at_risk:
            cr_fn += 1
        else:
            cr_tn += 1

        # Health score prediction (lower = worse = at risk)
        hs_score = record.health_score or 100
        hs_predicted_at_risk = hs_score < HEALTH_SCORE_THRESHOLD

        if actually_churned and hs_predicted_at_risk:
            hs_tp += 1
        elif not actually_churned and hs_predicted_at_risk:
            hs_fp += 1
        elif actually_churned and not hs_predicted_at_risk:
            hs_fn += 1
        else:
            hs_tn += 1

    cr_prec, cr_rec, cr_f1, cr_acc = _safe_precision_recall_f1_accuracy(cr_tp, cr_fp, cr_fn, cr_tn)
    hs_prec, hs_rec, hs_f1, hs_acc = _safe_precision_recall_f1_accuracy(hs_tp, hs_fp, hs_fn, hs_tn)

    return BacktestResponse(
        period_days=churn_days,
        customers_evaluated=len(records),
        churn_risk_metrics=PredictionMetrics(
            precision=round(cr_prec, 4),
            recall=round(cr_rec, 4),
            f1=round(cr_f1, 4),
            accuracy=round(cr_acc, 4),
            threshold=float(CHURN_THRESHOLD),
        ),
        health_score_metrics=HealthScoreMetrics(
            precision=round(hs_prec, 4),
            recall=round(hs_rec, 4),
            f1=round(hs_f1, 4),
            accuracy=round(hs_acc, 4),
        ),
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/backtest",
    response_model=BacktestResponse,
    dependencies=[Depends(require_system_admin)],
)
def run_backtest(
    body: BacktestRequest,
    db: Session = Depends(get_db),
):
    """
    Evaluate churn prediction accuracy using historical CustomerHealth data.

    Uses the proxy: customers with no feedback in the last `churn_days` days
    are considered 'actually churned'. Compares against churn_risk_component
    and health_score predictions.

    System admin only.
    """
    return _compute_backtest_metrics(db, body.churn_days, body.organization_id)
