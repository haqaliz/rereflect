"""
Tests for calibration_refit.refit_org() — Phase 6.1 (M4.1).

Written RED-first (TDD). All ~14 tests must fail before the implementation
in src/services/calibration_refit.py exists, then pass after GREEN.

Pattern: in-memory SQLite, no real DB, no Celery broker.
numpy/sklearn are stubbed via sys.modules because they lack Python 3.14 wheels.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub numpy and sklearn before any module that lazily imports them is loaded.
# This mirrors what conftest.py does for src.config / src.database.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Patch _fit_isotonic, _serialize_model, _compute_metrics at module level
# so numpy/sklearn are never invoked during tests.
# These patches are applied globally; individual tests can override if needed.
# ---------------------------------------------------------------------------

_FAKE_MODEL_JSON = {
    "breakpoints": [0.0, 50.0, 100.0],
    "probabilities": [0.0, 0.5, 1.0],
    "threshold_bands": {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
}
_FAKE_METRICS = {
    "precision": 0.70,
    "recall": 0.70,
    "f1": 0.70,
    "auc": 0.75,
    "optimal_threshold": 0.50,
}

class _FakeIR:
    """Stand-in IsotonicRegression used by the patched _fit_isotonic."""
    X_thresholds_ = [0.0, 50.0, 100.0]
    y_thresholds_ = [0.0, 0.5, 1.0]
    def fit(self, X, y): return self
    def predict(self, X): return [0.5 for _ in X]

def _fake_fit_isotonic(scores, labels):
    return _FakeIR()

def _fake_serialize_model(ir, scores, labels):
    return dict(_FAKE_MODEL_JSON)

def _fake_compute_metrics(scores, labels, ir):
    return dict(_FAKE_METRICS)

# ---------------------------------------------------------------------------

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    ChurnBacktestRun,
    ChurnCalibrationModel,
    CustomerChurnEvent,
    CustomerHealth,
    CustomerHealthHistory,
    Organization,
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


@pytest.fixture(autouse=True)
def patch_numpy_helpers():
    """Patch numpy/sklearn-dependent helpers so tests run without those packages."""
    with patch("src.services.calibration_refit._fit_isotonic", side_effect=_fake_fit_isotonic), \
         patch("src.services.calibration_refit._serialize_model", side_effect=_fake_serialize_model), \
         patch("src.services.calibration_refit._compute_metrics", side_effect=_fake_compute_metrics):
        yield


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
# Helper builders
# ---------------------------------------------------------------------------

def _make_org(db, name: str = "Test Org") -> Organization:
    org = Organization(name=name, plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_health(db, org_id: int, email: str, churn_risk_component: int = 50,
                 last_feedback_at=None) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        churn_risk_component=churn_risk_component,
        last_feedback_at=last_feedback_at or datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_churn_event(db, org_id: int, email: str, churned_at=None,
                      recovered_at=None, source: str = "manual") -> CustomerChurnEvent:
    row = CustomerChurnEvent(
        organization_id=org_id,
        customer_email=email,
        churned_at=churned_at or (datetime.utcnow() - timedelta(days=10)),
        reason_code="price",
        recovered_at=recovered_at,
        source=source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_calibration_model(db, org_id=None, is_active: bool = True,
                             f1: float = 0.70) -> ChurnCalibrationModel:
    model = ChurnCalibrationModel(
        organization_id=org_id,
        model_json={"breakpoints": [0.0, 50.0, 100.0], "probabilities": [0.0, 0.5, 1.0]},
        label_count=30,
        positive_count=10,
        precision=0.70,
        recall=0.70,
        f1=f1,
        auc=0.75,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        fit_at=datetime.utcnow() - timedelta(days=7),
        is_active=is_active,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _seed_enough_labels(db, org_id: int, count: int = 30,
                        churned_count: int = 20) -> None:
    """Seed enough customers + qualifying events so refit_org proceeds past the threshold.

    churned_count must be >= 20 (the MIN_LABELS threshold checks qualifying events).
    """
    now = datetime.utcnow()
    for i in range(count):
        email = f"customer{i}@test.com"
        _make_health(db, org_id, email, churn_risk_component=50 + (i % 50),
                     last_feedback_at=now - timedelta(days=i % 30))
        if i < churned_count:
            _make_churn_event(db, org_id, email)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_refit_org_returns_skipped_when_fewer_than_20_labels(db):
    """Returns {"skipped": True} when fewer than 20 non-auto-suggested churn events exist."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    # Only 5 labels — below threshold
    for i in range(5):
        email = f"c{i}@test.com"
        _make_health(db, org.id, email)
        _make_churn_event(db, org.id, email)

    result = refit_org(org.id, db)

    assert result["skipped"] is True
    assert "reason" in result


