"""
Tests for Celery tasks in tasks.churn_classifier_training — worker-churn-trainer-
and-schedule aspect (M5.3 per-org-churn-model).

Written RED-first (TDD), mirroring tests/test_classifier_training_tasks.py's
conventions: in-memory SQLite (Base.metadata.create_all), a `db` fixture,
`_make_org` seed helpers, a `_get_tasks()` lazy import, and per-test patching of
the analysis-engine churn core (analyzer.churn_classifier.*) so most tests never
require a real fit. The consecutive-runs promotion policy (plan amendment
2026-08-14) is pinned here:

- first clear (+0.02 macro-F1) -> eval run decision='promoted_candidate', no swap;
- candidate then a second consecutive clear -> promote (final artifact on ALL rows);
- any evaluable non-clear after a candidate -> 'streak broken' note, never promotes;
- below-gate / single-class weeks are no-signal (no true delta) and do NOT break
  the streak; the autopromote hold clears both runs' state.

Because SQLite does not enforce the Postgres partial-unique on
(organization_id, classifier_type) WHERE is_active, the "exactly one active"
invariant is asserted via explicit count(*) queries — this validates the code's
swap ordering, which is the real target.
"""

from __future__ import annotations

import importlib
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    ChurnCalibrationModel,
    CrmEnrichment,
    CustomerChurnEvent,
    CustomerHealth,
    CustomerHealthHistory,
    CustomerUsage,
    CustomerUsageHistory,
    FeedbackItem,
    Organization,
    OrgClassifierEvalRun,
    OrgClassifierModel,
)

from tests.test_classifier_training_tasks import (
    _fake_redis_lock_acquired,
    _fake_redis_lock_denied,
    _make_org,
)

