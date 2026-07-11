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

_DEFAULT_CLASSIFIER_TYPE = "sentiment"
_CLASSIFIER_TYPES: tuple[str, ...] = ("sentiment", "category")
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


_category_categorizer_cache = None


def _category_categorizers():
    """Lazily construct + process-cache (PainPointCategorizer, FeatureRequestCategorizer)
    instances — mirrors _get_redis()'s caching pattern. No add_custom_categories() call: the
    incumbent is deliberately un-merged, built-in-vocab-only, matching the analysis-engine
    keyword path's default construction (core.py never calls add_custom_categories either —
    see PRD 'Category incumbent for the A/B eval' note). Lazy import keeps this module
    importable without the analysis-engine's heavier analyzer/__init__.py import chain at
    module load time (Py3.14 CI target)."""
    global _category_categorizer_cache
    if _category_categorizer_cache is None:
        from analyzer.categorizer import FeatureRequestCategorizer, PainPointCategorizer
        _category_categorizer_cache = (PainPointCategorizer(), FeatureRequestCategorizer())
    return _category_categorizer_cache


def _build_category_incumbent_predict() -> Callable[[str], str]:
    """Build a deterministic incumbent predictor from the production keyword categorizers,
    covering the built-in category vocab only. For a given text, run BOTH categorizers and
    return the label with the strictly higher confidence; an exact tie (including the common
    all-zero-match case, where both categorizers fall through to their own unrelated
    defaults) breaks deterministically toward the pain-point categorizer's result."""
    pain_point_categorizer, feature_categorizer = _category_categorizers()

    def _predict(text: str) -> str:
        pain_result = pain_point_categorizer.categorize(text)
        feature_result = feature_categorizer.categorize(text)
        if feature_result.confidence > pain_result.confidence:
            return feature_result.category
        return pain_result.category

    return _predict


def _built_in_category_vocab() -> frozenset:
    """Union of both keyword categorizers' built-in category names — the label space the
    keyword incumbent can structurally emit. Used to compute the fair-A/B eval label subset
    (PRD critique #3): derive_labels(dataset) ∩ this set. NOT a fixed tuple defined here —
    read live off the categorizer instances so it can never drift from categorizer.py."""
    pain_point_categorizer, feature_categorizer = _category_categorizers()
    return frozenset(pain_point_categorizer.CATEGORIES) | frozenset(feature_categorizer.CATEGORIES)