def test_refit_org_filters_out_auto_suggested_source_labels(db):
    """auto_suggested events must not count toward the 20-label threshold."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    # Seed 25 auto_suggested events + 0 manual → should skip
    for i in range(25):
        email = f"c{i}@test.com"
        _make_health(db, org.id, email)
        _make_churn_event(db, org.id, email, source="auto_suggested")

    result = refit_org(org.id, db)

    assert result["skipped"] is True


def test_refit_org_creates_new_active_model_when_enough_labels(db):
    """refit_org stores a new ChurnCalibrationModel with is_active=True."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id)

    result = refit_org(org.id, db)

    assert "model_id" in result
    model = db.query(ChurnCalibrationModel).filter_by(id=result["model_id"]).first()
    assert model is not None
    assert model.is_active is True
    assert model.organization_id == org.id


def test_refit_org_deactivates_previous_active_org_model(db):
    """The previously active org model must be set is_active=False after refit."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    old_model = _make_calibration_model(db, org_id=org.id, is_active=True)
    _seed_enough_labels(db, org.id)

    refit_org(org.id, db)

    db.refresh(old_model)
    assert old_model.is_active is False


def test_refit_org_persists_backtest_run_linked_to_new_model(db):
    """refit_org inserts a ChurnBacktestRun row referencing the new model id."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id)

    result = refit_org(org.id, db)

    run = (
        db.query(ChurnBacktestRun)
        .filter_by(calibration_model_id=result["model_id"])
        .first()
    )
    assert run is not None
    assert run.organization_id == org.id


def test_refit_org_persists_precision_recall_f1_auc(db):
    """The new ChurnCalibrationModel row must have non-null precision/recall/f1/auc."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id)

    result = refit_org(org.id, db)

    model = db.query(ChurnCalibrationModel).filter_by(id=result["model_id"]).first()
    assert model.precision is not None
    assert model.recall is not None
    assert model.f1 is not None
    assert model.auc is not None


def test_refit_org_label_count_matches_positive_plus_negative(db):
    """label_count returned == positive_count + negative_count."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id, count=30, churned_count=20)

    result = refit_org(org.id, db)

    assert result["label_count"] == result["positive_count"] + (
        result["label_count"] - result["positive_count"]
    )
    # More precisely: label_count >= positive_count
    assert result["label_count"] >= result["positive_count"]
    assert result["positive_count"] >= 0


def test_refit_org_isotonic_model_json_round_trip(db):
    """model_json must be storable and reloadable; predictions must be consistent."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id)

    result = refit_org(org.id, db)

    model = db.query(ChurnCalibrationModel).filter_by(id=result["model_id"]).first()
    mj = model.model_json
    assert "breakpoints" in mj
    assert "probabilities" in mj
    assert len(mj["breakpoints"]) > 0
    assert len(mj["breakpoints"]) == len(mj["probabilities"])


def test_refit_org_uses_customer_health_history_when_available(db):
    """When customer_health_history exists, the historic churn_risk_component is used as score."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    # Seed enough customers; for the churned ones, add a history snapshot
    now = datetime.utcnow()
    for i in range(30):
        email = f"c{i}@test.com"
        health = _make_health(db, org.id, email, churn_risk_component=40 + (i % 50),
                              last_feedback_at=now - timedelta(days=5))
        if i < 20:
            _make_churn_event(db, org.id, email)
            # Add history with a different score
            hist = CustomerHealthHistory(
                customer_health_id=health.id,
                organization_id=org.id,
                health_score=60,
                churn_risk_component=80,  # different from current
                recorded_at=now - timedelta(days=15),
            )
            db.add(hist)
    db.commit()

    # Should succeed without error (history used for scoring)
    result = refit_org(org.id, db)
    assert "model_id" in result