# ---------------------------------------------------------------------------
# In-memory DB wiring
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_churn_event(db, org_id: int, email: str, *, churned_at=None,
                      source: str = "manual") -> CustomerChurnEvent:
    event = CustomerChurnEvent(
        organization_id=org_id,
        customer_email=email,
        churned_at=churned_at or (datetime.utcnow() - timedelta(days=5)),
        reason_code="price",
        reason_text=None,
        source=source,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _make_health(db, org_id: int, email: str, *, churn_risk: int = 50,
                 last_feedback_at=None, segment: str = "at_risk",
                 sentiment: int = 50) -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=50,
        churn_risk_component=churn_risk,
        sentiment_component=sentiment,
        resolution_component=50,
        frequency_component=50,
        usage_component=50,
        crm_component=50.0,
        risk_level="moderate",
        segment=segment,
        last_feedback_at=last_feedback_at or datetime.utcnow(),
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _make_usage(db, org_id: int, email: str, *, active_days_30d: int = 20,
                usage_score: int = 50) -> CustomerUsage:
    usage = CustomerUsage(
        organization_id=org_id,
        customer_email=email,
        active_days_7d=2,
        active_days_14d=5,
        active_days_30d=active_days_30d,
        login_count_30d=8,
        usage_score=usage_score,
        usage_trend_state="stable",
        usage_trend_pct=0.0,
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def _make_active_churn_model(db, org_id: int, macro_f1: float = 0.40) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="churn",
        model_json={"model_type": "churn_logreg", "version": 1,
                    "features": [], "coef": [], "intercept": 0.0, "classes": [0, 1]},
        label_count=30,
        precision=None,
        recall=None,
        macro_f1=macro_f1,
        accuracy=None,
        fit_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _make_calibration_model(db, org_id, *, breakpoints, probabilities) -> ChurnCalibrationModel:
    model = ChurnCalibrationModel(
        organization_id=org_id,
        model_json={"breakpoints": breakpoints, "probabilities": probabilities,
                    "threshold_bands": {"low": 0.30, "medium": 0.50,
                                        "high": 0.70, "critical": 0.85}},
        label_count=25,
        positive_count=10,
        precision=0.7,
        recall=0.7,
        f1=0.7,
        auc=0.8,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        fit_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


# ---------------------------------------------------------------------------
# Task import alias (lazy — avoids importing Celery at collection time)
# ---------------------------------------------------------------------------


def _get_tasks():
    import src.tasks.churn_classifier_training as churn_classifier_training
    return churn_classifier_training


# ---------------------------------------------------------------------------
# Core patch helper (deterministic decision without a real fit)
# ---------------------------------------------------------------------------


@contextmanager
def _patch_churn_core(decision: str = "retained", *, n: int = 25,
                      incumbent_macro_f1=0.50, challenger_macro_f1=0.60,
                      macro_f1_delta=0.0, notes=None, positive_rows=None,
                      artifact=None):
    """Patch the churn core so retrain_org's decision is fully deterministic,
    without sklearn needing to fit anything. The dataset builder still runs for
    real (fetch_churn_rows is patched to `positive_rows`; the label-0
    population is whatever the test DB holds)."""
    from analyzer.churn_classifier.evaluate import EvalResult

    if notes is None:
        notes = f"{decision} (delta={macro_f1_delta:+.4f}, n={n})" if macro_f1_delta is not None else decision
    if positive_rows is None:
        positive_rows = [
            {
                "customer_email": f"churned{i}@example.com",
                "churned_at": datetime.utcnow() - timedelta(days=5),
                "health_score": 60 - (i % 20),
                "churn_risk_component": 50 + (i % 40),
                "sentiment_component": 50,
                "resolution_component": 50,
                "frequency_component": 50,
                "usage_component": 50,
                "crm_component": 50.0,
                "risk_level": "moderate",
                "segment": "at_risk",
                "active_days_7d": 2,
                "active_days_14d": 5,
                "active_days_30d": 12,
                "login_count_30d": 8,
                "usage_score": 50,
                "usage_trend_state": "stable",
                "usage_trend_pct": 0.0,
            }
            for i in range(n)
        ]
    if artifact is None:
        artifact = {
            "model_type": "churn_logreg",
            "version": 1,
            "features": ["churn_risk_component"],
            "coef": [1.0],
            "intercept": -1.0,
            "classes": [0, 1],
        }

    fake_result = EvalResult(
        decision=decision, n=n,
        incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
        macro_f1_delta=macro_f1_delta, notes=notes,
    )

    # patch.object on the submodule, NOT a dotted patch() string —
    # analyzer.churn_classifier.__init__ re-exports evaluate_churn /
    # build_incumbent_predict under the same names as the evaluate submodule,
    # which breaks mock.patch's dotted-path getattr walk (same trap as
    # corrections_classifier, documented in test_classifier_training_tasks.py).
    evaluate_module = importlib.import_module("analyzer.churn_classifier.evaluate")

    with patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               return_value=positive_rows), \
         patch.object(evaluate_module, "evaluate_churn", return_value=fake_result), \
         patch.object(evaluate_module, "build_incumbent_predict",
                      return_value=lambda _vector: 0.5), \
         patch("analyzer.churn_classifier.trainer.train_churn_classifier",
               return_value=artifact):
        yield fake_result, artifact


# ---------------------------------------------------------------------------
# Phase 1 — module skeleton + schedule wiring
# ---------------------------------------------------------------------------


def test_task_module_importable():
    tasks = _get_tasks()
    assert hasattr(tasks, "retrain_all_orgs")
    assert hasattr(tasks, "retrain_org")
    assert hasattr(tasks, "purge_old_churn_classifier_models")


def test_no_module_level_sklearn_import():
    """The task module must have zero module-level sklearn/numpy imports — heavy
    ML wheels live only inside the analysis-engine core, imported lazily."""
    import src.tasks.churn_classifier_training as churn_classifier_training

    source = open(churn_classifier_training.__file__).read()
    for line in source.splitlines():
        if line.startswith((" ", "\t")):
            continue  # only inspect non-indented (module-top) lines
        assert not re.match(r"^\s*import\s+sklearn\b", line), line
        assert not re.match(r"^\s*import\s+numpy\b", line), line
        assert not re.match(r"^\s*from\s+sklearn\b", line), line
        assert not re.match(r"^\s*from\s+numpy\b", line), line


def test_task_module_in_include():
    """src.tasks.churn_classifier_training is registered in celery_app's include=[...]."""
    import src.celery_app as celery_app

    assert "src.tasks.churn_classifier_training" in celery_app.celery_app.conf.include


def test_beat_entry_registered_and_ordered():
    """celery_app.conf.beat_schedule has retrain-churn-classifier-weekly at
    Mon 06:00 UTC, strictly before retrain-classifier-weekly (06:30)."""
    from celery.schedules import crontab

    import src.celery_app as celery_app

    entries = celery_app.celery_app.conf.beat_schedule
    churn_entry = entries.get("retrain-churn-classifier-weekly")
    assert churn_entry is not None
    assert churn_entry["task"] == "src.tasks.churn_classifier_training.retrain_all_orgs"
    assert churn_entry["schedule"] == crontab(hour=6, minute=0, day_of_week=1)

    sentiment_entry = entries.get("retrain-classifier-weekly")
    assert sentiment_entry is not None
    from tests.test_beat_schedule_integrity import _crontab_key
    assert _crontab_key(churn_entry["schedule"]) < _crontab_key(sentiment_entry["schedule"])


# ---------------------------------------------------------------------------
# Phase 2 — dataset assembly (label-0 population + nearest-snapshot history)
# ---------------------------------------------------------------------------
#
# These tests run the REAL analyzer.churn_classifier.dataset.fetch_churn_rows
# against the worker's in-memory sqlite mirror (table/column names match), and
# the REAL rows_to_dataset + build_feature_vector. Only _build_churn_dataset's
# caller-side attachment logic is under test.


def test_build_dataset_uses_nearest_history_before_churned_at(db):
    org = _make_org(db)
    email = "churned@example.com"
    churned_at = datetime.utcnow() - timedelta(days=10)
    _make_churn_event(db, org.id, email, churned_at=churned_at)
    health = _make_health(db, org.id, email, churn_risk=40)
    _make_usage(db, org.id, email, active_days_30d=20, usage_score=50)
    # Two snapshots: one before the label date (must win), one after (must not).
    db.add(CustomerHealthHistory(
        customer_health_id=health.id,
        organization_id=org.id,
        health_score=70,
        churn_risk_component=88,
        sentiment_component=30,
        resolution_component=40,
        frequency_component=45,
        usage_component=35,
        crm_component=25.0,
        risk_level="critical",
        recorded_at=churned_at - timedelta(days=1),
    ))
    db.add(CustomerHealthHistory(
        customer_health_id=health.id,
        organization_id=org.id,
        health_score=99,
        churn_risk_component=99,
        sentiment_component=99,
        resolution_component=99,
        frequency_component=99,
        usage_component=99,
        crm_component=99.0,
        risk_level="healthy",
        recorded_at=churned_at + timedelta(days=1),
    ))
    db.add(CustomerUsageHistory(
        organization_id=org.id,
        customer_email=email,
        snapshot_date=churned_at.date() - timedelta(days=1),
        active_days_7d=0,
        active_days_14d=1,
        active_days_30d=7,
        login_count_30d=3,
        usage_score=20,
        usage_trend_state="declining",
        usage_trend_pct=-40.0,
    ))
    db.commit()

    tasks = _get_tasks()
    dataset = tasks._build_churn_dataset(org.id, db)

    from analyzer.churn_classifier.features import FEATURE_NAMES

    assert dataset["labels"] == [1]
    features = dataset["features"][0]
    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
    assert features[idx["churn_risk_component"]] == 88.0  # history at label date, not current 40
    assert features[idx["sentiment_component"]] == 30.0
    assert features[idx["risk_level"]] == 4.0  # critical (RISK_LEVEL_ORDER)
    assert features[idx["active_days_30d"]] == 7.0  # usage history, not current 20
    assert features[idx["usage_trend_pct"]] == -40.0


def test_build_dataset_partial_history_keeps_current_for_missing_fields(db):
    """A history snapshot missing a field must not null it out — the current
    joined value survives (calibrator fallback semantics)."""
    org = _make_org(db)
    email = "churned@example.com"
    churned_at = datetime.utcnow() - timedelta(days=10)
    _make_churn_event(db, org.id, email, churned_at=churned_at)
    health = _make_health(db, org.id, email, churn_risk=40)
    _make_usage(db, org.id, email, active_days_30d=20, usage_score=50)
    db.add(CustomerHealthHistory(
        customer_health_id=health.id,
        organization_id=org.id,
        health_score=70,
        churn_risk_component=88,
        sentiment_component=None,
        resolution_component=None,
        frequency_component=None,
        usage_component=None,
        crm_component=None,
        risk_level="critical",
        recorded_at=churned_at - timedelta(days=1),
    ))
    db.commit()

    tasks = _get_tasks()
    dataset = tasks._build_churn_dataset(org.id, db)

    from analyzer.churn_classifier.features import FEATURE_NAMES

    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
    features = dataset["features"][0]
    assert features[idx["churn_risk_component"]] == 88.0
    assert features[idx["sentiment_component"]] == 50.0  # current, not defaulted


def test_build_dataset_label0_population_excludes_qualifying_churned(db):
    org = _make_org(db)
    now = datetime.utcnow()
    # Churned in-window (manual) — positive row only, never a label-0 row.
    _make_churn_event(db, org.id, "churned@example.com", churned_at=now - timedelta(days=5))
    _make_health(db, org.id, "churned@example.com", churn_risk=80, last_feedback_at=now - timedelta(days=6))
    # auto_suggested event only — does NOT count as a qualifying churn.
    _make_churn_event(db, org.id, "suggested@example.com", churned_at=now - timedelta(days=5),
                      source="auto_suggested")
    _make_health(db, org.id, "suggested@example.com", churn_risk=30, last_feedback_at=now - timedelta(days=6))
    # Out-of-window manual event — still a qualifying churn (calibrator parity):
    # excluded from the label-0 population, and not a positive row either.
    _make_churn_event(db, org.id, "old@example.com", churned_at=now - timedelta(days=400))
    _make_health(db, org.id, "old@example.com", churn_risk=55, last_feedback_at=now - timedelta(days=6))
    # Active, never churned — the label-0 row.
    _make_health(db, org.id, "active@example.com", churn_risk=55, last_feedback_at=now - timedelta(days=2))
    _make_usage(db, org.id, "active@example.com", active_days_30d=25, usage_score=70)
    # Active but stale (no feedback in window) — not part of the population.
    _make_health(db, org.id, "stale@example.com", churn_risk=20,
                 last_feedback_at=now - timedelta(days=400))

    tasks = _get_tasks()
    dataset = tasks._build_churn_dataset(org.id, db)

    from analyzer.churn_classifier.features import FEATURE_NAMES

    # churned (positive) + suggested (only auto_suggested -> label-0) + active (label-0);
    # old@example.com (out-of-window qualifying churn) and stale@example.com
    # (no feedback in window) are excluded entirely.
    labels = dataset["labels"]
    assert labels == [1, 0, 0]
    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
    features = dataset["features"][2]  # the active, never-churned customer
    assert features[idx["churn_risk_component"]] == 55.0  # current value for label-0
    assert features[idx["active_days_30d"]] == 25.0


def test_build_dataset_feedback_aggregates_anchored_at_label_date(db):
    """Aggregates for a positive row must only count feedback BEFORE churned_at
    (leakage-free); post-churn feedback is excluded."""
    org = _make_org(db)
    email = "churned@example.com"
    churned_at = datetime.utcnow() - timedelta(days=10)
    _make_churn_event(db, org.id, email, churned_at=churned_at)
    _make_health(db, org.id, email, churn_risk=40)
    _make_usage(db, org.id, email)

    for days_back, score, urgent, churn_risk in (
        (15, 0.8, False, 60),   # in window, before label date
        (12, -0.6, True, 90),   # in window, before label date
        (5, 1.0, False, 10),    # AFTER label date — must be excluded
        (45, 0.5, True, 50),    # outside the 30-day window — excluded
    ):
        db.add(FeedbackItem(
            organization_id=org.id,
            customer_email=email,
            text=f"feedback {days_back}",
            sentiment_score=score,
            is_urgent=urgent,
            churn_risk_score=churn_risk,
            created_at=datetime.utcnow() - timedelta(days=days_back),
        ))
    db.commit()

    tasks = _get_tasks()
    dataset = tasks._build_churn_dataset(org.id, db)

    from analyzer.churn_classifier.features import FEATURE_NAMES

    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
    features = dataset["features"][0]
    assert features[idx["count_30d"]] == 2.0
    assert features[idx["avg_sentiment"]] == pytest.approx(0.1, abs=1e-9)  # (0.8 + -0.6) / 2
    assert features[idx["urgent_share"]] == pytest.approx(0.5, abs=1e-9)
    assert features[idx["avg_churn_risk"]] == pytest.approx(75.0, abs=1e-9)  # (60 + 90) / 2


def test_build_dataset_renewal_proximity_attached(db):
    org = _make_org(db)
    email = "churned@example.com"
    churned_at = datetime.utcnow() - timedelta(days=10)
    _make_churn_event(db, org.id, email, churned_at=churned_at)
    _make_health(db, org.id, email, churn_risk=40)
    _make_usage(db, org.id, email)
    db.add(CrmEnrichment(
        organization_id=org.id,
        customer_email=email,
        provider="hubspot",
        renewal_date=datetime.utcnow() + timedelta(days=30),
        last_synced_at=datetime.utcnow(),
    ))
    db.commit()

    tasks = _get_tasks()
    dataset = tasks._build_churn_dataset(org.id, db)

    from analyzer.churn_classifier.features import FEATURE_NAMES

    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
    assert dataset["features"][0][idx["renewal_proximity_days"]] == 40  # renewal - churned_at


def test_build_dataset_empty_returns_empty_dataset(db):
    org = _make_org(db)
    tasks = _get_tasks()
    assert tasks._build_churn_dataset(org.id, db) == {"features": [], "labels": []}


# ---------------------------------------------------------------------------
# Phase 3 — incumbent calibration loader (org -> global -> identity)
# ---------------------------------------------------------------------------


def test_load_calibration_predict_uses_org_model(db):
    org = _make_org(db)
    _make_calibration_model(db, org.id, breakpoints=[0, 50, 100], probabilities=[0.0, 0.5, 1.0])

    tasks = _get_tasks()
    calibrated = tasks._load_calibration_predict(org.id, db)
    assert calibrated is not None
    assert calibrated(50) == pytest.approx(0.5, abs=1e-9)
    assert calibrated(25) == pytest.approx(0.25, abs=1e-9)


def test_load_calibration_predict_falls_back_to_global_model(db):
    org = _make_org(db)
    _make_calibration_model(db, None, breakpoints=[0, 50, 100], probabilities=[0.0, 0.5, 1.0])

    tasks = _get_tasks()
    calibrated = tasks._load_calibration_predict(org.id, db)
    assert calibrated is not None
    assert calibrated(75) == pytest.approx(0.75, abs=1e-9)


def test_load_calibration_predict_identity_when_no_model(db):
    org = _make_org(db)
    tasks = _get_tasks()
    assert tasks._load_calibration_predict(org.id, db) is None


def test_load_calibration_predict_corrupt_artifact_identity(db):
    org = _make_org(db)
    model = _make_calibration_model(db, org.id, breakpoints=[0, 50, 100], probabilities=[0.0, 0.5, 1.0])
    model.model_json = {"garbage": True}
    db.commit()

    tasks = _get_tasks()
    assert tasks._load_calibration_predict(org.id, db) is None


def test_retrain_org_wires_build_incumbent_predict_with_org_loader(db):
    """retrain_org must hand build_incumbent_predict a loader that resolves the
    org's active calibrated model (org -> global -> identity) — not identity."""
    org = _make_org(db)
    _make_calibration_model(db, org.id, breakpoints=[0, 50, 100], probabilities=[0.0, 0.5, 1.0])
    fake_r, _ = _fake_redis_lock_acquired()

    captured_loader = {}
    evaluate_module = importlib.import_module("analyzer.churn_classifier.evaluate")

    def spy_build_incumbent(loader):
        captured_loader["loader"] = loader
        return lambda _vector: 0.5

    from analyzer.churn_classifier.evaluate import EvalResult

    fake_result = EvalResult(decision="retained", n=25, incumbent_macro_f1=0.5,
                             challenger_macro_f1=0.5, macro_f1_delta=0.0,
                             notes="retained (delta=+0.0000, n=25)")

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               return_value=[{"customer_email": f"c{i}@x.com", "churned_at": datetime.utcnow(),
                              "churn_risk_component": 60} for i in range(25)]), \
         patch.object(evaluate_module, "build_incumbent_predict",
                      side_effect=spy_build_incumbent), \
         patch.object(evaluate_module, "evaluate_churn", return_value=fake_result):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    assert captured_loader["loader"] is not None
    calibrated = captured_loader["loader"]()
    assert calibrated is not None
    assert calibrated(50) == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Phase 4 — lock behavior
# ---------------------------------------------------------------------------


def test_retrain_org_acquires_per_org_churn_lock(db):
    org = _make_org(db)
    fake_r, fake_lock = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("retained", n=25):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    fake_r.lock.assert_called_once_with(
        f"lock:classifier_refit:churn:{org.id}", timeout=600, blocking=False,
    )
    fake_lock.acquire.assert_called_once_with(blocking=False)


def test_retrain_org_lock_not_acquired_skips_without_writes(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_denied()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result == {"decision": "skipped", "skipped": True, "reason": "locked"}
    assert db.query(OrgClassifierEvalRun).count() == 0
    assert db.query(OrgClassifierModel).count() == 0


def test_retrain_org_releases_lock_in_finally(db):
    org = _make_org(db)
    fake_r, fake_lock = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               side_effect=RuntimeError("boom")):
        tasks = _get_tasks()
        with pytest.raises(RuntimeError):
            tasks.retrain_org(org.id, db)

    fake_lock.release.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 5 — skip paths (never raise)
# ---------------------------------------------------------------------------


def test_retrain_org_below_min_labels_writes_skipped_eval_run(db):
    """Real evaluate_churn: 5 rows < MIN_LABELS short-circuits before any fit."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               return_value=[{"customer_email": f"c{i}@x.com",
                              "churned_at": datetime.utcnow(),
                              "churn_risk_component": 60} for i in range(5)]):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "skipped"
    assert db.query(OrgClassifierModel).count() == 0
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "skipped"
    assert run.classifier_type == "churn"
    assert run.n == 5
    assert run.classifier_model_id is None


def test_retrain_org_single_class_writes_skipped_eval_run(db):
    """Real evaluate_churn: 25 rows of a single class -> skipped, never raises."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               return_value=[{"customer_email": f"c{i}@x.com",
                              "churned_at": datetime.utcnow(),
                              "churn_risk_component": 60} for i in range(25)]):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "skipped"
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "skipped"
    assert run.notes == "single-class labels"
    assert db.query(OrgClassifierModel).count() == 0


