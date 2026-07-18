"""
Probability updater service — Phase 3.1.

Recomputes churn probability for a customer after their CustomerHealth row
is refreshed by update_customer_health(). Pure logic: no Celery, no FastAPI.

Entry point
-----------
    update(org_id, customer_email, db) -> None

The function is idempotent; it short-circuits via a hysteresis guard when
the churn_risk_component has moved fewer than 2 points since the last history
snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.models import ChurnCalibrationModel, CustomerHealth, CustomerHealthHistory

logger = logging.getLogger(__name__)

# Minimum point-delta that triggers a recompute.
_HYSTERESIS_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Internal dataclass mirroring backend-api's CalibrationModel (no import)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Model:
    """Deserialized form of ChurnCalibrationModel.model_json."""

    breakpoints: list
    probabilities: list
    threshold_bands: dict
    label_count: int
    positive_count: int
    db_id: Optional[int]  # None when using identity fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update(org_id: int, customer_email: str, db: Session) -> None:
    """Recompute churn probability for a customer. Idempotent.

    Steps:
    1. Load CustomerHealth row (return early if absent).
    2. Hysteresis guard: skip if churn_risk_component changed < 2 pts vs most
       recent history snapshot (recompute unconditionally when no history).
    3. Load active calibration model (org → global → identity).
    4. Predict (p, low, high) via isotonic interpolation + bootstrap CI.
    5. Derive time_to_churn_bucket from probability × sentiment_trend.
    6. Persist updated columns; do NOT touch risk_level.
    """
    health = _load_health(org_id, customer_email, db)
    if health is None:
        return

    if _should_skip(health, db):
        return

    model = _load_active_model(org_id, db)
    p, low, high = _predict_with_interval(health.churn_risk_component or 0, model)
    sentiment_trend = _compute_sentiment_trend(health, db)
    bucket = _derive_timeline_bucket(p, sentiment_trend)

    health.churn_probability = round(p, 4)
    health.churn_probability_low = round(low, 4)
    health.churn_probability_high = round(high, 4)
    health.time_to_churn_bucket = bucket
    health.calibration_model_id = model.db_id
    health.probability_computed_at = datetime.utcnow()

    db.add(health)
    db.commit()

    # Fire churn-probability-threshold automation rules (run_playbook only) —
    # isolated worker mirror of backend-api's AutomationEngine, see
    # src.services.automation_churn_trigger for why this is a focused
    # evaluator rather than a full engine mirror. Must never break the
    # probability update itself.
    try:
        from src.services.automation_churn_trigger import evaluate_churn_probability_triggers
        evaluate_churn_probability_triggers(org_id, customer_email, float(p), db)
    except Exception as exc:
        logger.warning("churn playbook trigger failed for %s: %s", customer_email, exc)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_health(org_id: int, customer_email: str, db: Session) -> Optional[CustomerHealth]:
    """Return the CustomerHealth row or None if not found."""
    return (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.customer_email == customer_email,
        )
        .first()
    )


def _should_skip(health: CustomerHealth, db: Session) -> bool:
    """Return True when hysteresis guard says no recompute needed.

    Skips when the most recent history snapshot exists and the
    churn_risk_component changed by < _HYSTERESIS_THRESHOLD points.
    Recomputes unconditionally when there is no prior history.
    """
    latest_history = (
        db.query(CustomerHealthHistory)
        .filter(CustomerHealthHistory.customer_health_id == health.id)
        .order_by(CustomerHealthHistory.recorded_at.desc())
        .first()
    )

    if latest_history is None:
        return False  # No history → always recompute

    prev_component = latest_history.churn_risk_component
    if prev_component is None:
        return False

    current_component = health.churn_risk_component or 0
    delta = abs(current_component - prev_component)
    return delta < _HYSTERESIS_THRESHOLD


def _load_active_model(org_id: int, db: Session) -> _Model:
    """Load active calibration model: org → global → identity fallback."""
    # 1. Try org-specific active model
    db_model = (
        db.query(ChurnCalibrationModel)
        .filter(
            ChurnCalibrationModel.organization_id == org_id,
            ChurnCalibrationModel.is_active == True,
        )
        .first()
    )

    # 2. Fall back to global active model
    if db_model is None:
        db_model = (
            db.query(ChurnCalibrationModel)
            .filter(
                ChurnCalibrationModel.organization_id == None,
                ChurnCalibrationModel.is_active == True,
            )
            .first()
        )

    # 3. Fall back to identity model
    if db_model is None:
        return _identity_model()

    return _deserialize_model(db_model)


def _deserialize_model(db_row: ChurnCalibrationModel) -> _Model:
    """Deserialize model_json from DB into _Model. Falls back to identity on error."""
    try:
        mj = db_row.model_json
        if not isinstance(mj, dict):
            raise ValueError("model_json is not a dict")

        breakpoints = mj["breakpoints"]
        probabilities = mj["probabilities"]

        if not breakpoints or not probabilities:
            raise ValueError("Empty breakpoints or probabilities")

        bands = db_row.threshold_bands or {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85}

        return _Model(
            breakpoints=list(breakpoints),
            probabilities=list(probabilities),
            threshold_bands=dict(bands),
            label_count=db_row.label_count,
            positive_count=db_row.positive_count,
            db_id=db_row.id,
        )
    except Exception as exc:
        logger.warning("Corrupted model_json for ChurnCalibrationModel id=%s: %s. Falling back to identity.", db_row.id, exc)
        return _identity_model()


def _identity_model() -> _Model:
    """Linear identity fallback: score / 100 → probability."""
    breakpoints = list(range(0, 101, 1))
    probabilities = [bp / 100.0 for bp in breakpoints]
    return _Model(
        breakpoints=breakpoints,
        probabilities=probabilities,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        label_count=0,
        positive_count=0,
        db_id=None,
    )


def _predict_with_interval(
    score: int,
    model: _Model,
    n_bootstrap: int = 200,
    ci: float = 0.90,
) -> tuple:
    """Return (point_estimate, lower_bound, upper_bound) via bootstrap CI."""
    p = _interpolate(float(score), model.breakpoints, model.probabilities)
    low, high = _bootstrap_ci(score, model, n_bootstrap, ci)
    return (p, low, high)


def _interpolate(score: float, breakpoints: list, probabilities: list) -> float:
    """Linear interpolation between breakpoints; clamp outside range."""
    bps = breakpoints
    probs = probabilities

    if score <= bps[0]:
        return float(probs[0])
    if score >= bps[-1]:
        return float(probs[-1])

    lo, hi = 0, len(bps) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if bps[mid] <= score:
            lo = mid
        else:
            hi = mid

    x0, x1 = bps[lo], bps[hi]
    y0, y1 = probs[lo], probs[hi]
    if x1 == x0:
        return float(y0)
    t = (score - x0) / (x1 - x0)
    return float(y0 + t * (y1 - y0))


def _bootstrap_ci(
    score: int,
    model: _Model,
    n_bootstrap: int,
    ci: float,
) -> tuple:
    """Bootstrap 90% CI by resampling breakpoints/probabilities as surrogate data."""
    import numpy as np
    from sklearn.isotonic import IsotonicRegression

    rng = np.random.default_rng(seed=0)
    scores_arr = np.array(model.breakpoints, dtype=float)
    labels_arr = np.array(model.probabilities, dtype=float)
    n = len(scores_arr)
    boot_preds: list = []

    p_point = _interpolate(float(score), model.breakpoints, model.probabilities)

    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        s_boot = scores_arr[idx]
        l_boot = labels_arr[idx]

        if l_boot.sum() == 0 or l_boot.sum() == n:
            boot_preds.append(p_point)
            continue

        ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
        try:
            ir.fit(s_boot, l_boot)
            pred = float(ir.predict([float(score)])[0])
        except Exception:
            pred = p_point
        boot_preds.append(pred)

    alpha = 1.0 - ci
    lower = float(np.percentile(boot_preds, 100 * alpha / 2))
    upper = float(np.percentile(boot_preds, 100 * (1 - alpha / 2)))
    return (lower, upper)


def _compute_sentiment_trend(health: CustomerHealth, db: Session) -> float:
    """Compute sentiment trend as delta between current and previous history snapshot.

    Returns a float in approximately [-1, 1]:
    - Negative: sentiment is declining (higher churn urgency).
    - Zero: no data or no change.
    """
    current = health.sentiment_component or 50

    latest_history = (
        db.query(CustomerHealthHistory)
        .filter(CustomerHealthHistory.customer_health_id == health.id)
        .order_by(CustomerHealthHistory.recorded_at.desc())
        .first()
    )

    if latest_history is None or latest_history.sentiment_component is None:
        return 0.0

    prev = latest_history.sentiment_component
    # Normalise the delta to [-1, 1] range (components are 0–100)
    return (current - prev) / 100.0


def _derive_timeline_bucket(p: float, sentiment_trend: float) -> str:
    """Classify time-to-churn into five buckets matching PRD spec."""
    if p >= 0.85 or (p >= 0.70 and sentiment_trend <= -0.4):
        return "immediate"
    if p >= 0.70:
        return "2w"
    if p >= 0.50:
        return "2-4w"
    if p >= 0.30:
        return "1-3m"
    return "low"
