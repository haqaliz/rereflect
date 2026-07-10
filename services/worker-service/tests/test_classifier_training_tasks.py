"""
Tests for Celery tasks in tasks.classifier_training — worker-trainer-and-schedule
aspect (M5.2 per-org-corrections-classifier).

Written RED-first (TDD), phase by phase, mirroring test_churn_calibration_tasks.py's
conventions: in-memory SQLite (Base.metadata.create_all), a `db` fixture, `_make_org`
seed helpers, a `_get_tasks()` lazy import to avoid importing Celery at collection, and
per-phase autouse-free patching of the core (analyzer.corrections_classifier.*) so
these tests never require sklearn/numpy to actually fit anything.

Because SQLite does not enforce the Postgres partial-unique on
(organization_id, classifier_type) WHERE is_active, the "exactly one active" invariant
is asserted via explicit count(*) queries — this validates the code's swap ordering,
which is the real target.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    AICorrection,
    Base,
    Organization,
    OrgClassifierEvalRun,
    OrgClassifierModel,
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


def _make_active_model(db, org_id: int, macro_f1: float = 0.60,
                        fit_at: datetime | None = None) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="sentiment",
        model_json={"model_type": "tfidf_logreg", "classes": ["negative", "neutral", "positive"]},
        label_count=30,
        precision=0.60,
        recall=0.60,
        macro_f1=macro_f1,
        accuracy=0.60,
        fit_at=fit_at or datetime.utcnow(),
        is_active=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _make_inactive_model(db, org_id: int | None, fit_at: datetime) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="sentiment",
        model_json={"model_type": "tfidf_logreg", "classes": ["negative", "neutral", "positive"]},
        label_count=25,
        precision=0.55,
        recall=0.55,
        macro_f1=0.55,
        accuracy=0.55,
        fit_at=fit_at,
        is_active=False,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _seed_corrections(db, org_id: int, count: int = 25) -> None:
    """Seed AICorrection rows that build_sentiment_dataset() will pick up for real."""
    labels = ["positive", "neutral", "negative"]
    for i in range(count):
        db.add(
            AICorrection(
                organization_id=org_id,
                correction_type="sentiment",
                entity_type="feedback_item",
                entity_id=None,
                signal="correction",
                original_value="neutral",
                corrected_value=labels[i % 3],
                feedback_text=f"feedback text number {i}",
            )
        )
    db.commit()


# ---------------------------------------------------------------------------
# Task import alias (lazy — avoids importing Celery at collection time)
# ---------------------------------------------------------------------------


def _get_tasks():
    import src.tasks.classifier_training as classifier_training
    return classifier_training


# ---------------------------------------------------------------------------
# Phase 1 — module skeleton + schedule wiring
# ---------------------------------------------------------------------------


def test_task_module_importable():
    """import src.tasks.classifier_training succeeds."""
    tasks = _get_tasks()
    assert hasattr(tasks, "retrain_all_orgs")
    assert hasattr(tasks, "retrain_org")
    assert hasattr(tasks, "purge_old_classifier_models")


def test_no_module_level_sklearn_import():
    """The task module must have zero module-level sklearn/numpy imports — heavy
    ML wheels live only inside the analysis-engine core, imported lazily."""
    import src.tasks.classifier_training as classifier_training

    source = open(classifier_training.__file__).read()
    for line in source.splitlines():
        if line.startswith((" ", "\t")):
            continue  # only inspect non-indented (module-top) lines
        assert not re.match(r"^\s*import\s+sklearn\b", line), line
        assert not re.match(r"^\s*import\s+numpy\b", line), line
        assert not re.match(r"^\s*from\s+sklearn\b", line), line
        assert not re.match(r"^\s*from\s+numpy\b", line), line


def test_beat_entry_registered():
    """celery_app.conf.beat_schedule has an entry for retrain_all_orgs at
    Mon 06:30 UTC."""
    from celery.schedules import crontab

    import src.celery_app as celery_app

    entries = celery_app.celery_app.conf.beat_schedule
    matching = [
        entry for entry in entries.values()
        if entry["task"] == "src.tasks.classifier_training.retrain_all_orgs"
    ]
    assert len(matching) == 1
    assert matching[0]["schedule"] == crontab(day_of_week=1, hour=6, minute=30)


def test_task_module_in_include():
    """src.tasks.classifier_training is registered in celery_app's include=[...]."""
    import src.celery_app as celery_app

    assert "src.tasks.classifier_training" in celery_app.celery_app.conf.include


# ---------------------------------------------------------------------------
# Phase 2 — purge_old_classifier_models()
# ---------------------------------------------------------------------------


def test_purge_deletes_inactive_older_than_90d(db):
    """Inactive model rows with fit_at older than 90 days are deleted."""
    org = _make_org(db)
    old_inactive = _make_inactive_model(db, org.id, fit_at=datetime.utcnow() - timedelta(days=91))

    with patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.purge_old_classifier_models()

    remaining = db.query(OrgClassifierModel).filter_by(id=old_inactive.id).first()
    assert remaining is None


def test_purge_keeps_recent_inactive(db):
    """Inactive model rows less than 90 days old are retained."""
    org = _make_org(db)
    recent_inactive = _make_inactive_model(db, org.id, fit_at=datetime.utcnow() - timedelta(days=89))

    with patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.purge_old_classifier_models()

    remaining = db.query(OrgClassifierModel).filter_by(id=recent_inactive.id).first()
    assert remaining is not None


def test_purge_keeps_active_even_if_old(db):
    """Active model rows are never purged, no matter how old."""
    org = _make_org(db)
    old_active = _make_active_model(db, org.id, fit_at=datetime.utcnow() - timedelta(days=200))

    with patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        tasks.purge_old_classifier_models()

    remaining = db.query(OrgClassifierModel).filter_by(id=old_active.id).first()
    assert remaining is not None


def test_purge_returns_deleted_count(db):
    """purge_old_classifier_models() returns {"deleted": N}."""
    org = _make_org(db)
    _make_inactive_model(db, org.id, fit_at=datetime.utcnow() - timedelta(days=100))
    _make_inactive_model(db, org.id, fit_at=datetime.utcnow() - timedelta(days=120))
    _make_inactive_model(db, org.id, fit_at=datetime.utcnow() - timedelta(days=10))  # too recent

    with patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        tasks = _get_tasks()
        result = tasks.purge_old_classifier_models()

    assert result == {"deleted": 2}