# ---------------------------------------------------------------------------
# Phase 6 — consecutive-runs promotion policy
# ---------------------------------------------------------------------------


def test_first_clear_writes_promoted_candidate_without_model_swap(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, incumbent_macro_f1=0.50,
                           challenger_macro_f1=0.65, macro_f1_delta=0.15):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "promoted_candidate"
    assert db.query(OrgClassifierModel).count() == 0
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "promoted_candidate"
    assert run.classifier_type == "churn"
    assert run.classifier_model_id is None
    assert float(run.macro_f1_delta) == pytest.approx(0.15, abs=1e-4)
    assert run.n == 25


def test_candidate_then_clear_promotes_final_artifact_on_all_rows(db):
    org = _make_org(db)
    prior = _make_active_churn_model(db, org.id, macro_f1=0.40)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65) as (_, artifact):
        tasks = _get_tasks()
        first = tasks.retrain_org(org.id, db)

    assert first["decision"] == "promoted_candidate"
    db.refresh(prior)
    assert prior.is_active is True  # nothing swapped on the candidate run

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65) as (_, artifact):
        tasks = _get_tasks()
        second = tasks.retrain_org(org.id, db)

    assert second["decision"] == "promoted"
    assert second["promoted"] is True

    db.refresh(prior)
    assert prior.is_active is False
    models = db.query(OrgClassifierModel).filter_by(organization_id=org.id).all()
    assert len(models) == 2
    new_model = next(m for m in models if m.is_active)
    assert new_model.classifier_type == "churn"
    assert new_model.model_json == artifact
    assert new_model.label_count == 25
    assert float(new_model.macro_f1) == pytest.approx(0.65, abs=1e-4)

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id) \
        .order_by(OrgClassifierEvalRun.id.asc()).all()
    assert [r.decision for r in runs] == ["promoted_candidate", "promoted"]
    assert runs[1].classifier_model_id == new_model.id
    assert float(runs[1].macro_f1_delta) == pytest.approx(0.0, abs=1e-4)  # default delta

    active_count = (
        db.query(OrgClassifierModel)
        .filter_by(organization_id=org.id, classifier_type="churn", is_active=True)
        .count()
    )
    assert active_count == 1


