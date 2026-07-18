"""
Tests for probability_updater.update() — Phase 3.1.

All 14 tests follow strict TDD: written RED before implementation,
then driven GREEN by src/services/probability_updater.py.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, CustomerHealth, CustomerHealthHistory, ChurnCalibrationModel


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
# Helper builders
# ---------------------------------------------------------------------------

def _make_health(db, org_id: int = 1, email: str = "test@example.com", churn_risk_component: int = 50,
                 sentiment_component: int = 50, probability_computed_at=None) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        churn_risk_component=churn_risk_component,
        sentiment_component=sentiment_component,
        probability_computed_at=probability_computed_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_history(db, health_id: int, org_id: int, churn_risk_component: int,
                  recorded_at=None) -> CustomerHealthHistory:
    row = CustomerHealthHistory(
        customer_health_id=health_id,
        organization_id=org_id,
        health_score=50,
        churn_risk_component=churn_risk_component,
        recorded_at=recorded_at or (datetime.utcnow() - timedelta(days=1)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_calibration_model(db, org_id=None, is_active=True, label_count=50,
                            positive_count=10) -> ChurnCalibrationModel:
    """Seed a calibration model with a simple 2-breakpoint model_json."""
    # Not identity: maps 0→0.0, 100→0.8 (non-linear vs identity)
    model_json = {
        "breakpoints": [0, 50, 100],
        "probabilities": [0.05, 0.40, 0.80],
        "threshold_bands": {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
    }
    row = ChurnCalibrationModel(
        organization_id=org_id,
        model_json=model_json,
        label_count=label_count,
        positive_count=positive_count,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from src.services import probability_updater  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_update_persists_probability_when_no_calibration_exists(db):
    """No model in DB → uses identity model → probability == churn_risk_component / 100."""
    health = _make_health(db, churn_risk_component=60)
    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    assert health.churn_probability is not None
    assert abs(float(health.churn_probability) - 0.60) < 0.001


def test_update_uses_org_specific_calibration_when_available(db):
    """Org calibration model → probability derived from it, not identity."""
    health = _make_health(db, org_id=1, churn_risk_component=50)
    _make_calibration_model(db, org_id=1, is_active=True)

    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    # Our custom model maps 50 → 0.40, identity maps 50 → 0.50
    assert health.churn_probability is not None
    assert abs(float(health.churn_probability) - 0.40) < 0.01


def test_update_falls_back_to_global_model_when_no_org_model(db):
    """Global model (org_id IS NULL, is_active=True) used when no org model present."""
    health = _make_health(db, org_id=1, churn_risk_component=50)
    _make_calibration_model(db, org_id=None, is_active=True)  # global model

    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    # Same custom interpolation as previous test, but from global model
    assert health.churn_probability is not None
    assert abs(float(health.churn_probability) - 0.40) < 0.01


def test_update_skips_when_churn_risk_component_changed_less_than_two_points(db):
    """Hysteresis: component moved < 2 pts → no recompute (probability_computed_at unchanged)."""
    old_ts = datetime(2026, 1, 1, 12, 0, 0)
    health = _make_health(db, churn_risk_component=51, probability_computed_at=old_ts)
    _make_history(db, health.id, org_id=1, churn_risk_component=50)

    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    # probability_computed_at must still be the old timestamp
    assert health.probability_computed_at is not None
    assert abs((health.probability_computed_at - old_ts).total_seconds()) < 1


def test_update_recomputes_when_churn_risk_component_changed_by_at_least_two(db):
    """Hysteresis threshold met: component moved ≥ 2 pts → probability_computed_at updated."""
    old_ts = datetime(2026, 1, 1, 12, 0, 0)
    health = _make_health(db, churn_risk_component=53, probability_computed_at=old_ts)
    _make_history(db, health.id, org_id=1, churn_risk_component=50)

    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    assert health.probability_computed_at is not None
    assert health.probability_computed_at > old_ts


def test_update_recomputes_unconditionally_when_no_history_exists(db):
    """No history rows → always recompute regardless of current component value."""
    old_ts = datetime(2026, 1, 1, 12, 0, 0)
    health = _make_health(db, churn_risk_component=50, probability_computed_at=old_ts)

    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    assert health.probability_computed_at > old_ts


def test_update_persists_timeline_bucket(db):
    """time_to_churn_bucket is set to a valid enum value after update."""
    VALID_BUCKETS = {"immediate", "2w", "2-4w", "1-3m", "low"}
    _make_health(db, churn_risk_component=70)

    probability_updater.update(1, "test@example.com", db)

    db.execute  # ensure we work via ORM
    health = db.query(CustomerHealth).filter_by(
        organization_id=1, customer_email="test@example.com"
    ).first()

    assert health.time_to_churn_bucket in VALID_BUCKETS


def test_update_persists_confidence_interval_bounds(db):
    """CI bounds satisfy: low <= probability <= high."""
    _make_health(db, churn_risk_component=60)

    probability_updater.update(1, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=1, customer_email="test@example.com"
    ).first()

    p = float(health.churn_probability)
    lo = float(health.churn_probability_low)
    hi = float(health.churn_probability_high)

    assert lo <= p <= hi


def test_update_persists_calibration_model_id_when_using_db_model(db):
    """calibration_model_id is set to the active model's PK when a DB model is used."""
    _make_health(db, org_id=1, churn_risk_component=50)
    model = _make_calibration_model(db, org_id=1, is_active=True)

    probability_updater.update(1, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=1, customer_email="test@example.com"
    ).first()

    assert health.calibration_model_id == model.id


