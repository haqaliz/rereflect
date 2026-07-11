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


def test_promote_flushes_deactivation_before_inserting_new_active_row(db):
    """SQLAlchemy's unit-of-work emits INSERTs before UPDATEs within a single
    flush(). Postgres' partial-unique index uq_org_classifier_one_active
    (organization_id, classifier_type WHERE is_active) is IMMEDIATE, so if the
    deactivating UPDATE and the new active INSERT land in the same flush, the
    INSERT can hit the DB while the prior row is still is_active=TRUE and raise
    UniqueViolation. SQLite doesn't enforce the constraint, so we spy on
    db.flush() and assert there is a DB-visible window where the OLD active row
    has already been deactivated and the NEW active row has NOT been flushed
    yet — i.e. deactivation is its own flush, strictly before the insert."""
    org = _make_org(db)
    _make_active_model(db, org.id, macro_f1=0.40)
    fake_r, _ = _fake_redis_lock_acquired()

    flush_log: list[dict] = []
    original_flush = db.flush

    def spy_flush(*args, **kwargs):
        pending_new_model = any(isinstance(o, OrgClassifierModel) for o in db.new)
        ret = original_flush(*args, **kwargs)
        active_count = (
            db.query(OrgClassifierModel)
            .filter_by(organization_id=org.id, classifier_type="sentiment", is_active=True)
            .count()
        )
        flush_log.append({
            "pending_new_model_before_flush": pending_new_model,
            "active_count_after_flush": active_count,
        })
        return ret

    with patch.object(db, "flush", side_effect=spy_flush), \
         patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    assert len(flush_log) >= 2, (
        "expected at least 2 flush() calls: one to flush the deactivating "
        "UPDATE alone, one to flush the new active row's INSERT"
    )
    first = flush_log[0]
    assert first["pending_new_model_before_flush"] is False, (
        "the new active OrgClassifierModel row must not be pending in the "
        "session when the first flush() fires — that flush must contain only "
        "the deactivating UPDATE"
    )
    assert first["active_count_after_flush"] == 0, (
        "after the first flush, the DB must show ZERO active rows for this "
        "(org, classifier_type) — the old row was deactivated and the new "
        "one has not been inserted yet. A count of 1 here means the INSERT "
        "and UPDATE were flushed together (the bug)."
    )

    final_active_count = (
        db.query(OrgClassifierModel)
        .filter_by(organization_id=org.id, classifier_type="sentiment", is_active=True)
        .count()
    )
    assert final_active_count == 1


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
    assert args[0] == f"lock:classifier_refit:sentiment:{org.id}"
    fake_lock.acquire.assert_called_once_with(blocking=False)


def test_retrain_org_classifier_type_defaults_to_sentiment(db):
    """Characterization: calling retrain_org with NO classifier_type arg reproduces the
    pre-change sentiment-only behavior — writes classifier_type='sentiment' rows."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        tasks = _get_tasks()
        tasks.retrain_org(org.id, db)

    model = db.query(OrgClassifierModel).filter_by(organization_id=org.id).one()
    assert model.classifier_type == "sentiment"
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.classifier_type == "sentiment"


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


# ---------------------------------------------------------------------------
# Phase 7 — retrain_all_orgs orchestration + per-org isolation + folded purge
# ---------------------------------------------------------------------------


def test_retrain_all_orgs_iterates_all_orgs_and_both_types(db):
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    org3 = _make_org(db, "Org3")

    with patch("src.tasks.classifier_training.retrain_org") as mock_retrain, \
         patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.classifier_training.purge_old_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_retrain.return_value = {"decision": "retained", "retained": True, "n": 25}
        mock_purge.return_value = {"deleted": 0}

        tasks = _get_tasks()
        tasks.retrain_all_orgs()

    assert mock_retrain.call_count == 6  # 3 orgs x 2 classifier types
    called_pairs = {
        (c.args[0], c.kwargs.get("classifier_type")) for c in mock_retrain.call_args_list
    }
    assert called_pairs == {
        (org1.id, "sentiment"), (org1.id, "category"),
        (org2.id, "sentiment"), (org2.id, "category"),
        (org3.id, "sentiment"), (org3.id, "category"),
    }


def test_retrain_all_orgs_aggregates_counts_across_both_types(db):
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    org3 = _make_org(db, "Org3")

    results_by_key = {
        (org1.id, "sentiment"): {"decision": "promoted", "promoted": True, "n": 25},
        (org1.id, "category"): {"decision": "retained", "retained": True, "n": 25},
        (org2.id, "sentiment"): {"decision": "retained", "retained": True, "n": 25},
        (org2.id, "category"): {"decision": "promoted", "promoted": True, "n": 25},
        (org3.id, "sentiment"): {"decision": "skipped", "skipped": True, "reason": "below_min_labels", "n": 5},
        (org3.id, "category"): {"decision": "skipped", "skipped": True, "reason": "below_min_labels", "n": 2},
    }

    def side_effect(org_id, session, classifier_type="sentiment"):
        return results_by_key[(org_id, classifier_type)]

    with patch("src.tasks.classifier_training.retrain_org", side_effect=side_effect), \
         patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.classifier_training.purge_old_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_purge.return_value = {"deleted": 0}

        tasks = _get_tasks()
        result = tasks.retrain_all_orgs()

    # trained (promoted+retained) = 4 across both types (org1 both, org2 both); skipped = 2 (org3 both)
    assert result == {"trained": 4, "promoted": 2, "skipped": 2}


def test_retrain_all_orgs_isolates_per_org_exception_across_both_types(db):
    """org2's failure (both type-iterations) must leave the SHARED session usable for org1/org3's
    iterations. Mirrors the original single-type test's real-IntegrityError-and-rollback proof,
    doubled across the type loop."""
    org1 = _make_org(db, "Org1")
    org2 = _make_org(db, "Org2")
    org3 = _make_org(db, "Org3")

    processed = []

    def side_effect(org_id, session, classifier_type="sentiment"):
        processed.append((org_id, classifier_type))
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
            classifier_type=classifier_type,
            decision="retained",
            n=25,
        )
        session.add(good_run)
        session.commit()
        return {"decision": "retained", "retained": True, "n": 25}

    with patch("src.tasks.classifier_training.retrain_org", side_effect=side_effect), \
         patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.classifier_training.purge_old_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_purge.return_value = {"deleted": 0}

        tasks = _get_tasks()
        result = tasks.retrain_all_orgs()  # must not raise

    assert set(processed) == {
        (org1.id, "sentiment"), (org1.id, "category"),
        (org2.id, "sentiment"), (org2.id, "category"),
        (org3.id, "sentiment"), (org3.id, "category"),
    }
    assert result["trained"] == 4  # org1 x2 + org3 x2 succeeded; org2 x2 isolated-failed

    org3_runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org3.id).all()
    assert len(org3_runs) == 2
    org1_runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org1.id).all()
    assert len(org1_runs) == 2


def test_retrain_all_orgs_runs_purge_once(db):
    _make_org(db, "Org1")
    _make_org(db, "Org2")

    with patch("src.tasks.classifier_training.retrain_org") as mock_retrain, \
         patch("src.tasks.classifier_training.get_db_session") as mock_db_ctx, \
         patch("src.tasks.classifier_training.purge_old_classifier_models") as mock_purge:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_retrain.return_value = {"decision": "retained", "retained": True, "n": 25}
        mock_purge.return_value = {"deleted": 3}

        tasks = _get_tasks()
        tasks.retrain_all_orgs()

    mock_purge.assert_called_once()