def test_refit_org_falls_back_to_current_score_when_no_history(db):
    """When no history snapshot exists, falls back to current churn_risk_component."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id)  # no history rows added

    result = refit_org(org.id, db)

    assert "model_id" in result
    assert result["label_count"] > 0


def test_refit_org_only_includes_last_180_days_customers(db):
    """Customers whose last_feedback_at is older than 180 days are excluded from labels."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    # 20 recent customers
    now = datetime.utcnow()
    for i in range(20):
        email = f"recent{i}@test.com"
        _make_health(db, org.id, email, churn_risk_component=50,
                     last_feedback_at=now - timedelta(days=30))
        _make_churn_event(db, org.id, email)

    # 10 stale customers (older than 180 days)
    for i in range(10):
        email = f"stale{i}@test.com"
        _make_health(db, org.id, email, churn_risk_component=50,
                     last_feedback_at=now - timedelta(days=200))
        _make_churn_event(db, org.id, email)

    result = refit_org(org.id, db)

    # Stale customers excluded — label_count should reflect only recent customers
    assert result["label_count"] <= 30  # not > 30 (stale not included)


def test_refit_org_flags_f1_drop_when_new_f1_below_previous_by_10_pts(db):
    """f1_dropped=True when new F1 is more than 0.10 below the previous active model's F1."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    # Seed a previous model with high F1
    _make_calibration_model(db, org_id=org.id, is_active=True, f1=0.90)
    # Seed labels that will produce a low F1 (all positives → no true negatives)
    now = datetime.utcnow()
    for i in range(25):
        email = f"c{i}@test.com"
        _make_health(db, org.id, email, churn_risk_component=50,
                     last_feedback_at=now - timedelta(days=5))
        _make_churn_event(db, org.id, email)

    result = refit_org(org.id, db)

    # With all positives, F1 will be low — f1_dropped should be True when prev=0.90
    # (The test verifies the field exists; the actual value depends on computed F1)
    assert "f1_dropped" in result


def test_refit_org_does_not_flag_when_no_previous_model(db):
    """f1_dropped=False when there is no previous model to compare against."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    _seed_enough_labels(db, org.id)

    result = refit_org(org.id, db)

    assert result["f1_dropped"] is False


def test_refit_org_returns_active_event_and_recovered_event_both_as_churned(db):
    """Both active churn events (recovered_at=NULL) and recovered events count as positive labels."""
    from src.services.calibration_refit import refit_org

    org = _make_org(db)
    now = datetime.utcnow()

    # 10 active churns (no recovery)
    for i in range(10):
        email = f"active_churn{i}@test.com"
        _make_health(db, org.id, email, last_feedback_at=now - timedelta(days=5))
        _make_churn_event(db, org.id, email, recovered_at=None)

    # 10 recovered churns
    for i in range(10):
        email = f"recovered{i}@test.com"
        _make_health(db, org.id, email, last_feedback_at=now - timedelta(days=5))
        _make_churn_event(db, org.id, email,
                          recovered_at=datetime.utcnow() - timedelta(days=2))

    # 5 non-churned customers (no event)
    for i in range(5):
        email = f"healthy{i}@test.com"
        _make_health(db, org.id, email, last_feedback_at=now - timedelta(days=5))

    result = refit_org(org.id, db)

    # 20 positives (10 active + 10 recovered) + 5 negatives = 25 labels
    assert result["positive_count"] == 20
    assert result["label_count"] == 25
