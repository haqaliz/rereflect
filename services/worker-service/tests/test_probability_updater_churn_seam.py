"""
Phase 3 (GREEN) — per-org-churn-model predict seam at probability_updater.

Pins the churn ML seam for `update()`:
  - off / no churn model  -> byte-identical calibrated path (characterization).
  - shadow                -> ML probability computed + `rereflect.classifier.shadow`
                             log emitted, NOTHING written from the ML head.
  - auto + active model   -> ML probability REPLACES churn_probability; the
                             bootstrap CI (low/high) is calibration-derived and
                             does not apply to an ML point estimate, so both are
                             NULL (consumers tolerate NULL: backend
                             customer_profile_serializer._float_or_none, frontend
                             `?? undefined`, column nullable=True) — pinned below.
                             calibration_model_id is unchanged; ML-active state is
                             visible via the active org_classifier_models row.
  - auto + no active model -> calibrated fallback preserved.
  - hysteresis guard      -> the ML value passes through _HYSTERESIS_THRESHOLD too.
  - cross-org             -> (org_id, 'churn') scoped; foreign orgs' models never
                             loaded; each org's own model is used.

Churn artifacts are seeded by hand as OrgClassifierModel(classifier_type='churn')
rows, mirroring test_probability_updater.py's hand-written model_json style and
the trainer's JSON-only churn_logreg shape (coef/intercept/features/classes).
"""

import json
import logging
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.models import (
    ChurnCalibrationModel,
    CustomerHealth,
    CustomerHealthHistory,
    OrgAIConfig,
    OrgClassifierModel,
    Organization,
)
from src.services import probability_updater

SHADOW_LOGGER = "rereflect.classifier.shadow"

# The frozen feature vector length (analysis-engine churn_classifier.features).
CHURN_FEATURE_COUNT = 28


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db, name="Org") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _set_churn_mode(db, org_id: int, mode: str) -> OrgAIConfig:
    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    if config is None:
        config = OrgAIConfig(organization_id=org_id)
        db.add(config)
    config.churn_classifier_mode = mode
    db.commit()
    db.refresh(config)
    return config


def _make_health(db, org_id: int = 1, email: str = "test@example.com",
                 churn_risk_component: int = 50,
                 probability_computed_at=None) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        churn_risk_component=churn_risk_component,
        sentiment_component=50,
        health_score=50,
        risk_level="moderate",
        segment="at_risk",
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


