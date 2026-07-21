"""
AC 10 — the single most important test in the trend-detection-and-health
aspect: the executable form of the calibration boundary.

`churn_probability` = `_predict_with_interval(health.churn_risk_component,
model)` (worker-service/src/services/probability_updater.py:75).
`churn_risk_component` is FEEDBACK-ONLY (`_compute_churn_component`, this
module, below) and the org's isotonic calibration model was fitted against
that feedback-only distribution. Usage must NEVER reach
`churn_risk_component` / `churn_probability` / `churn_probability_low/high` /
`calibration_model_id` / `time_to_churn_bucket`, or every org's calibration
is silently invalidated with no error surfaced.

Why this test lives here (not in worker-service, against the daily Celery
task): `probability_updater.update()` — the only code that ever WRITES
churn_probability/_low/_high/calibration_model_id/time_to_churn_bucket — is
invoked exclusively from the FEEDBACK-analysis path
(worker-service/src/tasks/analysis.py:474), never from
`recompute_usage_scores`. `update_customer_health()` (this module) itself
never touches those five fields. This test proves that invariant directly
and rigorously against the REAL, unmocked `update_customer_health()` +
`_compute_usage_component()` + `apply_trend_penalty()` — not a stand-in —
by simulating "a previous probability_updater run already wrote these
fields" (a direct DB seed, the only way to populate them without pulling in
the worker's isotonic/sklearn dependency chain), then driving a
stable -> sharp_decline usage-trend transition through TWO real
`update_customer_health()` calls with NO new feedback in between.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.customer_usage import CustomerUsage
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.services.health_score_service import update_customer_health
from src.services.usage_score_service import compute_usage_score


EMAIL = "boundary_customer@example.com"
NOW = datetime(2026, 6, 1, 12, 0, 0)


def _seed_feedback(db: Session, org_id: int, email: str) -> None:
    """Fixed, known feedback — churn_risk_component is deterministic from
    this and must not move across the two update_customer_health() calls
    below, since no feedback changes between them."""
    rows = [(0.4, 35), (-0.1, 55), (0.2, 40)]
    for sentiment, churn in rows:
        db.add(FeedbackItem(
            organization_id=org_id,
            customer_email=email,
            text="boundary test feedback",
            source="email",
            sentiment_score=sentiment,
            sentiment_label="neutral",
            churn_risk_score=churn,
            is_urgent=False,
            created_at=NOW - timedelta(days=1),
        ))
    db.commit()


@pytest.fixture
def seeded_health(db: Session, test_organization: Organization) -> CustomerHealth:
    """
    Seed feedback, a CustomerUsage rollup at usage_trend_state='stable', run
    update_customer_health() once (real call) to create the CustomerHealth
    row, then directly seed churn_probability/_low/_high/
    calibration_model_id/time_to_churn_bucket onto it — simulating a prior,
    unrelated probability_updater.update() run. This is the ONLY way to
    populate those fields without importing the worker's isotonic-regression
    dependency chain into a backend-api test.
    """
    _seed_feedback(db, test_organization.id, EMAIL)

    rollup = CustomerUsage(
        organization_id=test_organization.id,
        customer_email=EMAIL,
        last_active_at=NOW - timedelta(days=1),
        active_days_7d=6, active_days_14d=12, active_days_30d=25,
        login_count_7d=9, login_count_30d=40,
        distinct_feature_count=5,
        usage_trend_state="stable",
        usage_trend_pct=0.0,
    )
    rollup.usage_score = compute_usage_score(rollup, now=NOW)
    db.add(rollup)
    db.commit()

    update_customer_health(test_organization.id, EMAIL, db)

    health = db.query(CustomerHealth).filter_by(
        organization_id=test_organization.id, customer_email=EMAIL,
    ).first()

    # Simulate a prior probability_updater.update() run.
    health.churn_probability = 0.4231
    health.churn_probability_low = 0.3012
    health.churn_probability_high = 0.5678
    health.calibration_model_id = None  # identity-model fallback is valid too
    health.time_to_churn_bucket = "2-4w"
    health.probability_computed_at = NOW
    db.commit()
    db.refresh(health)
    return health


class TestNoChurnStackMovementOnTrendTransition:
    """AC 10: stable -> sharp_decline usage-trend transition, NO new
    feedback, must leave the five churn-stack fields byte-unchanged."""

    def test_churn_fields_unchanged_after_trend_transition(
        self, db: Session, test_organization: Organization, seeded_health: CustomerHealth,
    ):
        before = {
            "churn_risk_component": seeded_health.churn_risk_component,
            "churn_probability": seeded_health.churn_probability,
            "churn_probability_low": seeded_health.churn_probability_low,
            "churn_probability_high": seeded_health.churn_probability_high,
            "calibration_model_id": seeded_health.calibration_model_id,
            "time_to_churn_bucket": seeded_health.time_to_churn_bucket,
        }

        # The transition: usage_trend_state moves stable -> sharp_decline,
        # with NO new FeedbackItem row created anywhere in this test.
        rollup = db.query(CustomerUsage).filter_by(
            organization_id=test_organization.id, customer_email=EMAIL,
        ).first()
        rollup.usage_trend_state = "sharp_decline"
        rollup.usage_trend_pct = -70.0
        db.commit()

        # Real, unmocked call — the same function the worker's trend-aware
        # health-refresh trigger invokes (AC 12). update_customer_health()
        # does not commit itself (its callers do — see usage_metrics.py's
        # recompute_usage_scores); commit here to match real usage, since
        # Session.refresh() below does NOT flush an object's own pending
        # changes first — without this commit the refresh would silently
        # discard the update and this test would pass for the wrong reason.
        update_customer_health(test_organization.id, EMAIL, db)
        db.commit()

        db.expire(seeded_health)
        db.refresh(seeded_health)

        after = {
            "churn_risk_component": seeded_health.churn_risk_component,
            "churn_probability": float(seeded_health.churn_probability),
            "churn_probability_low": float(seeded_health.churn_probability_low),
            "churn_probability_high": float(seeded_health.churn_probability_high),
            "calibration_model_id": seeded_health.calibration_model_id,
            "time_to_churn_bucket": seeded_health.time_to_churn_bucket,
        }
        before["churn_probability"] = float(before["churn_probability"])
        before["churn_probability_low"] = float(before["churn_probability_low"])
        before["churn_probability_high"] = float(before["churn_probability_high"])

        assert after == before, (
            f"Usage-trend transition must never move the churn stack. "
            f"before={before} after={after}"
        )

        # Sanity check (not vacuous): the usage_component DID move — proving
        # the trend penalty is genuinely wired in, so the churn-stack
        # equality above isn't trivially passing because nothing happened.
        from src.services.usage_score_service import TREND_PENALTY_SHARP_DECLINE
        assert seeded_health.usage_component == 100 - TREND_PENALTY_SHARP_DECLINE

    def test_usage_component_and_health_score_do_move_while_churn_stays_still(
        self, db: Session, test_organization: Organization, seeded_health: CustomerHealth,
    ):
        """Companion sanity test: proves the boundary test above is
        meaningful by confirming the trend DOES change something (usage
        component / health_score) even as the churn stack stays put."""
        usage_component_before = seeded_health.usage_component
        health_score_before = seeded_health.health_score

        rollup = db.query(CustomerUsage).filter_by(
            organization_id=test_organization.id, customer_email=EMAIL,
        ).first()
        rollup.usage_trend_state = "sharp_decline"
        rollup.usage_trend_pct = -70.0
        db.commit()

        # Raise the usage weight so the trend penalty is visible in
        # health_score too (weight 0 is the AC 9 byte-stability case,
        # covered elsewhere — this test wants the opposite: a real, visible
        # movement to prove the sanity check has teeth).
        from src.models.org_ai_config import OrgAIConfig
        config = db.query(OrgAIConfig).filter_by(
            organization_id=test_organization.id,
        ).first()
        if config is None:
            config = OrgAIConfig(organization_id=test_organization.id)
            db.add(config)
        config.health_weight_churn = 30
        config.health_weight_sentiment = 20
        config.health_weight_resolution = 20
        config.health_weight_frequency = 10
        config.health_weight_usage = 20
        config.health_weight_crm = 0
        db.commit()

        # Same commit-before-refresh note as the boundary test above.
        update_customer_health(test_organization.id, EMAIL, db)
        db.commit()

        db.expire(seeded_health)
        db.refresh(seeded_health)

        assert seeded_health.usage_component < usage_component_before
        assert seeded_health.health_score != health_score_before