def _round_or_none(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None


def _skip_result(reason: str, **extra) -> dict:
    """Convenience dict for a skipped retrain_org run — no "promoted"/"retained" key,
    per the spec's return-shape contract."""
    return {"decision": "skipped", "skipped": True, "reason": reason, **extra}


def _decision_result(decision: str, **extra) -> dict:
    """Convenience dict for a promoted/retained retrain_org run — sets a boolean flag
    named after the decision (e.g. "promoted": True) alongside "decision"."""
    return {"decision": decision, decision: True, **extra}


def _promote(org_id: int, dataset: list, result, train_classifier: Callable, db: Session,
             classifier_type: str) -> int:
    """Atomic promotion, single transaction (caller commits): train the FINAL
    production artifact on ALL rows (not just the core's internal train-split —
    that one never sees the full data), deactivate the prior active
    (org, classifier_type) row, insert the new active row, flush to populate its id.
    Never a window with 0 or 2 active rows for the same (org, classifier_type).

    precision/recall/accuracy are not exposed by the core's leakage-free EvalResult
    (only macro_f1 is) — left nullable/unset here rather than re-deriving a second,
    out-of-band metrics pass over the holdout (see worker-trainer-and-schedule
    report deviations).
    """
    artifact = train_classifier(dataset)

    prev_active = (
        db.query(OrgClassifierModel)
        .filter(
            OrgClassifierModel.organization_id == org_id,
            OrgClassifierModel.classifier_type == classifier_type,
            OrgClassifierModel.is_active == True,  # noqa: E712
        )
        .first()
    )
    if prev_active is not None:
        prev_active.is_active = False
        db.add(prev_active)
        db.flush()  # force the deactivating UPDATE to hit the DB before the new
        # active row is INSERTed below. SQLAlchemy's unit-of-work otherwise emits
        # INSERTs before UPDATEs within a single flush, which would transiently
        # violate Postgres' IMMEDIATE partial-unique index
        # uq_org_classifier_one_active (organization_id, classifier_type WHERE
        # is_active) — the new row would INSERT while the old row is still
        # is_active=TRUE. This extra flush does not commit; the deactivate+insert
        # remains one atomic transaction (caller commits once).

    new_model = OrgClassifierModel(
        organization_id=org_id,
        classifier_type=classifier_type,
        model_json=artifact,
        label_count=len(dataset),
        precision=None,
        recall=None,
        macro_f1=_round_or_none(result.challenger_macro_f1),
        accuracy=None,
        fit_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(new_model)
    db.flush()  # populate new_model.id before the eval-run FK
    return new_model.id


def _insert_eval_run(org_id: int, model_id: Optional[int], result, duration_ms: int, db: Session,
                      classifier_type: str) -> None:
    """Insert the one org_classifier_eval_runs row every retrain_org run writes
    (except a lock-miss, which writes nothing — see module docstring)."""
    eval_run = OrgClassifierEvalRun(
        organization_id=org_id,
        classifier_model_id=model_id,
        classifier_type=classifier_type,
        incumbent_macro_f1=_round_or_none(result.incumbent_macro_f1),
        challenger_macro_f1=_round_or_none(result.challenger_macro_f1),
        macro_f1_delta=_round_or_none(result.macro_f1_delta),
        decision=result.decision,
        n=result.n,
        duration_ms=duration_ms,
        notes=result.notes,
    )
    db.add(eval_run)


def retrain_org(org_id: int, db: Session, classifier_type: str = _DEFAULT_CLASSIFIER_TYPE) -> dict:
    """Retrain the corrections classifier (sentiment or category) for a single org.

    1. Acquire a per-(classifier_type, org) Redis advisory lock (non-blocking) — an
       overlapping refit already owns this org+type: write nothing, return
       {"skipped": True, "reason": "locked"}.
    2. Build the org's dataset (aspect B's dataset builder).
    3. evaluate() the challenger against a live incumbent predictor, leakage-free (the
       core trains the challenger itself, only on its own train-split/per-fold).
    4. Only when decision == "promoted": atomically promote the FINAL production
       artifact (see _promote — trained on ALL rows, not just the core's internal
       train-split).
    5. Always insert one org_classifier_eval_runs row keyed off the decision, then
       commit once (single transaction covering both the model swap and the
       eval-run insert).

    Below-gate / worse-challenger / small-holdout (decision in {"skipped", "retained"})
    write zero model rows. classifier_type selects which correction bucket / incumbent /
    lock this call operates on; "sentiment" is the byte-stable default.
    """
    r = _get_redis()
    lock = r.lock(
        f"lock:classifier_refit:{classifier_type}:{org_id}",
        timeout=_LOCK_TIMEOUT_SECONDS, blocking=False,
    )

    if not lock.acquire(blocking=False):
        logger.info("retrain_org: org=%s type=%s already refitting, skipping", org_id, classifier_type)
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

        model_id: Optional[int] = None
        if result.decision == "promoted":
            model_id = _promote(org_id, dataset, result, train_classifier, db, classifier_type)

        _insert_eval_run(org_id, model_id, result, duration_ms, db, classifier_type)
        db.commit()

        if result.decision == "skipped":
            logger.info(
                "retrain_org: org=%s type=%s skipped (below_min_labels) n=%s",
                org_id, classifier_type, result.n,
            )
            return _skip_result("below_min_labels", n=result.n, notes=result.notes)

        logger.info(
            "retrain_org: org=%s type=%s decision=%s model_id=%s n=%s",
            org_id, classifier_type, result.decision, model_id, result.n,
        )
        return _decision_result(result.decision, model_id=model_id, n=result.n, notes=result.notes)
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass


def retrain_all_orgs() -> dict:
    """Weekly driver: retrain every org's classifier for BOTH types (sentiment, category),
    then purge old inactive artifacts once (folded — no separate beat slot, not type-scoped).

    Per-(type, org) try/except isolation: one (type, org) combination's exception is logged
    and skipped, it never aborts the rest of the batch — same shared-session
    rollback-on-error discipline as before, now applied per (classifier_type, org_id) pair.

    Beat: Mondays 06:30 UTC. Returns {"trained": n, "promoted": m, "skipped": k} — tallies now
    cover BOTH classifier types combined (a 3-org run does up to 6 retrain_org calls).
    """
    trained = 0
    promoted = 0
    skipped = 0

    with get_db_session() as db:
        org_ids = _all_org_ids(db)
        for classifier_type in _CLASSIFIER_TYPES:
            for org_id in org_ids:
                try:
                    result = retrain_org(org_id, db, classifier_type=classifier_type)
                except Exception:
                    logger.error(
                        "retrain_all_orgs: org=%s type=%s FAILED", org_id, classifier_type,
                        exc_info=True,
                    )
                    # This db session is shared across every (type, org) in the batch. A
                    # failed flush/commit (e.g. the promotion UniqueViolation above,
                    # or any other per-org DB error) leaves the session needing a
                    # rollback; without it, the NEXT iteration's first DB operation raises
                    # sqlalchemy.exc.PendingRollbackError and the whole batch cascades.
                    db.rollback()
                    continue

                if result.get("skipped"):
                    skipped += 1
                else:
                    trained += 1
                    if result.get("promoted"):
                        promoted += 1

    purge_result = purge_old_classifier_models()
    logger.info(
        "retrain_all_orgs: done trained=%s promoted=%s skipped=%s purged=%s",
        trained, promoted, skipped, purge_result.get("deleted"),
    )
    return {"trained": trained, "promoted": promoted, "skipped": skipped}


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
