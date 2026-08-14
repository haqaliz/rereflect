"""
Celery tasks for weekly per-org churn classifier retraining — worker-churn-
trainer-and-schedule aspect (M5.3 per-org-churn-model).

Beat schedule (registered in celery_app.py):
- retrain_all_orgs → Mondays 06:00 UTC (before retrain-classifier-weekly 06:30).

Schedule intent: the ML challenger's incumbent is the org's active calibrated
heuristic. The incumbent's weekly per-org refit (refit-churn-calibration-weekly)
runs Mondays 07:45 UTC — AFTER this task — and the global incumbent refits
daily 03:00 UTC. So this task at week N+1 always evaluates against the incumbent
as refit in week N: the challenger must beat the post-refit incumbent of the
previous week, never a stale one.

CONSECUTIVE-RUNS PROMOTION (plan amendment 2026-08-14, gate-study verdict):
the study's honest-limits finding answered PRD OQ2 — at the 200-label crossover
only 57% of pooled simulated orgs cleared the +0.02 macro-F1 bar on a SINGLE
run (high variance). Therefore promotion requires two consecutive weekly
clears, recorded per run:

- run 1: evaluate_churn clears +0.02 → eval run decision='promoted_candidate'
  (no model swap, no promote);
- run 2 (next week): clears again → promote: train the final artifact on ALL
  rows, deactivate the prior active row, INSERT the new active row (flush
  BEFORE INSERT — partial unique index uq_org_classifier_one_active), eval run
  decision='promoted';
- any EVALUABLE non-clear after a candidate → eval run keeps its true decision
  and delta, notes gain 'streak broken'; never promotes; the next clear starts
  a fresh candidate;
- below-gate / single-class weeks are NO-SIGNAL (no true delta): decision
  'skipped', never raise, and they do NOT break the streak;
- the autopromote hold clears both runs' state: a held would-promote writes
  decision='held' (with the real delta/n) and neither marks a candidate nor
  promotes.

Streak state lives entirely in the org_classifier_eval_runs table (the most
recent evaluable run for (org, 'churn')), so it survives worker restarts; the
single db.commit() covering the model swap + eval run makes each run atomic.

This module is the ONLY writer of org_classifier_models for classifier_type
'churn'. It mirrors tasks/classifier_training.py conventions (lock, hold,
flush-before-INSERT).

CPU-only / lazy heavy imports: sklearn/numpy live entirely inside the
analysis-engine core (analyzer.churn_classifier.trainer) and are imported
lazily there. This module has ZERO module-level sklearn/numpy imports and does
not import the core at module top either — everything from
analyzer.churn_classifier.* is imported lazily inside the functions, so this
module stays importable in the worker-service's Python 3.14 CI target (no ML
wheels there).
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace as _dataclasses_replace
from datetime import datetime, timedelta
from typing import Callable, Optional

import redis
from celery import shared_task
from sqlalchemy.orm import Session

from src.config import get_redis_url
from src.database import get_db_session
from src.models import (
    CrmEnrichment,
    CustomerChurnEvent,
    CustomerHealth,
    CustomerHealthHistory,
    CustomerUsage,
    CustomerUsageHistory,
    FeedbackItem,
    OrgAIConfig,
    OrgClassifierEvalRun,
    OrgClassifierModel,
    Organization,
)

logger = logging.getLogger(__name__)

_CHURN_CLASSIFIER_TYPE = "churn"

# Parity with calibration_refit._MIN_LABELS / churn_calibration._ORG_LABEL_THRESHOLD
# (the sweep gate: at least this many qualifying events before the org is worth
# a retrain call). The in-window dataset gate is the core's MIN_LABELS.
_ORG_LABEL_THRESHOLD = 20
_LABEL_WINDOW_DAYS = 180
_PURGE_AFTER_DAYS = 90
_LOCK_TIMEOUT_SECONDS = 600

# Redis client for per-org advisory locking — mirrors tasks/classifier_training.py.
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


def _count_org_labels(org_id: int, db: Session) -> int:
    """Count of non-auto-suggested churn events for the org (all time) —
    mirrors churn_calibration._count_org_labels (calibrator label semantics)."""
    return (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.source != "auto_suggested",
        )
        .count()
    )


def _round_or_none(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None


def _skip_result(reason: str, **extra) -> dict:
    """Convenience dict for a skipped retrain_org run — no "promoted" key,
    per the spec's return-shape contract."""
    return {"decision": "skipped", "skipped": True, "reason": reason, **extra}


