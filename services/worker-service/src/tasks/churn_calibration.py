"""
Celery tasks for weekly churn calibration — Phase 6.1 (M4.1).

Beat schedule (registered in celery_app.py):
- refit_all_orgs            → Mondays 07:45 UTC
- refit_global_calibration  → Daily 03:00 UTC
- purge_old_calibration_models → Sundays 03:30 UTC
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.database import get_db_session
from src.models import (
    ChurnBacktestRun,
    ChurnCalibrationModel,
    CustomerChurnEvent,
    CustomerHealth,
    Organization,
)
from src.services.calibration_refit import refit_org

logger = logging.getLogger(__name__)

# Minimum qualifying labels (non-auto-suggested) to trigger per-org refit.
_ORG_LABEL_THRESHOLD = 20
# Only customers active within this window contribute labels.
_LABEL_WINDOW_DAYS = 180
# Calibration models older than this are eligible for purge.
_PURGE_AFTER_DAYS = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_org_labels(org_id: int, db: Session) -> int:
    """Return count of non-auto-suggested churn events for the org (all time)."""
    return (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.source != "auto_suggested",
        )
        .count()
    )


def _all_org_ids(db: Session) -> list[int]:
    """Return all distinct organization IDs."""
    rows = db.query(Organization.id).all()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def refit_all_orgs() -> dict:
    """For each org with >= 20 non-auto-suggested labels, refit its calibration model.

    Beat: Mondays 07:45 UTC.
    Returns {"refit_count": N, "skipped": M}.
    """
    refit_count = 0
    skipped = 0

    with get_db_session() as db:
        org_ids = _all_org_ids(db)
        for org_id in org_ids:
            count = _count_org_labels(org_id, db)
            if count < _ORG_LABEL_THRESHOLD:
                skipped += 1
                logger.info(
                    "refit_all_orgs: org=%s skipped (labels=%s < %s)",
                    org_id, count, _ORG_LABEL_THRESHOLD,
                )
                continue

            try:
                result = refit_org(org_id, db)
                if result.get("skipped"):
                    skipped += 1
                else:
                    refit_count += 1
                    logger.info(
                        "refit_all_orgs: org=%s refit model_id=%s f1=%.4f f1_dropped=%s",
                        org_id, result["model_id"], result["f1"], result["f1_dropped"],
                    )
            except Exception as exc:
                logger.error(
                    "refit_all_orgs: org=%s FAILED — %s", org_id, exc, exc_info=True
                )
                # Continue with next org — one failure must not abort the batch.

    logger.info("refit_all_orgs: done refit_count=%s skipped=%s", refit_count, skipped)
    return {"refit_count": refit_count, "skipped": skipped}


def refit_global_calibration() -> dict:
    """Pool all orgs' non-auto-suggested labels into one global isotonic model.

    Stores result as organization_id=NULL. Deactivates previous global model.
    Beat: Daily 03:00 UTC.
    Returns {"global_model_id": id, "label_count": N}.
    """
    # Lazy imports — numpy/sklearn unavailable in Python 3.14 CI venv
    import numpy as np
    from sklearn.isotonic import IsotonicRegression

    with get_db_session() as db:
        cutoff = datetime.utcnow() - timedelta(days=_LABEL_WINDOW_DAYS)

        # Collect all qualifying churn events across all orgs
        events = (
            db.query(CustomerChurnEvent)
            .filter(CustomerChurnEvent.source != "auto_suggested")
            .all()
        )
        churned_keys: set[tuple] = {(e.organization_id, e.customer_email) for e in events}

        # All customers active in the last 180 days
        health_rows = (
            db.query(CustomerHealth)
            .filter(CustomerHealth.last_feedback_at >= cutoff)
            .all()
        )

        scores: list[float] = []
        labels: list[float] = []

        for h in health_rows:
            key = (h.organization_id, h.customer_email)
            scores.append(float(h.churn_risk_component or 50))
            labels.append(1.0 if key in churned_keys else 0.0)

        label_count = len(scores)
        positive_count = int(sum(labels))

        # Fit global model (even with few labels — identity fallback not needed here
        # because we're pooling across all orgs and may have very few)
        scores_arr = np.array(scores, dtype=float) if scores else np.array([0.0, 100.0])
        labels_arr = np.array(labels, dtype=float) if labels else np.array([0.0, 1.0])

        try:
            ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
            ir.fit(scores_arr, labels_arr)
            bps = ir.X_thresholds_.tolist()
            probs = ir.y_thresholds_.tolist()
        except Exception:
            # Identity fallback
            bps = list(range(0, 101))
            probs = [x / 100.0 for x in range(0, 101)]

        bands = {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85}
        mj = {"breakpoints": bps, "probabilities": probs, "threshold_bands": bands}

        # Deactivate previous global active model
        old_global = (
            db.query(ChurnCalibrationModel)
            .filter(
                ChurnCalibrationModel.organization_id == None,
                ChurnCalibrationModel.is_active == True,
            )
            .first()
        )
        if old_global is not None:
            old_global.is_active = False
            db.add(old_global)

        # Insert new global model
        new_global = ChurnCalibrationModel(
            organization_id=None,
            model_json=mj,
            label_count=label_count,
            positive_count=positive_count,
            precision=None,
            recall=None,
            f1=None,
            auc=None,
            threshold_bands=bands,
            fit_at=datetime.utcnow(),
            is_active=True,
        )
        db.add(new_global)
        db.commit()
        db.refresh(new_global)

    logger.info(
        "refit_global_calibration: global_model_id=%s label_count=%s",
        new_global.id, label_count,
    )
    return {"global_model_id": new_global.id, "label_count": label_count}


def purge_old_calibration_models() -> dict:
    """Delete ChurnCalibrationModel rows where is_active=False AND fit_at < now()-90d.

    Beat: Sundays 03:30 UTC.
    Returns {"deleted": N}.
    """
    cutoff = datetime.utcnow() - timedelta(days=_PURGE_AFTER_DAYS)

    with get_db_session() as db:
        old_rows = (
            db.query(ChurnCalibrationModel)
            .filter(
                ChurnCalibrationModel.is_active == False,
                ChurnCalibrationModel.fit_at < cutoff,
            )
            .all()
        )
        for row in old_rows:
            db.delete(row)
        db.commit()

    logger.info("purge_old_calibration_models: deleted=%s", len(old_rows))
    return {"deleted": len(old_rows)}