def test_clear_then_degrade_never_promotes_streak_reset(db):
    """clear -> candidate; non-clear -> 'streak broken' note, no promote; a later
    clear restarts the streak as a candidate (never skips straight to promote)."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)  # run 1: candidate

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("retained", n=25, incumbent_macro_f1=0.65,
                           challenger_macro_f1=0.60, macro_f1_delta=-0.05):
        tasks = _get_tasks()
        result2 = tasks.retrain_org(org.id, db)  # run 2: degrade

    assert result2["decision"] == "retained"
    assert "streak broken" in result2["notes"]
    assert db.query(OrgClassifierModel).count() == 0

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        result3 = tasks.retrain_org(org.id, db)  # run 3: clear again

    assert result3["decision"] == "promoted_candidate"  # streak restarted, NOT promoted
    assert db.query(OrgClassifierModel).count() == 0

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id) \
        .order_by(OrgClassifierEvalRun.id.asc()).all()
    assert [r.decision for r in runs] == ["promoted_candidate", "retained", "promoted_candidate"]
    assert "streak broken" in runs[1].notes
    assert float(runs[1].macro_f1_delta) == pytest.approx(-0.05, abs=1e-4)


def test_retained_without_candidate_has_no_streak_note(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("retained", n=25, incumbent_macro_f1=0.65,
                           challenger_macro_f1=0.60, macro_f1_delta=-0.05):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "retained"
    assert "streak broken" not in result["notes"]
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "retained"
    assert "streak broken" not in run.notes


def test_promoted_restarts_as_candidate_on_next_clear(db):
    """After a promotion the streak is spent: the next clear is a fresh candidate."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    for _ in range(2):
        with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
             _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
            tasks = _get_tasks()
            tasks.retrain_org(org.id, db)

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        result3 = tasks.retrain_org(org.id, db)

    assert result3["decision"] == "promoted_candidate"

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id) \
        .order_by(OrgClassifierEvalRun.id.asc()).all()
    assert [r.decision for r in runs] == ["promoted_candidate", "promoted", "promoted_candidate"]
    assert db.query(OrgClassifierModel).filter_by(
        organization_id=org.id, is_active=True).count() == 1