def test_update_persists_null_calibration_model_id_when_using_identity_fallback(db):
    """calibration_model_id is NULL when identity model (no DB model) is used."""
    _make_health(db, churn_risk_component=50)

    probability_updater.update(1, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=1, customer_email="test@example.com"
    ).first()

    assert health.calibration_model_id is None


def test_update_handles_missing_customer_health_gracefully(db):
    """No CustomerHealth row for customer → function returns without raising."""
    # Should not raise; nothing to update
    probability_updater.update(1, "nobody@example.com", db)


def test_update_handles_corrupted_model_json_falls_back_to_identity(db):
    """Malformed model_json in DB → catch error, fall back to identity model."""
    health = _make_health(db, org_id=1, churn_risk_component=60)

    # Seed a model with corrupted model_json (missing required keys)
    bad_model = ChurnCalibrationModel(
        organization_id=1,
        model_json={"corrupted": True},  # missing breakpoints/probabilities
        label_count=5,
        positive_count=1,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        is_active=True,
    )
    db.add(bad_model)
    db.commit()

    # Must not raise; falls back to identity
    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    # Identity: p ≈ 0.60
    assert health.churn_probability is not None
    assert abs(float(health.churn_probability) - 0.60) < 0.001


def test_update_uses_inactive_models_disregarded(db):
    """is_active=FALSE org model is ignored; global active model is used instead."""
    health = _make_health(db, org_id=1, churn_risk_component=50)
    _make_calibration_model(db, org_id=1, is_active=False)   # inactive org model
    _make_calibration_model(db, org_id=None, is_active=True)  # active global model

    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    # Global model (same custom json) maps 50 → 0.40, not identity 0.50
    assert health.churn_probability is not None
    assert abs(float(health.churn_probability) - 0.40) < 0.01


def test_update_idempotent_when_called_twice(db):
    """Second call short-circuits via hysteresis (component didn't change between calls)."""
    health = _make_health(db, churn_risk_component=55)

    # First call — computes and persists
    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)
    ts_after_first = health.probability_computed_at

    assert ts_after_first is not None

    # Between first and second call, a history row will have been written by
    # the health-score service (simulated here manually with the same component)
    _make_history(db, health.id, org_id=1, churn_risk_component=55,
                  recorded_at=ts_after_first - timedelta(seconds=1))

    # Second call: component is still 55, history says 55 → delta=0 < 2 → skip
    probability_updater.update(1, "test@example.com", db)
    db.refresh(health)

    # probability_computed_at must not have moved
    assert health.probability_computed_at == ts_after_first


# ---------------------------------------------------------------------------
# Seam: automation_churn_trigger dispatch (Task 4, churn-triggered-playbooks)
# ---------------------------------------------------------------------------


def test_update_calls_churn_trigger_evaluator_with_new_probability(db):
    """update() invokes evaluate_churn_probability_triggers with the fresh (org, email, p, db)."""
    _make_health(db, org_id=1, churn_risk_component=60)

    with patch(
        "src.services.automation_churn_trigger.evaluate_churn_probability_triggers"
    ) as mock_evaluate:
        probability_updater.update(1, "test@example.com", db)

    mock_evaluate.assert_called_once()
    args, kwargs = mock_evaluate.call_args
    assert args[0] == 1
    assert args[1] == "test@example.com"
    assert isinstance(args[2], float)
    assert abs(args[2] - 0.60) < 0.001
    assert args[3] is db


def test_update_swallows_churn_trigger_evaluator_exceptions(db):
    """An exception raised by the evaluator must NOT propagate out of update()."""
    health = _make_health(db, org_id=1, churn_risk_component=60)

    with patch(
        "src.services.automation_churn_trigger.evaluate_churn_probability_triggers",
        side_effect=RuntimeError("boom"),
    ):
        # Must not raise.
        probability_updater.update(1, "test@example.com", db)

    db.refresh(health)
    # The probability update itself must still have succeeded.
    assert health.churn_probability is not None
    assert abs(float(health.churn_probability) - 0.60) < 0.001
