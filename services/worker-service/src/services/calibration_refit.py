"""
Calibration refit logic — Phase 6.1 (M4.1).

Entry point
-----------
    refit_org(org_id, db) -> dict

Pure logic: no Celery, no FastAPI. All DB I/O is synchronous SQLAlchemy.
The caller (churn_calibration Celery task) owns the session lifecycle.

numpy/sklearn imports are intentionally lazy (inside functions) so the module
can be imported in environments where those packages are unavailable (e.g.,
Python 3.14 CI venv where numpy wheels don't yet exist).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.models import (
    ChurnBacktestRun,
    ChurnCalibrationModel,
    CustomerChurnEvent,
    CustomerHealth,
    CustomerHealthHistory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_LABELS: int = 20
_LABEL_WINDOW_DAYS: int = 180
_F1_DROP_THRESHOLD: float = 0.10
_DEFAULT_BANDS: dict = {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refit_org(org_id: int, db: Session) -> dict:
    """Refit an isotonic calibration model for a single organisation.

    Returns a summary dict. Skips if fewer than _MIN_LABELS non-auto-suggested
    churn events exist — these are the qualifying positive labels that drive
    calibration quality.
    """
    start_ms = int(time.monotonic() * 1000)

    # Count qualifying events first to enforce the threshold gate
    qualifying_event_count = (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.source != "auto_suggested",
        )
        .count()
    )

    if qualifying_event_count < _MIN_LABELS:
        return {
            "skipped": True,
            "reason": f"insufficient_labels ({qualifying_event_count} < {_MIN_LABELS})",
        }

    scores, labels = _collect_labels(org_id, db)

    if len(scores) == 0:
        return {
            "skipped": True,
            "reason": "no_customers_in_window",
        }

    positive_count = int(sum(labels))

    # Fit isotonic model (lazy import — numpy may not be available in test venv)
    ir_model = _fit_isotonic(scores, labels)
    mj = _serialize_model(ir_model, scores, labels)

    # Compute metrics on the full dataset
    metrics = _compute_metrics(scores, labels, ir_model)

    # Check F1 drop against previous active model
    prev_model = _load_prev_active(org_id, db)
    f1_dropped = _check_f1_drop(org_id, metrics["f1"], prev_model)

    # Deactivate previous active model
    if prev_model is not None:
        prev_model.is_active = False
        db.add(prev_model)

    # Insert new active model
    new_model = ChurnCalibrationModel(
        organization_id=org_id,
        model_json=mj,
        label_count=len(scores),
        positive_count=positive_count,
        precision=round(metrics["precision"], 4),
        recall=round(metrics["recall"], 4),
        f1=round(metrics["f1"], 4),
        auc=round(metrics["auc"], 4),
        threshold_bands=dict(_DEFAULT_BANDS),
        fit_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(new_model)
    db.flush()  # populate new_model.id before backtest insert

    # Insert backtest run
    duration_ms = int(time.monotonic() * 1000) - start_ms
    run = ChurnBacktestRun(
        organization_id=org_id,
        calibration_model_id=new_model.id,
        run_at=datetime.utcnow(),
        label_count=len(scores),
        precision=round(metrics["precision"], 4),
        recall=round(metrics["recall"], 4),
        f1=round(metrics["f1"], 4),
        auc=round(metrics["auc"], 4),
        optimal_threshold=round(metrics["optimal_threshold"], 4),
        duration_ms=duration_ms,
    )
    db.add(run)
    db.commit()

    return {
        "model_id": new_model.id,
        "label_count": len(scores),
        "positive_count": positive_count,
        "f1": metrics["f1"],
        "f1_dropped": f1_dropped,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_labels(org_id: int, db: Session) -> tuple[list[float], list[float]]:
    """Build (scores, labels) from customers active in the last 180 days.

    Labels:
    - positive (1.0) — customer has any churn event (active or recovered),
      source != 'auto_suggested'.
    - negative (0.0) — customer has no qualifying churn event.

    Scores come from the customer's churn_risk_component at churn time
    (uses customer_health_history if available; else current health score).
    """
    cutoff = datetime.utcnow() - timedelta(days=_LABEL_WINDOW_DAYS)

    health_rows = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.last_feedback_at >= cutoff,
        )
        .all()
    )

    if not health_rows:
        return [], []

    email_to_health: dict[str, CustomerHealth] = {h.customer_email: h for h in health_rows}
    qualifying_emails = list(email_to_health.keys())

    # Qualifying churn events (non-auto-suggested) for these emails
    churn_events = (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.customer_email.in_(qualifying_emails),
            CustomerChurnEvent.source != "auto_suggested",
        )
        .all()
    )

    churned_emails: set[str] = {e.customer_email for e in churn_events}
    # Map email → latest churn event timestamp (for history lookup)
    email_to_churn_at: dict[str, datetime] = {}
    for e in churn_events:
        prev = email_to_churn_at.get(e.customer_email)
        if prev is None or e.churned_at > prev:
            email_to_churn_at[e.customer_email] = e.churned_at

    scores: list[float] = []
    labels: list[float] = []

    for email, health in email_to_health.items():
        is_churned = email in churned_emails
        score = _get_score_for_customer(health, email_to_churn_at.get(email), db)
        scores.append(float(score))
        labels.append(1.0 if is_churned else 0.0)

    return scores, labels


def _get_score_for_customer(
    health: CustomerHealth,
    churned_at: Optional[datetime],
    db: Session,
) -> float:
    """Return churn_risk_component at churn time, or current value as fallback."""
    if churned_at is not None:
        hist = (
            db.query(CustomerHealthHistory)
            .filter(
                CustomerHealthHistory.customer_health_id == health.id,
                CustomerHealthHistory.recorded_at <= churned_at,
            )
            .order_by(CustomerHealthHistory.recorded_at.desc())
            .first()
        )
        if hist is not None and hist.churn_risk_component is not None:
            return float(hist.churn_risk_component)
    return float(health.churn_risk_component or 50)


def _fit_isotonic(scores: list[float], labels: list[float]):
    """Fit and return an IsotonicRegression model."""
    import numpy as np
    from sklearn.isotonic import IsotonicRegression

    scores_arr = np.array(scores, dtype=float)
    labels_arr = np.array(labels, dtype=float)
    ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
    ir.fit(scores_arr, labels_arr)
    return ir


def _serialize_model(ir, scores: list[float], labels: list[float]) -> dict:
    """Serialize isotonic model to JSON-compatible dict.

    Schema matches what probability_updater._deserialize_model expects:
    {"breakpoints": [...], "probabilities": [...], "threshold_bands": {...}}
    """
    bps: list = ir.X_thresholds_.tolist()
    probs: list = ir.y_thresholds_.tolist()
    return {
        "breakpoints": bps,
        "probabilities": probs,
        "threshold_bands": dict(_DEFAULT_BANDS),
    }


def _compute_metrics(scores: list[float], labels: list[float], ir) -> dict:
    """Compute precision, recall, F1, AUC, optimal_threshold."""
    import numpy as np
    from sklearn.metrics import roc_auc_score

    scores_arr = np.array(scores, dtype=float)
    labels_arr = np.array(labels, dtype=float)
    probs = ir.predict(scores_arr)

    # Degenerate case — all same label
    if labels_arr.sum() == 0 or labels_arr.sum() == len(labels_arr):
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "auc": 0.0,
            "optimal_threshold": 0.5,
        }

    # AUC
    try:
        auc = float(roc_auc_score(labels_arr, probs))
    except Exception:
        auc = 0.0

    # Sweep thresholds for best F1
    best_f1 = -1.0
    best_precision = 0.0
    best_recall = 0.0
    best_threshold = 0.5

    for t in np.unique(probs):
        preds = (probs >= t).astype(float)
        tp = float((preds * labels_arr).sum())
        fp = float((preds * (1 - labels_arr)).sum())
        fn = float(((1 - preds) * labels_arr).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        if f1 > best_f1:
            best_f1 = f1
            best_precision = precision
            best_recall = recall
            best_threshold = float(t)

    return {
        "precision": best_precision,
        "recall": best_recall,
        "f1": best_f1,
        "auc": auc,
        "optimal_threshold": best_threshold,
    }


def _load_prev_active(org_id: int, db: Session) -> Optional[ChurnCalibrationModel]:
    """Return the currently active org model, or None."""
    return (
        db.query(ChurnCalibrationModel)
        .filter(
            ChurnCalibrationModel.organization_id == org_id,
            ChurnCalibrationModel.is_active == True,
        )
        .first()
    )


def _check_f1_drop(
    org_id: int,
    new_f1: float,
    prev_model: Optional[ChurnCalibrationModel],
) -> bool:
    """Return True and log a warning when F1 drops more than 0.10 vs previous model."""
    if prev_model is None:
        return False

    prev_f1 = float(prev_model.f1) if prev_model.f1 is not None else None
    if prev_f1 is None:
        return False

    dropped = new_f1 < prev_f1 - _F1_DROP_THRESHOLD
    if dropped:
        logger.warning(
            "CALIBRATION_F1_DROP org=%s prev_f1=%.4f new_f1=%.4f drop=%.4f",
            org_id,
            prev_f1,
            new_f1,
            prev_f1 - new_f1,
        )
    return dropped