def test_skipped_week_does_not_break_streak(db):
    """A below-gate week has no evaluable signal (no true delta) and must NOT
    reset the streak: candidate -> skipped -> clear still promotes."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)  # run 1: candidate

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               return_value=[{"customer_email": f"c{i}@x.com",
                              "churned_at": datetime.utcnow(),
                              "churn_risk_component": 60} for i in range(5)]):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)  # run 2: below gate -> skipped (no-signal)

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        result3 = tasks.retrain_org(org.id, db)  # run 3: clear -> PROMOTE

    assert result3["decision"] == "promoted"
    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id) \
        .order_by(OrgClassifierEvalRun.id.asc()).all()
    assert [r.decision for r in runs] == ["promoted_candidate", "skipped", "promoted"]
    assert "streak broken" not in runs[2].notes
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 1


# ---------------------------------------------------------------------------
# Phase 7 — promote atomicity (flush-before-INSERT + active invariant)
# ---------------------------------------------------------------------------


def test_promote_flushes_deactivation_before_inserting_new_active_row(db):
    """Clone of the M5.2 flush-order guard for classifier_type='churn': the
    deactivating UPDATE of the prior active row must be its own flush, strictly
    before the new active row's INSERT (Postgres' IMMEDIATE partial-unique
    index uq_org_classifier_one_active)."""
    org = _make_org(db)
    _make_active_churn_model(db, org.id, macro_f1=0.40)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)  # candidate run first
    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()

        flush_log: list[dict] = []
        original_flush = db.flush

        def spy_flush(*args, **kwargs):
            pending_new_model = any(isinstance(o, OrgClassifierModel) for o in db.new)
            ret = original_flush(*args, **kwargs)
            active_count = (
                db.query(OrgClassifierModel)
                .filter_by(organization_id=org.id, classifier_type="churn", is_active=True)
                .count()
            )
            flush_log.append({
                "pending_new_model_before_flush": pending_new_model,
                "active_count_after_flush": active_count,
            })
            return ret

        with patch.object(db, "flush", side_effect=spy_flush):
            tasks.retrain_org(org.id, db)

    assert len(flush_log) >= 2
    first = flush_log[0]
    assert first["pending_new_model_before_flush"] is False
    assert first["active_count_after_flush"] == 0

    final_active_count = (
        db.query(OrgClassifierModel)
        .filter_by(organization_id=org.id, classifier_type="churn", is_active=True)
        .count()
    )
    assert final_active_count == 1


def test_active_invariant_holds_across_repeated_promotions(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    for i in range(3):  # 3 candidate+promote cycles
        for _ in range(2):
            with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
                 _patch_churn_core("promoted", n=25, challenger_macro_f1=0.60 + i * 0.01):
                tasks = _get_tasks()
                tasks.retrain_org(org.id, db)

        active_count = (
            db.query(OrgClassifierModel)
            .filter_by(organization_id=org.id, classifier_type="churn", is_active=True)
            .count()
        )
        assert active_count == 1, f"cycle {i}: expected exactly 1 active churn row"


# ---------------------------------------------------------------------------
# Phase 8 — purge (inactive + >90d, churn-type-scoped)
# ---------------------------------------------------------------------------


def test_purge_deletes_inactive_churn_older_than_90d(db):
    org = _make_org(db)
    old_inactive = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="churn",
        model_json={"model_type": "churn_logreg"},
        label_count=20,
        fit_at=datetime.utcnow() - timedelta(days=91),
        is_active=False,
    )
    db.add(old_inactive)
    db.commit()

    with patch("src.tasks.churn_classifier_training.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.purge_old_churn_classifier_models()

    assert db.query(OrgClassifierModel).filter_by(id=old_inactive.id).first() is None


def test_purge_keeps_recent_inactive_and_active_and_other_types(db):
    org = _make_org(db)
    recent_inactive = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="churn",
        model_json={"model_type": "churn_logreg"},
        label_count=20,
        fit_at=datetime.utcnow() - timedelta(days=89),
        is_active=False,
    )
    old_active = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="churn",
        model_json={"model_type": "churn_logreg"},
        label_count=20,
        fit_at=datetime.utcnow() - timedelta(days=200),
        is_active=True,
    )
    old_sentiment_inactive = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="sentiment",
        model_json={"model_type": "tfidf_logreg"},
        label_count=20,
        fit_at=datetime.utcnow() - timedelta(days=200),
        is_active=False,
    )
    db.add_all([recent_inactive, old_active, old_sentiment_inactive])
    db.commit()

    with patch("src.tasks.churn_classifier_training.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        result = tasks.purge_old_churn_classifier_models()

    assert result == {"deleted": 0}
    assert db.query(OrgClassifierModel).filter_by(id=recent_inactive.id).first() is not None
    assert db.query(OrgClassifierModel).filter_by(id=old_active.id).first() is not None
    # type-scoped: an old inactive SENTIMENT row is not this purge's business
    assert db.query(OrgClassifierModel).filter_by(id=old_sentiment_inactive.id).first() is not None


# ---------------------------------------------------------------------------
# Phase 9 — retrain_all_orgs orchestration + per-org isolation + folded purge
# ---------------------------------------------------------------------------


def test_retrain_all_orgs_only_processes_orgs_with_trainable_labels(db):
    org_eligible = _make_org(db, "Eligible")
    org_below = _make_org(db, "Below")
    for i in range(25):
        _make_churn_event(db, org_eligible.id, f"c{i}@x.com")
    for i in range(5):
        _make_churn_event(db, org_below.id, f"b{i}@x.com")

    with patch("src.tasks.churn_classifier_training.retrain_org") as mock_retrain, \
         patch("src.tasks.churn_classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.churn_classifier_training.purge_old_churn_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_retrain.return_value = {"decision": "retained", "retained": True, "n": 25}
        mock_purge.return_value = {"deleted": 0}

        tasks = _get_tasks()
        result = tasks.retrain_all_orgs()

    mock_retrain.assert_called_once_with(org_eligible.id, db)
    assert result == {"trained": 1, "promoted": 0, "candidates": 0,
                      "skipped": 1, "held": 0, "locked": 0}


def test_retrain_all_orgs_tallies_all_decisions(db):
    orgs = [_make_org(db, f"Org{i}") for i in range(6)]
    for org in orgs:
        for i in range(25):
            _make_churn_event(db, org.id, f"c{i}@x.com")

    results_by_org = {
        orgs[0].id: {"decision": "promoted", "promoted": True, "n": 25},
        orgs[1].id: {"decision": "promoted_candidate", "promoted_candidate": True, "n": 25},
        orgs[2].id: {"decision": "retained", "retained": True, "n": 25},
        orgs[3].id: {"decision": "held", "held": True, "n": 25},
        orgs[4].id: {"decision": "skipped", "skipped": True, "reason": "below_min_labels", "n": 5},
        orgs[5].id: {"skipped": True, "reason": "locked"},
    }

    def side_effect(org_id, session):
        return results_by_org[org_id]

    with patch("src.tasks.churn_classifier_training.retrain_org", side_effect=side_effect), \
         patch("src.tasks.churn_classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.churn_classifier_training.purge_old_churn_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_purge.return_value = {"deleted": 2}

        tasks = _get_tasks()
        result = tasks.retrain_all_orgs()

    assert result == {"trained": 4, "promoted": 1, "candidates": 1,
                      "skipped": 1, "held": 1, "locked": 1}


def test_retrain_all_orgs_isolates_per_org_exception(db):
    """org2's failure must leave the SHARED session usable for org1/org3's
    iterations (rollback discipline)."""
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    org3 = _make_org(db, "Org3")
    for org in (org1, org2, org3):
        for i in range(25):
            _make_churn_event(db, org.id, f"c{i}@x.com")

    processed = []

    def side_effect(org_id, session):
        processed.append(org_id)
        if org_id == org2.id:
            bad_run = OrgClassifierEvalRun(
                organization_id=org2.id,
                classifier_type=None,  # NOT NULL violation
                decision=None,  # NOT NULL violation
                n=1,
            )
            session.add(bad_run)
            session.flush()  # raises IntegrityError
            return {"decision": "retained", "retained": True, "n": 25}  # unreachable
        good_run = OrgClassifierEvalRun(
            organization_id=org_id,
            classifier_type="churn",
            decision="retained",
            n=25,
        )
        session.add(good_run)
        session.commit()
        return {"decision": "retained", "retained": True, "n": 25}

    with patch("src.tasks.churn_classifier_training.retrain_org", side_effect=side_effect), \
         patch("src.tasks.churn_classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.churn_classifier_training.purge_old_churn_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_purge.return_value = {"deleted": 0}

        tasks = _get_tasks()
        result = tasks.retrain_all_orgs()  # must not raise

    assert set(processed) == {org1.id, org2.id, org3.id}
    assert result["trained"] == 2  # org1 + org3; org2 isolated-failed

    org3_runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org3.id).all()
    assert len(org3_runs) == 1


def test_retrain_all_orgs_runs_purge_once(db):
    org = _make_org(db)
    for i in range(25):
        _make_churn_event(db, org.id, f"c{i}@x.com")

    with patch("src.tasks.churn_classifier_training.retrain_org") as mock_retrain, \
         patch("src.tasks.churn_classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.churn_classifier_training.purge_old_churn_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_retrain.return_value = {"decision": "retained", "retained": True, "n": 25}
        mock_purge.return_value = {"deleted": 3}

        tasks = _get_tasks()
        tasks.retrain_all_orgs()

    mock_purge.assert_called_once()