def _decision_result(decision: str, **extra) -> dict:
    """Convenience dict for a real retrain_org run — sets a boolean flag named
    after the decision (e.g. "promoted": True) alongside "decision"."""
    return {"decision": decision, decision: True, **extra}


# ---------------------------------------------------------------------------
# OrgAIConfig column reads (getattr-defensive — no crash pre-migration)
# ---------------------------------------------------------------------------


def _config_held(config) -> bool:
    """Defensive read of churn_autopromote_hold (M5.2 convention): an object
    without the column (pre-migration DB) is treated as not held, never raises."""
    return bool(getattr(config, "churn_autopromote_hold", False))


def _config_mode(config) -> str:
    """Defensive read of churn_classifier_mode (M5.2 convention): an object
    without the column is treated as 'off', never raises."""
    return getattr(config, "churn_classifier_mode", None) or "off"


def _churn_config(org_id: int, db: Session) -> tuple[bool, str]:
    """Row-locked read (.with_for_update()) of the org's OrgAIConfig churn
    columns, taken inside retrain_org's single transaction so a concurrently-
    committed hold-flip is observed before the promote-or-not decision.
    .with_for_update() is a safe no-op on SQLite (ignored) — only matters on
    Postgres. No OrgAIConfig row for the org -> (False, 'off') (column defaults).
    Returns (held, mode)."""
    config = (
        db.query(OrgAIConfig)
        .filter(OrgAIConfig.organization_id == org_id)
        .with_for_update()
        .first()
    )
    if config is None:
        return False, "off"
    return _config_held(config), _config_mode(config)


# ---------------------------------------------------------------------------
# Dataset assembly (caller side of the core's contract)
# ---------------------------------------------------------------------------
#
# The core's fetch_churn_rows LEFT JOINs CURRENT health/usage values onto the
# qualifying churn events. Per the core's dataset contract the CALLER attaches,
# before rows_to_dataset runs: (1) the nearest-at-label-date health/usage
# HISTORY snapshot values, (2) feedback aggregates, (3) renewal proximity —
# mirroring how the calibrator looks up customer_health_history in Python
# rather than SQL. Label-0 rows (non-churned customers active in the window)
# are also the caller's job.


def _coerce_datetime(value):
    """fetch_churn_rows returns churned_at in whatever the driver produced
    (sqlite: an ISO string; postgres: a datetime). Normalize to a naive
    datetime so history lookups compare against a real DateTime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    return value


def _nearest_health_history(db: Session, health_id: int, as_of: datetime):
    """Nearest customer_health_history snapshot at or before `as_of` (the label
    date), or None. Mirrors calibration_refit._get_score_for_customer's lookup."""
    return (
        db.query(CustomerHealthHistory)
        .filter(
            CustomerHealthHistory.customer_health_id == health_id,
            CustomerHealthHistory.recorded_at <= as_of,
        )
        .order_by(CustomerHealthHistory.recorded_at.desc())
        .first()
    )


def _nearest_usage_history(db: Session, org_id: int, email: str, as_of: datetime):
    """Nearest customer_usage_history snapshot at or before `as_of`, or None."""
    return (
        db.query(CustomerUsageHistory)
        .filter(
            CustomerUsageHistory.organization_id == org_id,
            CustomerUsageHistory.customer_email == email,
            CustomerUsageHistory.snapshot_date <= as_of.date(),
        )
        .order_by(CustomerUsageHistory.snapshot_date.desc())
        .first()
    )