def _make_calibration_model(db, org_id=None, is_active=True) -> ChurnCalibrationModel:
    """Same non-identity org calibration model as test_probability_updater.py:
    maps 0 -> 0.05, 50 -> 0.40, 100 -> 0.80."""
    model_json = {
        "breakpoints": [0, 50, 100],
        "probabilities": [0.05, 0.40, 0.80],
        "threshold_bands": {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
    }
    row = ChurnCalibrationModel(
        organization_id=org_id,
        model_json=model_json,
        label_count=50,
        positive_count=10,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _churn_artifact(*, intercept: float, first_coef: float = 0.0) -> dict:
    """Hand-written churn_logreg artifact (trainer.py JSON shape).

    coef[0] is the churn_risk_component coefficient (frozen feature 0), so the
    predicted probability depends deterministically on the health row's
    component: p = sigmoid(intercept + first_coef * component).
    """
    coef = [0.0] * CHURN_FEATURE_COUNT
    coef[0] = first_coef
    return {
        "model_type": "churn_logreg",
        "version": 1,
        "features": [f"feature_{i}" for i in range(CHURN_FEATURE_COUNT)],
        "coef": coef,
        "intercept": intercept,
        "classes": [0, 1],
    }


def _make_churn_model(db, org_id, *, model_json=None, is_active=True) -> OrgClassifierModel:
    if model_json is None:
        model_json = _churn_artifact(intercept=-2.0, first_coef=0.05)
    row = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="churn",
        model_json=model_json,
        label_count=50,
        is_active=is_active,
        fit_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _shadow_records(caplog):
    return [r for r in caplog.records if r.name == SHADOW_LOGGER]


# ---------------------------------------------------------------------------
# 1. Characterization: off / no churn model -> byte-identical calibrated path
# ---------------------------------------------------------------------------


def test_characterization_off_mode_is_byte_identical_to_calibrated_path(db, caplog):
    """With churn_classifier_mode unset ('off' default) and no active churn
    model, update() output is byte-identical to the pre-seam behavior: the
    calibrated probability, non-null bootstrap CI, calibration_model_id,
    bucket and a fresh probability_computed_at. No shadow log line."""
    caplog.set_level(logging.INFO, logger=SHADOW_LOGGER)
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    calibration_model = _make_calibration_model(db, org_id=org.id)

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs(float(health.churn_probability) - 0.40) < 0.001
    assert health.churn_probability_low is not None
    assert health.churn_probability_high is not None
    assert float(health.churn_probability_low) <= float(health.churn_probability) <= float(health.churn_probability_high)
    assert health.calibration_model_id == calibration_model.id
    assert health.time_to_churn_bucket == "1-3m"
    assert health.probability_computed_at is not None
    assert _shadow_records(caplog) == []


# ---------------------------------------------------------------------------
# 2. Shadow: compute + log, write nothing
# ---------------------------------------------------------------------------


def test_shadow_mode_logs_ml_value_but_writes_nothing(db, caplog):
    """shadow + active churn model: the ML probability is computed and logged
    on rereflect.classifier.shadow with the incumbent calibrated value, but the
    persisted columns keep the calibrated path's values (byte-identical)."""
    caplog.set_level(logging.INFO, logger=SHADOW_LOGGER)
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    _make_calibration_model(db, org_id=org.id)
    churn_model = _make_churn_model(db, org.id)  # p = sigmoid(-2 + 0.05*50) = 0.6225
    _set_churn_mode(db, org.id, "shadow")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    # ML value NOT written — calibrated path unchanged.
    assert abs(float(health.churn_probability) - 0.40) < 0.001
    assert health.churn_probability_low is not None
    assert health.churn_probability_high is not None

    records = _shadow_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.org_id == org.id
    assert record.classifier_type == "churn"
    assert record.mode == "shadow"
    assert record.model_id == churn_model.id
    assert abs(record.ml_probability - 0.6225) < 0.001
    assert abs(record.incumbent_probability - 0.40) < 0.001


# ---------------------------------------------------------------------------
# 3. Auto + active model: ML probability replaces the calibrated value
# ---------------------------------------------------------------------------


def test_auto_mode_replaces_probability_with_ml_value(db, caplog):
    """auto + active churn model: churn_probability comes from the ML head,
    the bootstrap CI (calibration-derived) is NULL for the ML point estimate,
    bucket derives from the ML value, computed_at stays fresh and
    calibration_model_id is unchanged (ML-active state is visible via the
    active org_classifier_models row)."""
    caplog.set_level(logging.INFO, logger=SHADOW_LOGGER)
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    calibration_model = _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, org.id)  # p = sigmoid(-2 + 0.05*50) = 0.6225
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs(float(health.churn_probability) - 0.6225) < 0.001
    # Honest CI: the bootstrap bounds are calibration-derived and do not apply
    # to an ML point estimate -> NULL, never a fabricated interval.
    assert health.churn_probability_low is None
    assert health.churn_probability_high is None
    assert health.time_to_churn_bucket == "2-4w"  # derived from ML value 0.6225
    assert health.calibration_model_id == calibration_model.id
    assert health.probability_computed_at is not None

    assert len(_shadow_records(caplog)) == 1


def test_auto_mode_feature_vector_comes_from_health_row(db):
    """The ML feature vector is built from the health row update() already
    loads: a different churn_risk_component must change the ML probability
    (coef[0] = 0.05 => p = sigmoid(-2 + 0.05 * component))."""
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=80)
    _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, org.id)
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    # sigmoid(-2 + 0.05*80) = sigmoid(2) = 0.8808 (vs 0.6225 at component 50).
    assert abs(float(health.churn_probability) - 0.8808) < 0.001
    assert health.time_to_churn_bucket == "immediate"


