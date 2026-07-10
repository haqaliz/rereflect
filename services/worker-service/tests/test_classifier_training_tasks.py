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
from contextlib import contextmanager
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
# Redis-lock / incumbent-predictor patch helpers (shared by Phase 3+ tests)
# ---------------------------------------------------------------------------


def _fake_redis_lock_acquired():
    """A fake `_get_redis()` whose lock() always acquires successfully."""
    fake_lock = MagicMock()
    fake_lock.acquire.return_value = True
    fake_r = MagicMock()
    fake_r.lock.return_value = fake_lock
    return fake_r, fake_lock


def _fake_redis_lock_denied():
    """A fake `_get_redis()` whose lock() never acquires (already held)."""
    fake_lock = MagicMock()
    fake_lock.acquire.return_value = False
    fake_r = MagicMock()
    fake_r.lock.return_value = fake_lock
    return fake_r, fake_lock


@contextmanager
def _patch_core(decision: str, *, n: int = 25, incumbent_macro_f1=0.50,
                 challenger_macro_f1=0.65, macro_f1_delta=0.15, notes=None,
                 dataset=None, artifact=None):
    """Patch the training-and-eval-core's build_sentiment_dataset/evaluate/
    train_classifier so retrain_org's decision is fully deterministic, without
    needing sklearn to actually fit anything. Mirrors the plan's "patch the core
    via the autouse stub" strategy."""
    from analyzer.corrections_classifier.evaluate import EvalResult

    if notes is None:
        notes = f"{decision} (delta={macro_f1_delta:+.4f}, n={n})" if macro_f1_delta is not None else decision
    if dataset is None:
        labels = ["positive", "neutral", "negative"]
        dataset = [(f"text {i}", labels[i % 3]) for i in range(n)]
    if artifact is None:
        artifact = {
            "model_type": "tfidf_logreg",
            "classifier_type": "sentiment",
            "classes": ["negative", "neutral", "positive"],
            "vectorizer": {"vocabulary": {}, "idf": [], "lowercase": True,
                           "token_pattern": r"(?u)\b\w\w+\b", "ngram_range": [1, 1],
                           "norm": "l2", "sublinear_tf": False, "smooth_idf": True},
            "logreg": {"coef": [[0.0]], "intercept": [0.0], "multi_class": "multinomial"},
            "label_count": n,
        }

    fake_result = EvalResult(
        decision=decision, n=n,
        incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
        macro_f1_delta=macro_f1_delta, notes=notes,
    )

    with patch("analyzer.corrections_classifier.dataset.build_sentiment_dataset", return_value=dataset), \
         patch("analyzer.corrections_classifier.evaluate.evaluate", return_value=fake_result), \
         patch("analyzer.corrections_classifier.trainer.train_classifier", return_value=artifact):
        yield fake_result, artifact


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


# ---------------------------------------------------------------------------
# Phase 3 — retrain_org below-gate skip path
# ---------------------------------------------------------------------------
#
# Below min_labels, evaluate() short-circuits BEFORE ever calling train_fn or
# incumbent_predict (pure stdlib path, no sklearn needed) — so these tests seed a
# real (< MIN_LABELS) AICorrection set and let the REAL build_sentiment_dataset +
# evaluate run for real. Only the Redis lock is faked (no real Redis in tests).


def test_retrain_org_below_gate_writes_one_skipped_eval_run(db):
    org = _make_org(db)
    _seed_corrections(db, org.id, count=5)  # well under MIN_LABELS=20
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    runs = db.query(OrgClassifierEvalRun).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.decision == "skipped"
    assert run.n == 5
    assert run.notes
    assert run.duration_ms is not None and run.duration_ms >= 0
    assert run.classifier_model_id is None


def test_retrain_org_below_gate_creates_zero_model_rows(db):
    org = _make_org(db)
    _seed_corrections(db, org.id, count=5)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    assert db.query(OrgClassifierModel).count() == 0


def test_retrain_org_below_gate_return_shape(db):
    org = _make_org(db)
    _seed_corrections(db, org.id, count=5)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result["skipped"] is True
    assert "promoted" not in result


# ---------------------------------------------------------------------------
# Phase 4 — retrain_org promote path + atomic-swap invariant
# ---------------------------------------------------------------------------


def test_retrain_org_promote_inserts_one_active_model(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65) as (fake_result, artifact):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    models = db.query(OrgClassifierModel).filter_by(organization_id=org.id).all()
    assert len(models) == 1
    model = models[0]
    assert model.is_active is True
    assert model.classifier_type == "sentiment"
    assert float(model.macro_f1) == pytest.approx(0.65, abs=1e-4)
    assert model.label_count == 25
    assert model.fit_at is not None
    assert model.model_json == artifact