def _attach_history(org_id: int, row: dict, db: Session, as_of: datetime) -> None:
    """Overwrite a positive row's health/usage feature fields with the nearest
    history-snapshot values at/before the label date. Only non-None history
    fields override (calibrator fallback semantics: a missing field keeps the
    current joined value, never defaulted to 50)."""
    health = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.customer_email == row["customer_email"],
        )
        .order_by(CustomerHealth.id.desc())
        .first()
    )
    if health is None:
        return
    hist = _nearest_health_history(db, health.id, as_of)
    if hist is not None:
        for field in (
            "health_score",
            "churn_risk_component",
            "sentiment_component",
            "resolution_component",
            "frequency_component",
            "usage_component",
            "crm_component",
            "risk_level",
        ):
            value = getattr(hist, field)
            if value is not None:
                row[field] = value

    usage_hist = _nearest_usage_history(db, org_id, row["customer_email"], as_of)
    if usage_hist is not None:
        for field in (
            "active_days_7d",
            "active_days_14d",
            "active_days_30d",
            "login_count_30d",
            "usage_score",
            "usage_trend_state",
            "usage_trend_pct",
        ):
            value = getattr(usage_hist, field)
            if value is not None:
                row[field] = value


def _feedback_aggregates(org_id: int, email: str, db: Session,
                         as_of: Optional[datetime] = None) -> dict:
    """Feedback aggregates over the 30 days ENDING at `as_of` (the label date;
    now for label-0 rows). Post-label feedback is excluded — leakage-free.

    sentiment_trend mirrors production's compute_sentiment_trend lookback shape
    (avg sentiment last 7d minus the 7d before that), anchored at `as_of`;
    0 when either half has no signal. All aggregates default to 0 ("no signal")
    per the core's missing_snapshot_defaults.
    """
    end = as_of or datetime.utcnow()
    start = end - timedelta(days=30)

    items = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.customer_email == email,
            FeedbackItem.created_at >= start,
            FeedbackItem.created_at < end,
        )
        .all()
    )

    count = len(items)
    sentiments = [i.sentiment_score for i in items if i.sentiment_score is not None]
    churn_risks = [i.churn_risk_score for i in items if i.churn_risk_score is not None]
    urgent = sum(1 for i in items if i.is_urgent)

    recent = [i.sentiment_score for i in items
              if i.sentiment_score is not None and i.created_at >= end - timedelta(days=7)]
    previous = [i.sentiment_score for i in items
                if i.sentiment_score is not None
                and i.created_at >= end - timedelta(days=14)
                and i.created_at < end - timedelta(days=7)]

    return {
        "count_30d": float(count),
        "avg_sentiment": float(sum(sentiments) / len(sentiments)) if sentiments else 0.0,
        "sentiment_trend": (sum(recent) / len(recent) - sum(previous) / len(previous))
        if recent and previous else 0.0,
        "urgent_share": float(urgent / count) if count else 0.0,
        "avg_churn_risk": float(sum(churn_risks) / len(churn_risks)) if churn_risks else 0.0,
    }


def _renewal_proximity(org_id: int, email: str, db: Session,
                       as_of: Optional[datetime] = None) -> Optional[float]:
    """Days from `as_of` to the customer's CRM renewal date (CrmEnrichment),
    or None when absent (the core defaults the field to -1)."""
    enrichment = (
        db.query(CrmEnrichment)
        .filter(
            CrmEnrichment.organization_id == org_id,
            CrmEnrichment.customer_email == email,
            CrmEnrichment.renewal_date.isnot(None),
        )
        .first()
    )
    if enrichment is None:
        return None
    anchor = as_of or datetime.utcnow()
    return float((enrichment.renewal_date - anchor).days)