def test_auto_mode_automation_trigger_receives_ml_value(db):
    """Automations (churn_probability_threshold) consume churn_probability for
    free: the trigger evaluator must receive the ML value, not the calibrated."""
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, org.id)
    _set_churn_mode(db, org.id, "auto")

    with patch(
        "src.services.automation_churn_trigger.evaluate_churn_probability_triggers"
    ) as mock_evaluate:
        probability_updater.update(org.id, "test@example.com", db)

    mock_evaluate.assert_called_once()
    args = mock_evaluate.call_args
    assert abs(args[0][2] - 0.6225) < 0.001


# ---------------------------------------------------------------------------
# 4. Auto + no active model -> calibrated fallback preserved
# ---------------------------------------------------------------------------


def test_auto_mode_without_active_churn_model_falls_back_to_calibrated(db, caplog):
    """auto mode with no org (or global) churn model: the existing calibrated
    path is preserved byte-identically and no shadow line is logged (there is
    no challenger prediction to disclose)."""
    caplog.set_level(logging.INFO, logger=SHADOW_LOGGER)
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    calibration_model = _make_calibration_model(db, org_id=org.id)
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs(float(health.churn_probability) - 0.40) < 0.001
    assert health.churn_probability_low is not None
    assert health.churn_probability_high is not None
    assert health.calibration_model_id == calibration_model.id
    assert _shadow_records(caplog) == []


# ---------------------------------------------------------------------------
# 5. Hysteresis guard applies to the ML path too
# ---------------------------------------------------------------------------


def test_auto_mode_hysteresis_guard_still_skips_sub_threshold_delta(db, caplog):
    """auto + active churn model: a sub-threshold churn_risk_component delta
    skips the recompute entirely — probability_computed_at does not move and
    the ML head never runs (no shadow log)."""
    caplog.set_level(logging.INFO, logger=SHADOW_LOGGER)
    org = _make_org(db)
    old_ts = datetime(2026, 1, 1, 12, 0, 0)
    _make_health(db, org_id=org.id, churn_risk_component=51, probability_computed_at=old_ts)
    _make_history(db, 1, org_id=org.id, churn_risk_component=50)
    _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, org.id)
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs((health.probability_computed_at - old_ts).total_seconds()) < 1
    assert _shadow_records(caplog) == []


def test_auto_mode_hysteresis_threshold_met_runs_ml_head(db):
    """auto + active churn model with a >= 2-point delta: recompute runs and
    the ML value is written."""
    org = _make_org(db)
    old_ts = datetime(2026, 1, 1, 12, 0, 0)
    _make_health(db, org_id=org.id, churn_risk_component=53, probability_computed_at=old_ts)
    _make_history(db, 1, org_id=org.id, churn_risk_component=50)
    _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, org.id)
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    # sigmoid(-2 + 0.05*53) = sigmoid(0.65) = 0.6570
    assert abs(float(health.churn_probability) - 0.6570) < 0.001
    assert health.probability_computed_at > old_ts


# ---------------------------------------------------------------------------
# 6. Cross-org scoping
# ---------------------------------------------------------------------------


def test_cross_org_foreign_model_never_loaded(db):
    """Org B has no churn model of its own: org A's active churn model must
    never leak into org B's update (calibrated path for B)."""
    org_a = _make_org(db, name="Org A")
    org_b = _make_org(db, name="Org B")
    _make_health(db, org_id=org_a.id, churn_risk_component=50)
    _make_health(db, org_id=org_b.id, churn_risk_component=50, email="b@example.com")
    _make_calibration_model(db, org_id=org_a.id)
    _make_calibration_model(db, org_id=org_b.id)
    _make_churn_model(db, org_a.id)
    _set_churn_mode(db, org_a.id, "auto")
    _set_churn_mode(db, org_b.id, "auto")

    probability_updater.update(org_b.id, "b@example.com", db)

    health_b = db.query(CustomerHealth).filter_by(
        organization_id=org_b.id, customer_email="b@example.com"
    ).first()
    assert abs(float(health_b.churn_probability) - 0.40) < 0.001


