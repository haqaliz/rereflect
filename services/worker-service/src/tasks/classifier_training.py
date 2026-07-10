"""
Celery tasks for weekly per-org sentiment corrections classifier retraining —
worker-trainer-and-schedule aspect (M5.2 per-org-corrections-classifier).

Beat schedule (registered in celery_app.py):
- retrain_all_orgs → Mondays 06:30 UTC (folds in purge_old_classifier_models after
  the loop — no separate beat slot)

Mirrors tasks/churn_calibration.py + services/calibration_refit.py conventions:
- versioned artifact + atomic active-model swap (deactivate prev active -> insert new
  is_active row -> flush (populate id) -> insert eval-run -> commit; never a window
  with 0 or 2 active rows for the same (org, classifier_type)).
- per-org Redis advisory lock, mirroring tasks/analysis.py's `_get_redis()` +
  `r.lock(...)` pattern (here keyed per-org: lock:classifier_refit:{org_id}).
- a folded purge (mirrors purge_old_calibration_models, no separate beat slot).

This module is the ONLY writer of org_classifier_models. It does not touch
predict-at-ingest, API, or UI.

CPU-only / lazy heavy imports: sklearn/numpy live entirely inside the
analysis-engine core (analyzer.corrections_classifier.trainer.train_classifier) and
are imported lazily there, only when actually training. This module has ZERO
module-level sklearn/numpy imports, and does not import the core at module top
either — everything from analyzer.corrections_classifier.* is imported lazily
inside retrain_org, so this module stays importable in the worker-service's
Python 3.14 CI target (no ML wheels there).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import redis
from sqlalchemy.orm import Session

from src.config import get_redis_url
from src.database import get_db_session
from src.models import Organization, OrgClassifierEvalRun, OrgClassifierModel

logger = logging.getLogger(__name__)

_CLASSIFIER_TYPE = "sentiment"
_PURGE_AFTER_DAYS = 90
_LOCK_TIMEOUT_SECONDS = 600

# Redis client for per-org advisory locking — mirrors tasks/analysis.py's _get_redis().
_redis_client = None


def _get_redis():
    """Get or create Redis client for per-org classifier-refit locking."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(get_redis_url(0))
    return _redis_client


def _all_org_ids(db: Session) -> list[int]:
    """Return all distinct organization IDs (mirrors churn_calibration._all_org_ids)."""
    rows = db.query(Organization.id).all()
    return [r[0] for r in rows]


def _build_incumbent_predict() -> Callable[[str], str]:
    """Build a live incumbent predictor from the production SentimentAnalyzer
    (default provider: VADER) — lazy import, reuses tasks/analysis.py's cached
    get_sentiment_analyzer() factory rather than duplicating construction/fallback
    logic."""
    from src.tasks.analysis import get_sentiment_analyzer

    analyzer = get_sentiment_analyzer("vader")

    def _predict(text: str) -> str:
        return analyzer.analyze(text)["label"]

    return _predict


def _round_or_none(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None


def _skip_result(reason: str, **extra) -> dict:
    """Convenience dict for a skipped retrain_org run — no "promoted"/"retained" key,
    per the spec's return-shape contract."""
    return {"decision": "skipped", "skipped": True, "reason": reason, **extra}


def retrain_org(org_id: int, db: Session) -> dict:
    """Retrain the sentiment corrections classifier for a single org.

    1. Acquire a per-org Redis advisory lock (non-blocking) — an overlapping refit
       already owns this org: write nothing, return {"skipped": True, "reason": "locked"}.
    2. Build the org's sentiment dataset (aspect B's dataset builder).
    3. evaluate() the challenger against a live incumbent predictor, leakage-free (the
       core trains the challenger itself, only on its own train-split/per-fold).
    4. Always insert one org_classifier_eval_runs row keyed off the decision.
    5. Only when decision == "promoted": train the FINAL production artifact on ALL
       rows (train_classifier(dataset)) and persist it via an atomic swap (deactivate
       prior active row, insert new active row, flush to populate its id before the
       eval-run FK, commit as one transaction).

    Below-gate (decision == "skipped") writes zero model rows.

    Below-gate handling (Phase 3) is implemented here; promote/retained handling is
    added in later phases.
    """
    r = _get_redis()
    lock = r.lock(f"lock:classifier_refit:{org_id}", timeout=_LOCK_TIMEOUT_SECONDS, blocking=False)

    if not lock.acquire(blocking=False):
        logger.info("retrain_org: org=%s already refitting, skipping", org_id)
        return _skip_result("locked")

    try:
        start = time.monotonic()

        # Lazy imports — the core owns sklearn/numpy; this module stays CPU-only-safe.
        from analyzer.corrections_classifier.dataset import build_sentiment_dataset
        from analyzer.corrections_classifier.evaluate import evaluate
        from analyzer.corrections_classifier.labels import MARGIN, MIN_LABELS
        from analyzer.corrections_classifier.trainer import train_classifier

        dataset = build_sentiment_dataset(org_id, db)
        incumbent_predict = _build_incumbent_predict()

        result = evaluate(
            dataset,
            incumbent_predict,
            train_fn=train_classifier,
            min_labels=MIN_LABELS,
            margin=MARGIN,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        if result.decision == "skipped":
            eval_run = OrgClassifierEvalRun(
                organization_id=org_id,
                classifier_model_id=None,
                classifier_type=_CLASSIFIER_TYPE,
                incumbent_macro_f1=_round_or_none(result.incumbent_macro_f1),
                challenger_macro_f1=_round_or_none(result.challenger_macro_f1),
                macro_f1_delta=_round_or_none(result.macro_f1_delta),
                decision=result.decision,
                n=result.n,
                duration_ms=duration_ms,
                notes=result.notes,
            )
            db.add(eval_run)
            db.commit()
            return _skip_result("below_min_labels", n=result.n, notes=result.notes)

        # Promote/retained handling — added in later phases.
        raise NotImplementedError(f"retrain_org: decision={result.decision!r} not yet handled")
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass


def retrain_all_orgs() -> dict:
    """Weekly driver: retrain every org's sentiment classifier, then purge old
    inactive artifacts.

    Beat: Mondays 06:30 UTC.
    Stub — implemented phase by phase via TDD (Phase 7).
    """
    return {}


def purge_old_classifier_models() -> dict:
    """Delete OrgClassifierModel rows where is_active=False AND fit_at < now()-90d.

    Folded into retrain_all_orgs (no separate beat slot).
    Mirrors churn_calibration.purge_old_calibration_models.
    Returns {"deleted": N}.
    """
    cutoff = datetime.utcnow() - timedelta(days=_PURGE_AFTER_DAYS)

    with get_db_session() as db:
        old_rows = (
            db.query(OrgClassifierModel)
            .filter(
                OrgClassifierModel.is_active == False,  # noqa: E712
                OrgClassifierModel.fit_at < cutoff,
            )
            .all()
        )
        for row in old_rows:
            db.delete(row)
        db.commit()

    logger.info("purge_old_classifier_models: deleted=%s", len(old_rows))
    return {"deleted": len(old_rows)}