def _label0_rows(org_id: int, db: Session) -> list[dict]:
    """Label-0 population: customers ACTIVE in the 180-day window whose email
    has NO qualifying (source != 'auto_suggested') churn event at all — the
    calibrator's label semantics (a recovered customer is still churned; an
    out-of-window churn still disqualifies the label-0 row). Feature values
    are the CURRENT health/usage rows (no label date -> current snapshot),
    aggregates over the current 30 days."""
    cutoff = datetime.utcnow() - timedelta(days=_LABEL_WINDOW_DAYS)

    churned_emails = {
        row[0]
        for row in (
            db.query(CustomerChurnEvent.customer_email)
            .filter(
                CustomerChurnEvent.organization_id == org_id,
                CustomerChurnEvent.source != "auto_suggested",
            )
            .distinct()
            .all()
        )
    }

    health_rows = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.last_feedback_at >= cutoff,
        )
        .order_by(CustomerHealth.id.asc())
        .all()
    )

    usage_by_email = {
        u.customer_email: u
        for u in db.query(CustomerUsage)
        .filter(CustomerUsage.organization_id == org_id)
        .all()
    }

    rows: list[dict] = []
    for health in health_rows:
        if health.customer_email in churned_emails:
            continue
        usage = usage_by_email.get(health.customer_email)
        row = {
            "customer_email": health.customer_email,
            "health_score": health.health_score,
            "churn_risk_component": health.churn_risk_component,
            "sentiment_component": health.sentiment_component,
            "resolution_component": health.resolution_component,
            "frequency_component": health.frequency_component,
            "usage_component": health.usage_component,
            "crm_component": health.crm_component,
            "risk_level": health.risk_level,
            "segment": health.segment,
        }
        if usage is not None:
            row.update({
                "active_days_7d": usage.active_days_7d,
                "active_days_14d": usage.active_days_14d,
                "active_days_30d": usage.active_days_30d,
                "login_count_30d": usage.login_count_30d,
                "usage_score": usage.usage_score,
                "usage_trend_state": usage.usage_trend_state,
                "usage_trend_pct": usage.usage_trend_pct,
            })
        row.update(_feedback_aggregates(org_id, health.customer_email, db))
        renewal = _renewal_proximity(org_id, health.customer_email, db)
        if renewal is not None:
            row["renewal_proximity_days"] = renewal
        row["label"] = 0
        rows.append(row)
    return rows


def _build_churn_dataset(org_id: int, db: Session) -> dict:
    """Assemble the org's binary churn dataset: {"features": [...], "labels": [...]}.

    Positive rows = the core's fetch_churn_rows (qualifying in-window churn
    events), history-snapshotted at the label date with leakage-free feedback
    aggregates. Label-0 rows = active non-churned customers (see _label0_rows).
    The core's rows_to_dataset does the final transform.
    """
    from analyzer.churn_classifier.dataset import fetch_churn_rows, rows_to_dataset

    rows = fetch_churn_rows(org_id, db)
    for row in rows:
        churned_at = _coerce_datetime(row["churned_at"])
        _attach_history(org_id, row, db, as_of=churned_at)
        row.update(_feedback_aggregates(org_id, row["customer_email"], db, as_of=churned_at))
        renewal = _renewal_proximity(org_id, row["customer_email"], db, as_of=churned_at)
        if renewal is not None:
            row["renewal_proximity_days"] = renewal

    rows.extend(_label0_rows(org_id, db))
    return rows_to_dataset(rows)


# ---------------------------------------------------------------------------
# Incumbent (org -> global -> identity calibrated heuristic)
# ---------------------------------------------------------------------------


def _load_calibration_predict(org_id: int, db: Session) -> Optional[Callable[[float], float]]:
    """Load the org's active calibrated heuristic as a p(churn_risk_component)
    callable, following probability_updater._load_active_model's
    org -> global -> identity chain. Returns None for identity (the core's
    build_incumbent_predict applies p = component / 100 then). Never raises:
    a corrupt artifact degrades to identity (probability_updater's own
    fallback, re-used here)."""
    from src.services.probability_updater import _interpolate, _load_active_model

    model = _load_active_model(org_id, db)
    if model.db_id is None:
        return None  # identity fallback

    def _calibrated(component: float) -> float:
        return _interpolate(float(component), model.breakpoints, model.probabilities)

    return _calibrated


def _build_incumbent_predict_for(org_id: int, db: Session) -> Callable[[list], float]:
    """Wrap the org's calibrated incumbent via the core's build_incumbent_predict.
    The calibration loader is cached per run (the core calls it per holdout row;
    the model cannot change within this single transaction)."""
    from analyzer.churn_classifier.evaluate import build_incumbent_predict

    cached = {"fn": None}

    def _loader():
        if cached["fn"] is None:
            cached["fn"] = _load_calibration_predict(org_id, db)
        return cached["fn"]

    return build_incumbent_predict(_loader)


