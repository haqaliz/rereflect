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


def retrain_org(org_id: int, db: Session) -> dict:
    """Retrain the sentiment corrections classifier for a single org.

    Stub — implemented phase by phase via TDD (Phase 3+).
    """
    return {}


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
