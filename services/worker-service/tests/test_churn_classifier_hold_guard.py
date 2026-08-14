"""
Tests for the churn auto-promotion hold guard — worker-churn-trainer-and-schedule
aspect (M5.3 per-org-churn-model), mirroring tests/test_classifier_hold_guard.py.

retrain_org must re-read the org's OrgAIConfig `churn_autopromote_hold` column,
row-locked (.with_for_update()), immediately before the promote-or-not decision,
in the SAME transaction that writes the eval run. When held:

- the would-promote candidate run becomes decision='held' (no promoted_candidate);
- a promotion behind an existing candidate is blocked (hold clears both runs'
  state);
- the eval run still carries the REAL macro_f1_delta/n (disclosure, not
  suppression);
- below-gate skips still write decision='skipped' (no delta to disclose).

The column read is getattr-defensive so the module cannot crash against a DB
that hasn't run the aspect's migration yet (M5.2 convention).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, OrgAIConfig, OrgClassifierEvalRun, OrgClassifierModel

from tests.test_churn_classifier_training_tasks import (
    _fake_redis_lock_acquired,
    _make_org,
    _patch_churn_core,
)

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


def _make_config(db, org_id: int, *, hold: bool = False,
                 mode: str | None = "auto") -> OrgAIConfig:
    config = OrgAIConfig(
        organization_id=org_id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        churn_autopromote_hold=hold,
        churn_classifier_mode=mode,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


# ---------------------------------------------------------------------------
# G1 — held + would-promote -> held, no candidate, no model rows
# ---------------------------------------------------------------------------


def test_hold_set_would_promote_writes_held_not_candidate(db):
    org = _make_org(db)
    _make_config(db, org.id, hold=True)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, incumbent_macro_f1=0.50,
                           challenger_macro_f1=0.65, macro_f1_delta=0.15):
        from src.tasks import churn_classifier_training as tasks
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "held"
    assert result["held"] is True
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 0

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.decision == "held"
    assert run.classifier_model_id is None
    # Real eval numbers still persisted (nudge data, not suppressed).
    assert float(run.macro_f1_delta) == pytest.approx(0.15, abs=1e-4)
    assert run.n == 25


def test_hold_set_blocks_promotion_after_candidate(db):
    """Hold flips on between run 1 (candidate) and run 2 (would-promote): the
    second run is 'held' and the streak is frozen — never a promotion."""
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        from src.tasks import churn_classifier_training as tasks
        first = tasks.retrain_org(org.id, db)

    assert first["decision"] == "promoted_candidate"

    _make_config(db, org.id, hold=True)

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
        from src.tasks import churn_classifier_training as tasks
        second = tasks.retrain_org(org.id, db)

    assert second["decision"] == "held"
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 0

    runs = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id) \
        .order_by(OrgClassifierEvalRun.id.asc()).all()
    assert [r.decision for r in runs] == ["promoted_candidate", "held"]


# ---------------------------------------------------------------------------
# G2 — held + retained -> held with the real delta
# ---------------------------------------------------------------------------


def test_hold_set_but_challenger_retained_still_writes_held(db):
    org = _make_org(db)
    _make_config(db, org.id, hold=True)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         _patch_churn_core("retained", n=25, incumbent_macro_f1=0.65,
                           challenger_macro_f1=0.60, macro_f1_delta=-0.05):
        from src.tasks import churn_classifier_training as tasks
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "held"
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "held"
    assert float(run.macro_f1_delta) == pytest.approx(-0.05, abs=1e-4)
    assert db.query(OrgClassifierModel).count() == 0


# ---------------------------------------------------------------------------
# G3 — below-gate skip wins over the hold (no delta to disclose)
# ---------------------------------------------------------------------------


def test_below_gate_skipped_beats_hold(db):
    org = _make_org(db)
    _make_config(db, org.id, hold=True)
    fake_r, _ = _fake_redis_lock_acquired()

    with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
         patch("analyzer.churn_classifier.dataset.fetch_churn_rows",
               return_value=[{"customer_email": f"c{i}@x.com",
                              "churned_at": datetime.utcnow(),
                              "churn_risk_component": 60} for i in range(5)]):
        from src.tasks import churn_classifier_training as tasks
        result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "skipped"
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id).one()
    assert run.decision == "skipped"
    assert run.macro_f1_delta is None
    assert db.query(OrgClassifierModel).count() == 0


# ---------------------------------------------------------------------------
# G5 — no regression: hold unset / absent config -> candidate-then-promote
# ---------------------------------------------------------------------------


def test_hold_unset_promotes_after_candidate(db):
    org = _make_org(db)
    _make_config(db, org.id, hold=False)
    fake_r, _ = _fake_redis_lock_acquired()

    for _ in range(2):
        with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
             _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
            from src.tasks import churn_classifier_training as tasks
            result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "promoted"
    models = db.query(OrgClassifierModel).filter_by(organization_id=org.id).all()
    assert len(models) == 1
    assert models[0].is_active is True
    run = db.query(OrgClassifierEvalRun).filter_by(organization_id=org.id) \
        .order_by(OrgClassifierEvalRun.id.asc()).all()[-1]
    assert run.decision == "promoted"
    assert run.classifier_model_id == models[0].id


def test_no_config_row_treated_as_not_held(db):
    org = _make_org(db)
    fake_r, _ = _fake_redis_lock_acquired()

    for _ in range(2):
        with patch("src.tasks.churn_classifier_training._get_redis", return_value=fake_r), \
             _patch_churn_core("promoted", n=25, challenger_macro_f1=0.65):
            from src.tasks import churn_classifier_training as tasks
            result = tasks.retrain_org(org.id, db)

    assert result["decision"] == "promoted"
    assert db.query(OrgClassifierModel).filter_by(organization_id=org.id).count() == 1


# ---------------------------------------------------------------------------
# G6 — getattr-defensive column reads (no crash pre-migration)
# ---------------------------------------------------------------------------


def test_config_helpers_are_getattr_defensive():
    """The hold/mode reads must never raise on an object lacking the columns —
    the module must survive a DB that hasn't run the aspect's migration."""
    from src.tasks import churn_classifier_training as tasks

    bare = object()
    assert tasks._config_held(bare) is False
    assert tasks._config_mode(bare) == "off"


def test_hold_and_mode_read_from_real_config_row(db):
    org = _make_org(db)
    _make_config(db, org.id, hold=True, mode="auto")

    from src.tasks import churn_classifier_training as tasks

    config = db.query(OrgAIConfig).filter_by(organization_id=org.id).one()
    assert tasks._config_held(config) is True
    assert tasks._config_mode(config) == "auto"