def test_cross_org_each_org_uses_its_own_active_model(db):
    """Two orgs, two churn models: each org's update uses its own artifact."""
    org_a = _make_org(db, name="Org A")
    org_b = _make_org(db, name="Org B")
    _make_health(db, org_id=org_a.id, churn_risk_component=50)
    _make_health(db, org_id=org_b.id, churn_risk_component=50, email="b@example.com")
    _make_calibration_model(db, org_id=org_a.id)
    _make_calibration_model(db, org_id=org_b.id)
    _make_churn_model(db, org_a.id, model_json=_churn_artifact(intercept=-2.0, first_coef=0.05))
    _make_churn_model(db, org_b.id, model_json=_churn_artifact(intercept=-2.0, first_coef=0.10))
    _set_churn_mode(db, org_a.id, "auto")
    _set_churn_mode(db, org_b.id, "auto")

    probability_updater.update(org_a.id, "test@example.com", db)
    probability_updater.update(org_b.id, "b@example.com", db)

    health_a = db.query(CustomerHealth).filter_by(
        organization_id=org_a.id, customer_email="test@example.com"
    ).first()
    health_b = db.query(CustomerHealth).filter_by(
        organization_id=org_b.id, customer_email="b@example.com"
    ).first()
    # sigmoid(-2 + 0.05*50) = 0.6225 vs sigmoid(-2 + 0.10*50) = 0.9526
    assert abs(float(health_a.churn_probability) - 0.6225) < 0.001
    assert abs(float(health_b.churn_probability) - 0.9526) < 0.001


def test_global_churn_model_used_when_org_has_none(db):
    """The shared loader's 3-tier fallback holds for 'churn': a global (org_id
    NULL) active churn model serves orgs without their own."""
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, None)  # global active churn model
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs(float(health.churn_probability) - 0.6225) < 0.001


# ---------------------------------------------------------------------------
# Edge cases: corrupt / shape-violating artifacts -> calibrated fallback
# ---------------------------------------------------------------------------


def test_auto_mode_corrupt_churn_artifact_falls_back_to_calibrated(db, caplog):
    """A structurally corrupt churn artifact degrades to the calibrated path
    (loader _deserialize defense), never raises, and logs no shadow line."""
    caplog.set_level(logging.INFO, logger=SHADOW_LOGGER)
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    calibration_model = _make_calibration_model(db, org_id=org.id)
    _make_churn_model(db, org.id, model_json={"corrupted": True})
    _set_churn_mode(db, org.id, "auto")

    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs(float(health.churn_probability) - 0.40) < 0.001
    assert health.calibration_model_id == calibration_model.id
    assert _shadow_records(caplog) == []


def test_auto_mode_feature_count_mismatch_falls_back_to_calibrated(db):
    """A coef row whose length disagrees with the frozen 28-feature vector is a
    contract violation: the core's predict raises, the seam catches and falls
    back to the calibrated path (never breaks the probability update)."""
    org = _make_org(db)
    _make_health(db, org_id=org.id, churn_risk_component=50)
    _make_calibration_model(db, org_id=org.id)
    bad_artifact = _churn_artifact(intercept=-2.0, first_coef=0.05)
    bad_artifact["coef"] = [0.5, -0.5, 0.25]  # length 3 != 28
    _make_churn_model(db, org.id, model_json=bad_artifact)
    _set_churn_mode(db, org.id, "auto")

    # Must not raise.
    probability_updater.update(org.id, "test@example.com", db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=org.id, customer_email="test@example.com"
    ).first()
    assert abs(float(health.churn_probability) - 0.40) < 0.001
