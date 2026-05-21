"""
Tests for Celery tasks in tasks.churn_calibration — Phase 6.1 (M4.1).

Written RED-first (TDD). All ~9 tests must fail before the implementation
in src/tasks/churn_calibration.py exists, then pass after GREEN.

Strategy: patch refit_org + DB session; test task orchestration logic only.
numpy/sklearn are stubbed because they lack Python 3.14 wheels.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub numpy and sklearn before lazy imports inside task / refit modules fire.
# ---------------------------------------------------------------------------
class _TolistList(list):
    """List subclass that supports .tolist() for sklearn threshold compatibility."""
    def tolist(self):
        return list(self)


class _FakeIR:
    """Minimal IsotonicRegression stub for task-level tests."""
    X_thresholds_ = _TolistList([0.0, 50.0, 100.0])
    y_thresholds_ = _TolistList([0.0, 0.5, 1.0])

    def fit(self, X, y):
        return self

    def predict(self, X):
        return _TolistList([0.5 for _ in X])


class _TolistList(list):
    def tolist(self):
        return list(self)


class _FakeNP:
    """Minimal numpy stub sufficient for refit_global_calibration."""
    @staticmethod
    def array(x, dtype=None):
        return _TolistList(x)

    @staticmethod
    def unique(x):
        return _TolistList(sorted(set(x)))


class _FakeSklearnIsotonic:
    IsotonicRegression = _FakeIR

# ---------------------------------------------------------------------------

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch
import builtins

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
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db, name: str = "Org") -> Organization:
    org = Organization(name=name, plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _seed_churn_events(db, org_id: int, count: int = 25,
                       source: str = "manual") -> None:
    now = datetime.utcnow()
    for i in range(count):
        email = f"c{i}_{org_id}@test.com"
        health = CustomerHealth(
            organization_id=org_id,
            customer_email=email,
            churn_risk_component=50,
            last_feedback_at=now - timedelta(days=5),
        )
        db.add(health)
        db.flush()
        event = CustomerChurnEvent(
            organization_id=org_id,
            customer_email=email,
            churned_at=now - timedelta(days=10),
            reason_code="price",
            source=source,
        )
        db.add(event)
    db.commit()


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


# ---------------------------------------------------------------------------
# Autouse fixture: patch numpy/sklearn inside the task module's lazy imports
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_numpy_for_tasks():
    """Patch numpy and sklearn inside the task and refit modules."""
    fake_np = _FakeNP()
    fake_isotonic = _FakeSklearnIsotonic()
    with patch.dict(sys.modules, {
        "numpy": fake_np,
        "sklearn": MagicMock(),
        "sklearn.isotonic": fake_isotonic,
        "sklearn.metrics": MagicMock(roc_auc_score=MagicMock(return_value=0.75)),
    }):
        yield


# ---------------------------------------------------------------------------
# Task import alias (lazy — avoids importing Celery at collection time)
# ---------------------------------------------------------------------------

def _get_tasks():
    import src.tasks.churn_calibration as churn_calibration
    return churn_calibration


# ---------------------------------------------------------------------------
# refit_all_orgs
# ---------------------------------------------------------------------------


def test_refit_all_orgs_calls_refit_org_for_each_eligible_org(db):
    """refit_all_orgs calls refit_org once per org with >= 20 manual labels."""
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    _seed_churn_events(db, org1.id, count=25)
    _seed_churn_events(db, org2.id, count=25)

    with patch("src.tasks.churn_calibration.refit_org") as mock_refit, \
         patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_refit.return_value = {"model_id": 1, "label_count": 25,
                                   "positive_count": 10, "f1": 0.70, "f1_dropped": False}

        tasks = _get_tasks()
        tasks.refit_all_orgs()

    assert mock_refit.call_count == 2
    called_org_ids = {c.args[0] for c in mock_refit.call_args_list}
    assert org1.id in called_org_ids
    assert org2.id in called_org_ids


def test_refit_all_orgs_skips_orgs_below_label_threshold(db):
    """refit_all_orgs does NOT call refit_org for orgs with < 20 manual labels."""
    org_small = _make_org(db, "SmallOrg")
    org_large = _make_org(db, "LargeOrg")
    _seed_churn_events(db, org_small.id, count=5)   # below threshold
    _seed_churn_events(db, org_large.id, count=25)  # above threshold

    with patch("src.tasks.churn_calibration.refit_org") as mock_refit, \
         patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_refit.return_value = {"model_id": 1, "label_count": 25,
                                   "positive_count": 10, "f1": 0.70, "f1_dropped": False}

        tasks = _get_tasks()
        tasks.refit_all_orgs()

    called_org_ids = {c.args[0] for c in mock_refit.call_args_list}
    assert org_small.id not in called_org_ids
    assert org_large.id in called_org_ids


def test_refit_all_orgs_returns_summary_counts(db):
    """refit_all_orgs returns {"refit_count": N, "skipped": M}."""
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    _seed_churn_events(db, org1.id, count=25)
    _seed_churn_events(db, org2.id, count=5)  # below threshold

    with patch("src.tasks.churn_calibration.refit_org") as mock_refit, \
         patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_refit.return_value = {"model_id": 1, "label_count": 25,
                                   "positive_count": 10, "f1": 0.70, "f1_dropped": False}

        tasks = _get_tasks()
        result = tasks.refit_all_orgs()

    assert result["refit_count"] == 1
    assert result["skipped"] == 1


def test_refit_all_orgs_handles_one_org_failure_without_aborting(db):
    """If refit_org raises for one org, processing continues for the rest."""
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    _seed_churn_events(db, org1.id, count=25)
    _seed_churn_events(db, org2.id, count=25)

    call_count = 0

    def side_effect(org_id, session):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated refit failure")
        return {"model_id": 2, "label_count": 25, "positive_count": 10,
                "f1": 0.70, "f1_dropped": False}

    with patch("src.tasks.churn_calibration.refit_org", side_effect=side_effect), \
         patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        result = tasks.refit_all_orgs()  # must not raise

    assert call_count == 2  # both orgs were attempted


# ---------------------------------------------------------------------------
# refit_global_calibration
# ---------------------------------------------------------------------------


def test_refit_global_calibration_pools_all_orgs_labels(db):
    """refit_global_calibration uses labels from all orgs combined."""
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    _seed_churn_events(db, org1.id, count=15)
    _seed_churn_events(db, org2.id, count=15)

    with patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        result = tasks.refit_global_calibration()

    assert result["label_count"] >= 30  # pooled from both orgs


def test_refit_global_calibration_deactivates_previous_global(db):
    """The previous global (org_id=NULL, is_active=True) model is deactivated."""
    old_global = _make_calibration_model(db, org_id=None, is_active=True)

    org1 = _make_org(db, "Org1")
    _seed_churn_events(db, org1.id, count=25)

    with patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.refit_global_calibration()

    db.refresh(old_global)
    assert old_global.is_active is False


def test_refit_global_calibration_stored_with_null_organization_id(db):
    """The new global calibration model is stored with organization_id=NULL."""
    org1 = _make_org(db, "Org1")
    _seed_churn_events(db, org1.id, count=25)

    with patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        result = tasks.refit_global_calibration()

    global_model = db.query(ChurnCalibrationModel).filter_by(
        id=result["global_model_id"]
    ).first()
    assert global_model is not None
    assert global_model.organization_id is None
    assert global_model.is_active is True


# ---------------------------------------------------------------------------
# purge_old_calibration_models
# ---------------------------------------------------------------------------


def test_purge_old_calibration_models_deletes_inactive_older_than_90_days(db):
    """Inactive models older than 90 days are deleted."""
    old_inactive = _make_calibration_model(db, org_id=None, is_active=False)
    # Force fit_at to be > 90 days ago
    old_inactive.fit_at = datetime.utcnow() - timedelta(days=100)
    db.commit()

    with patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.purge_old_calibration_models()

    remaining = db.query(ChurnCalibrationModel).filter_by(id=old_inactive.id).first()
    assert remaining is None


def test_purge_old_calibration_models_keeps_active_models(db):
    """Active models (even if old) are never deleted."""
    old_active = _make_calibration_model(db, org_id=None, is_active=True)
    old_active.fit_at = datetime.utcnow() - timedelta(days=200)
    db.commit()

    with patch("src.tasks.churn_calibration.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.purge_old_calibration_models()

    remaining = db.query(ChurnCalibrationModel).filter_by(id=old_active.id).first()
    assert remaining is not None