# ---------------------------------------------------------------------------
# Eval-run + promote plumbing
# ---------------------------------------------------------------------------


def _streak_carrier(org_id: int, db: Session) -> Optional[OrgClassifierEvalRun]:
    """The streak-state carrier: the most recent EVALUABLE OrgClassifierEvalRun
    for (org, 'churn'). Skipped runs are NO-SIGNAL weeks (no true delta — the
    'streak broken' rule only applies to evaluable non-clears), so they are
    transparent to the streak: a candidate survives a below-gate week. Held
    runs are NOT transparent (the hold clears the streak — after it lifts,
    two fresh clears are required again)."""
    return (
        db.query(OrgClassifierEvalRun)
        .filter(
            OrgClassifierEvalRun.organization_id == org_id,
            OrgClassifierEvalRun.classifier_type == _CHURN_CLASSIFIER_TYPE,
            OrgClassifierEvalRun.decision != "skipped",
        )
        .order_by(OrgClassifierEvalRun.created_at.desc(), OrgClassifierEvalRun.id.desc())
        .first()
    )


def _insert_eval_run(org_id: int, model_id: Optional[int], result, duration_ms: int,
                     db: Session) -> None:
    """Insert the one org_classifier_eval_runs row every retrain_org run writes
    (except a lock-miss, which writes nothing)."""
    eval_run = OrgClassifierEvalRun(
        organization_id=org_id,
        classifier_model_id=model_id,
        classifier_type=_CHURN_CLASSIFIER_TYPE,
        incumbent_macro_f1=_round_or_none(result.incumbent_macro_f1),
        challenger_macro_f1=_round_or_none(result.challenger_macro_f1),
        macro_f1_delta=_round_or_none(result.macro_f1_delta),
        decision=result.decision,
        n=result.n,
        duration_ms=duration_ms,
        notes=result.notes,
    )
    db.add(eval_run)


