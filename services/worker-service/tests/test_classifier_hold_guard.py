"""
Tests for the auto-promotion hold guard — worker-hold-guard aspect
(classifier-model-versioning-rollback, M2/M3a).

retrain_org must re-read the org's OrgAIConfig `*_autopromote_hold` column for the
current classifier_type, row-locked (.with_for_update()), immediately before the
_promote() call. When held: never call _promote (active model id unchanged, zero new
model rows), and the eval run must persist decision="held" (not "promoted") while
still carrying the real macro_f1_delta/n. When not held: unchanged promote behavior
(G5, no regression).

Reuses tests/test_classifier_training_tasks.py's scaffolding (_make_org,
_fake_redis_lock_acquired, _patch_core) rather than re-deriving it.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, Organization, OrgAIConfig, OrgClassifierEvalRun, OrgClassifierModel

from tests.test_classifier_training_tasks import _fake_redis_lock_acquired, _make_org, _patch_core

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


_HOLD_COLUMN_BY_TYPE = {
    "sentiment": "sentiment_autopromote_hold",
    "category": "category_autopromote_hold",
    "urgency": "urgency_autopromote_hold",
}


def _make_config(db, org_id: int, **hold_flags) -> OrgAIConfig:
    config = OrgAIConfig(
        organization_id=org_id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        **hold_flags,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


# ---------------------------------------------------------------------------
# G1 — hold set + would-promote challenger -> held, active model id unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("classifier_type", ["sentiment", "category", "urgency"])
def test_hold_set_prevents_promotion_writes_held_eval_run(db, classifier_type):
    org = _make_org(db)
    hold_column = _HOLD_COLUMN_BY_TYPE[classifier_type]
    _make_config(db, org.id, **{hold_column: True})
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", classifier_type=classifier_type, n=25,
                      incumbent_macro_f1=0.50, challenger_macro_f1=0.65, macro_f1_delta=0.15):
        from src.tasks import classifier_training as tasks
        result = tasks.retrain_org(org.id, db, classifier_type=classifier_type)

    # No model row was ever created — nothing to promote to, active model id unchanged.
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 0

    runs = db.query(OrgClassifierEvalRun).filter_by(
        organization_id=org.id, classifier_type=classifier_type
    ).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.decision == "held"
    assert run.classifier_model_id is None
    # Real eval numbers still persisted (nudge data, not suppressed).
    assert float(run.macro_f1_delta) == pytest.approx(0.15, abs=1e-4)
    assert run.n == 25

    assert result["decision"] == "held"


def test_hold_set_leaves_existing_active_model_unchanged(db):
    """A prior active model stays active and untouched when a would-promote challenger
    is held — proves _promote() is genuinely never called, not just that the return
    value is overridden."""
    org = _make_org(db)
    _make_config(db, org.id, sentiment_autopromote_hold=True)

    prior = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="sentiment",
        model_json={"model_type": "tfidf_logreg", "classes": ["negative", "neutral", "positive"]},
        label_count=30,
        macro_f1=0.40,
        is_active=True,
    )
    db.add(prior)
    db.commit()
    db.refresh(prior)

    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        from src.tasks import classifier_training as tasks
        tasks.retrain_org(org.id, db, classifier_type="sentiment")

    db.refresh(prior)
    assert prior.is_active is True

    active_models = (
        db.query(OrgClassifierModel)
        .filter_by(organization_id=org.id, classifier_type="sentiment", is_active=True)
        .all()
    )
    assert len(active_models) == 1
    assert active_models[0].id == prior.id


# ---------------------------------------------------------------------------
# G5 — no regression: hold unset -> promotes exactly as today
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("classifier_type", ["sentiment", "category", "urgency"])
def test_hold_unset_promotes_as_today(db, classifier_type):
    org = _make_org(db)
    hold_column = _HOLD_COLUMN_BY_TYPE[classifier_type]
    _make_config(db, org.id, **{hold_column: False})
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", classifier_type=classifier_type, n=25, challenger_macro_f1=0.65):
        from src.tasks import classifier_training as tasks
        result = tasks.retrain_org(org.id, db, classifier_type=classifier_type)

    models = db.query(OrgClassifierModel).filter_by(
        organization_id=org.id, classifier_type=classifier_type
    ).all()
    assert len(models) == 1
    assert models[0].is_active is True

    run = db.query(OrgClassifierEvalRun).filter_by(
        organization_id=org.id, classifier_type=classifier_type
    ).one()
    assert run.decision == "promoted"
    assert run.classifier_model_id == models[0].id

    assert result["decision"] == "promoted"


def test_no_config_row_treated_as_not_held(db):
    """No OrgAIConfig row for the org at all -> not held (default False), promotes
    exactly as today."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", n=25, challenger_macro_f1=0.65):
        from src.tasks import classifier_training as tasks
        result = tasks.retrain_org(org.id, db, classifier_type="sentiment")

    assert result["decision"] == "promoted"
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 1


def test_only_matching_hold_column_gates_its_own_classifier_type(db):
    """sentiment_autopromote_hold=True must not gate a category retrain, and vice
    versa — each classifier_type maps to its own column."""
    org = _make_org(db)
    _make_config(db, org.id, sentiment_autopromote_hold=True)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("promoted", classifier_type="category", n=25, challenger_macro_f1=0.70):
        from src.tasks import classifier_training as tasks
        result = tasks.retrain_org(org.id, db, classifier_type="category")

    assert result["decision"] == "promoted"
    assert db.query(OrgClassifierModel).filter_by(
        organization_id=org.id, classifier_type="category"
    ).count() == 1


def test_hold_set_but_challenger_retained_still_writes_held(db):
    """Held path still overrides the eval-run decision to 'held' even when the
    underlying evaluate() decision was 'retained' (not just the would-promote case)."""
    org = _make_org(db)
    _make_config(db, org.id, sentiment_autopromote_hold=True)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.classifier_training._get_redis", return_value=fake_r), \
         _patch_core("retained", n=25, incumbent_macro_f1=0.65, challenger_macro_f1=0.60,
                      macro_f1_delta=-0.05):
        from src.tasks import classifier_training as tasks
        tasks.retrain_org(org.id, db, classifier_type="sentiment")

    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "held"
    assert float(run.macro_f1_delta) == pytest.approx(-0.05, abs=1e-4)
    assert db.query(OrgClassifierModel).count() == 0