def test_retrain_org_promote_flips_prior_active_inactive(db):
    org = _make_org(db)
    prior = _make_active_model(db, org.id, macro_f1=0.40)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    db.refresh(prior)
    assert prior.is_active is False

    active_models = (
        db.query(OrgClassifierModel)
        .filter_by(organization_id=org.id, classifier_type="sentiment", is_active=True)
        .all()
    )
    assert len(active_models) == 1
    assert active_models[0].id != prior.id


def test_retrain_org_promote_writes_one_promoted_eval_run(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, incumbent_macro_f1=0.50,
                      challenger_macro_f1=0.65, macro_f1_delta=0.15):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.decision == "promoted"
    assert float(run.macro_f1_delta) == pytest.approx(0.15, abs=1e-4)
    assert float(run.incumbent_macro_f1) == pytest.approx(0.50, abs=1e-4)
    assert float(run.challenger_macro_f1) == pytest.approx(0.65, abs=1e-4)

    new_model = db.query(OrgClassifierModel).filter_by(organization_id=org.id).one()
    assert run.classifier_model_id == new_model.id


def test_active_invariant_holds_across_repeated_refits(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    for i in range(3):
        with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
             _patch_core("promoted", n=25, challenger_macro_f1=0.60 + i * 0.01):
            tasks = _get_tasks()
            tasks.retrain_org(org.id, db)

        active_count = (
            db.query(OrgClassifierModel)
            .filter_by(organization_id=org.id, classifier_type="sentiment", is_active=True)
            .count()
        )
        assert active_count == 1, f"iteration {i}: expected exactly 1 active row"


# ---------------------------------------------------------------------------
# Phase 5 — retrain_org retained path (worse + small-holdout forced-retain)
# ---------------------------------------------------------------------------


def test_retrain_org_worse_challenger_creates_no_model_row(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("retained", n=25, incumbent_macro_f1=0.65, challenger_macro_f1=0.60,
                      macro_f1_delta=-0.05):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    assert db.query(OrgClassifierModel).count() == 0


def test_retrain_org_worse_challenger_writes_one_retained_eval_run(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("retained", n=25, incumbent_macro_f1=0.65, challenger_macro_f1=0.60,
                      macro_f1_delta=-0.05):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.decision == "retained"
    assert float(run.macro_f1_delta) == pytest.approx(-0.05, abs=1e-4)
    assert run.classifier_model_id is None


def test_retrain_org_small_holdout_retained_with_note(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("retained", n=3, incumbent_macro_f1=None, challenger_macro_f1=None,
                      macro_f1_delta=None, notes="held-out too small"):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "retained"
    assert run.notes == "held-out too small"
    assert db.query(OrgClassifierModel).count() == 0


def test_retrain_org_promote_then_worse_keeps_prior_active(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    promoted_model = db.query(OrgClassifierModel).filter_by(organization_id=org.id).one()
    assert promoted_model.is_active is True

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("retained", n=25, incumbent_macro_f1=0.65, challenger_macro_f1=0.60,
                      macro_f1_delta=-0.05):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    db.refresh(promoted_model)
    assert promoted_model.is_active is True
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 1

    active_count = (
        db.query(OrgClassifierModel)
        .filter_by(organization_id=org.id, classifier_type="sentiment", is_active=True)
        .count()
    )
    assert active_count == 1


# ---------------------------------------------------------------------------
# Phase 6 — per-org advisory lock (overlap guard)
# ---------------------------------------------------------------------------


def test_retrain_org_acquires_per_org_lock(db):
    org = _make_org(db)
    fake_r, fake_lock = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    fake_r.lock.assert_called_once()
    args, kwargs = fake_r.lock.call_args
    assert args[0] == f"lock:classifier_refit:{org.id}"
    fake_lock.acquire.assert_called_once_with(blocking=False)


def test_retrain_org_lock_not_acquired_skips_without_writes(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_denied()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r):
        tasks = _get_tasks()
        result = tasks.retrain_org(org.id, db)

    assert result == {"decision": "skipped", "skipped": True, "reason": "locked"}
    assert db.query(OrgClassifierEvalRun).count() == 0
    assert db.query(OrgClassifierModel).count() == 0


def test_retrain_org_releases_lock_in_finally(db):
    org = _make_org(db)
    fake_r, fake_lock = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.corrections_classifier.dataset.build_sentiment_dataset",
               side_effect=RuntimeError("boom")):
        tasks = _get_tasks()
        with pytest.raises(RuntimeError):
            tasks.retrain_org(org.id, db)

    fake_lock.release.assert_called_once()