def _promote(org_id: int, dataset: dict, result, db: Session) -> int:
    """Atomic promotion, single transaction (caller commits): train the FINAL
    production artifact on ALL rows (not just the core's internal train-split
    — that one never sees the full data), deactivate the prior active
    (org, 'churn') row, insert the new active row, flush to populate its id.
    Never a window with 0 or 2 active rows for the same (org, 'churn')."""
    from analyzer.churn_classifier.trainer import train_churn_classifier

    artifact = train_churn_classifier(dataset)

    prev_active = (
        db.query(OrgClassifierModel)
        .filter(
            OrgClassifierModel.organization_id == org_id,
            OrgClassifierModel.classifier_type == _CHURN_CLASSIFIER_TYPE,
            OrgClassifierModel.is_active == True,  # noqa: E712
        )
        .first()
    )
    if prev_active is not None:
        prev_active.is_active = False
        db.add(prev_active)
        db.flush()  # force the deactivating UPDATE to hit the DB before the new
        # active row is INSERTed below. SQLAlchemy's unit-of-work otherwise
        # emits INSERTs before UPDATEs within a single flush, which would
        # transiently violate Postgres' IMMEDIATE partial-unique index
        # uq_org_classifier_one_active (organization_id, classifier_type WHERE
        # is_active) — the new row would INSERT while the old row is still
        # is_active=TRUE. This extra flush does not commit; the deactivate+
        # insert remains one atomic transaction (caller commits once).

    new_model = OrgClassifierModel(
        organization_id=org_id,
        classifier_type=_CHURN_CLASSIFIER_TYPE,
        model_json=artifact,
        label_count=len(dataset["labels"]),
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


# ---------------------------------------------------------------------------
# retrain_org
# ---------------------------------------------------------------------------


def retrain_org(org_id: int, db: Session) -> dict:
    """Retrain the per-org churn classifier for a single org.

    1. Acquire a per-(classifier_type, org) Redis advisory lock (non-blocking) —
       an overlapping refit already owns this org: write nothing, return
       {"skipped": True, "reason": "locked"}.
    2. Assemble the org's binary dataset (positive churn events + label-0
       population, history-snapshotted at the label dates).
    3. evaluate_churn() the challenger against the org's active calibrated
       heuristic (org -> global -> identity) — leakage-free (the core trains
       the challenger itself, only on its own train-split/per-fold).
    4. Apply the consecutive-runs policy + the autopromote hold (see module
       docstring) and write exactly one org_classifier_eval_runs row, then
       commit once (single transaction covering the model swap and the eval
       run). Below-gate / single-class outcomes write a 'skipped' eval run and
       never raise.

    Streak state is read from the most recent (org, 'churn') eval run, so the
    two-week consecutive-clear requirement survives worker restarts.
    """
    r = _get_redis()
    lock = r.lock(
        f"lock:classifier_refit:{_CHURN_CLASSIFIER_TYPE}:{org_id}",
        timeout=_LOCK_TIMEOUT_SECONDS, blocking=False,
    )

    if not lock.acquire(blocking=False):
        logger.info(
            "retrain_org: org=%s type=%s already refitting, skipping",
            org_id, _CHURN_CLASSIFIER_TYPE,
        )
        return _skip_result("locked")

    try:
        start = time.monotonic()

        # Lazy imports — the core owns sklearn/numpy; this module stays CPU-only-safe.
        from analyzer.churn_classifier.evaluate import evaluate_churn
        from analyzer.churn_classifier.labels import MARGIN, MIN_LABELS

        dataset = _build_churn_dataset(org_id, db)
        incumbent_predict = _build_incumbent_predict_for(org_id, db)

        result = evaluate_churn(
            dataset, incumbent_predict, _promote_train_fn,
            min_labels=MIN_LABELS, margin=MARGIN,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        if result.decision == "skipped":
            # Below min labels / single-class — no signal to promote or hold.
            _insert_eval_run(org_id, None, result, duration_ms, db)
            db.commit()
            logger.info(
                "retrain_org: org=%s type=%s skipped n=%s notes=%s",
                org_id, _CHURN_CLASSIFIER_TYPE, result.n, result.notes,
            )
            return _skip_result(result.notes or "skipped", n=result.n, notes=result.notes)

        # Re-read the hold flag immediately before the promote-or-not decision,
        # row-locked, in the SAME transaction that (maybe) promotes + always
        # inserts the eval run (single db.commit() below) — a concurrently-
        # committed rollback (hold flip) is observed here. Held blocks BOTH
        # runs' state: no candidate, no promote. The eval run persists
        # decision="held" with the real macro_f1_delta/n (disclosure only).
        held, mode = _churn_config(org_id, db)
        if held:
            result = _dataclasses_replace(result, decision="held")

        model_id: Optional[int] = None
        if result.decision != "held":
            prev_run = _streak_carrier(org_id, db)
            clears = result.decision == "promoted"

            if clears and (prev_run is None or prev_run.decision != "promoted_candidate"):
                # First of the two required consecutive clears — stage it, no swap.
                result = _dataclasses_replace(result, decision="promoted_candidate")
            elif clears:
                # Second consecutive clear — promote.
                model_id = _promote(org_id, dataset, result, db)
                result = _dataclasses_replace(result, decision="promoted")
            elif prev_run is not None and prev_run.decision == "promoted_candidate":
                # Evaluable non-clear after a candidate — streak broken.
                result = _dataclasses_replace(result, notes=f"streak broken; {result.notes}")

        _insert_eval_run(org_id, model_id, result, duration_ms, db)
        db.commit()

        if result.decision == "held":
            logger.info(
                "retrain_org: org=%s type=%s held (autopromote hold) delta=%s n=%s",
                org_id, _CHURN_CLASSIFIER_TYPE, result.macro_f1_delta, result.n,
            )
            return _decision_result("held", model_id=model_id, n=result.n,
                                    notes=result.notes, mode=mode)

        logger.info(
            "retrain_org: org=%s type=%s decision=%s model_id=%s n=%s",
            org_id, _CHURN_CLASSIFIER_TYPE, result.decision, model_id, result.n,
        )
        return _decision_result(
            result.decision, model_id=model_id, n=result.n, notes=result.notes,
            mode=mode,
        )
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass


def _promote_train_fn(dataset: dict) -> dict:
    """train_fn seam for evaluate_churn — production trainer, imported lazily so
    the module stays importable without sklearn. Only ever called by the core
    on the core's own train split."""
    from analyzer.churn_classifier.trainer import train_churn_classifier

    return train_churn_classifier(dataset)


# ---------------------------------------------------------------------------
# retrain_all_orgs + purge
# ---------------------------------------------------------------------------


@shared_task(name="src.tasks.churn_classifier_training.retrain_all_orgs")
def retrain_all_orgs() -> dict:
    """Weekly driver: retrain the churn classifier for every org with a
    trainable label count, then purge old inactive churn artifacts once
    (folded — no separate beat slot).

    Per-org try/except isolation: one org's exception is logged and the shared
    session rolled back, it never aborts the rest of the batch.

    Beat: Mondays 06:00 UTC (before the corrections-classifier batch at 06:30;
    the challenger evaluates against the incumbent refit of the previous week —
    see the module docstring). Returns tallies:
    {"trained", "promoted", "candidates", "skipped", "held", "locked"}.
    """
    trained = 0
    promoted = 0
    candidates = 0
    skipped = 0
    held = 0
    locked = 0

    with get_db_session() as db:
        org_ids = _all_org_ids(db)
        for org_id in org_ids:
            if _count_org_labels(org_id, db) < _ORG_LABEL_THRESHOLD:
                skipped += 1
                logger.info(
                    "retrain_all_orgs: org=%s skipped (labels < %s)",
                    org_id, _ORG_LABEL_THRESHOLD,
                )
                continue

            try:
                result = retrain_org(org_id, db)
            except Exception:
                logger.error(
                    "retrain_all_orgs: org=%s FAILED", org_id,
                    exc_info=True,
                )
                # This db session is shared across every org in the batch. A
                # failed flush/commit leaves the session needing a rollback;
                # without it, the NEXT iteration's first DB operation raises
                # sqlalchemy.exc.PendingRollbackError and the batch cascades.
                db.rollback()
                continue

            if result.get("reason") == "locked":
                locked += 1
            elif result.get("skipped"):
                skipped += 1
            else:
                trained += 1
                if result.get("promoted"):
                    promoted += 1
                elif result.get("promoted_candidate"):
                    candidates += 1
                elif result.get("held"):
                    held += 1

    purge_result = purge_old_churn_classifier_models()
    logger.info(
        "retrain_all_orgs: done trained=%s promoted=%s candidates=%s "
        "skipped=%s held=%s locked=%s purged=%s",
        trained, promoted, candidates, skipped, held, locked,
        purge_result.get("deleted"),
    )
    return {
        "trained": trained,
        "promoted": promoted,
        "candidates": candidates,
        "skipped": skipped,
        "held": held,
        "locked": locked,
    }


def purge_old_churn_classifier_models() -> dict:
    """Delete OrgClassifierModel rows where classifier_type='churn' AND
    is_active=False AND fit_at < now()-90d.

    Folded into retrain_all_orgs (no separate beat slot). Type-scoped so this
    never touches sentiment/category/urgency rows (the M5.2 purge owns those).
    Mirrors churn_calibration.purge_old_calibration_models. Returns {"deleted": N}.
    """
    cutoff = datetime.utcnow() - timedelta(days=_PURGE_AFTER_DAYS)

    with get_db_session() as db:
        old_rows = (
            db.query(OrgClassifierModel)
            .filter(
                OrgClassifierModel.classifier_type == _CHURN_CLASSIFIER_TYPE,
                OrgClassifierModel.is_active == False,  # noqa: E712
                OrgClassifierModel.fit_at < cutoff,
            )
            .all()
        )
        for row in old_rows:
            db.delete(row)
        db.commit()

    logger.info("purge_old_churn_classifier_models: deleted=%s", len(old_rows))
    return {"deleted": len(old_rows)}
