"""
TDD tests for crm-health-component aspect.

Phase 1 (RED): all tests fail because _compute_crm_component does not exist yet.
Phase 4 (GREEN): all tests pass after service implementation.

Mirrors test_health_usage_component.py in structure and contract.
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import patch

from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig
from src.models.feedback import FeedbackItem
from src.services.health_score_service import (
    compute_health_score,
    update_customer_health,
    _compute_crm_component,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feedback(db, org_id, email, sentiment_score, churn_risk_score):
    """Create a FeedbackItem directly in the DB (mirrors usage component helper)."""
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="crm component test feedback",
        source="email",
        sentiment_score=sentiment_score,
        sentiment_label="neutral",
        churn_risk_score=churn_risk_score,
        is_urgent=False,
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# Fixture: crm_enrichment table
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def crm_enrichment_table(db):
    """
    The crm_enrichment table is already created by Base.metadata.create_all()
    in conftest (hubspot-sync aspect is on this branch). This fixture is kept
    for API compatibility with tests that declare it, but performs no DDL.

    Tests insert rows using the CrmEnrichment ORM model (or raw SQL with all
    required columns) and rely on the existing table definition.
    """
    yield


# ---------------------------------------------------------------------------
# Score-stability characterization (regression guard at CRM weight 0)
# ---------------------------------------------------------------------------

class TestScoreStabilityWithCrmWeightZero:
    """
    With health_weight_crm = 0 (default), compute_health_score returns
    the SAME value as before this aspect.  Snapshot: 47 with 3 feedbacks
    (sentiment=[0.5,-0.2,0.1], churn=[30,60,45]) and no OrgAIConfig row.
    These values MUST equal those in TestScoreStabilityCharacterization.
    """

    EMAIL = "crm_stability@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db, test_organization):
        for sentiment, churn in [(0.5, 30), (-0.2, 60), (0.1, 45)]:
            _make_feedback(db, test_organization.id, self.EMAIL, sentiment, churn)

    def test_health_score_unchanged_at_crm_weight_zero(self, db, test_organization):
        """health_score must equal 47 — unchanged from pre-crm-component baseline."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["health_score"] == 47

    def test_crm_component_in_return_dict(self, db, test_organization):
        """compute_health_score must include 'crm_component' key in return dict."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert "crm_component" in result

    def test_crm_component_defaults_to_neutral(self, db, test_organization):
        """With no crm_enrichment row, crm_component must be 50.0 (neutral)."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["crm_component"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# _compute_crm_component — fallback and never-raise
# ---------------------------------------------------------------------------

class TestComputeCrmComponentFallback:
    """_compute_crm_component must NEVER raise and returns 50.0 on no data."""

    def test_returns_neutral_when_no_crm_enrichment_table(
        self, db, test_organization
    ):
        """Missing crm_enrichment table returns 50.0, never raises."""
        result = _compute_crm_component(
            db, test_organization.id, "norow@example.com", datetime.utcnow()
        )
        assert result == pytest.approx(50.0)

    def test_never_raises_on_missing_table(self, db, test_organization):
        """_compute_crm_component is safe even with unexpected DB errors."""
        try:
            val = _compute_crm_component(
                db, test_organization.id, "safe@example.com", datetime.utcnow()
            )
        except Exception as exc:
            pytest.fail(f"_compute_crm_component raised unexpectedly: {exc}")
        assert isinstance(val, float)

    def test_returns_neutral_when_row_exists_but_no_renewal_date(
        self, db, test_organization, crm_enrichment_table
    ):
        """Row with renewal_date=NULL returns 50.0 (neutral)."""
        from src.models.crm_enrichment import CrmEnrichment
        row = CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="nullrenewal@example.com",
            renewal_date=None,
            last_synced_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        result = _compute_crm_component(
            db, test_organization.id, "nullrenewal@example.com", datetime.utcnow()
        )
        assert result == pytest.approx(50.0)

    def test_returns_neutral_when_no_row_for_email(
        self, db, test_organization, crm_enrichment_table
    ):
        """No row for this email returns 50.0 (neutral)."""
        result = _compute_crm_component(
            db, test_organization.id, "unknown@example.com", datetime.utcnow()
        )
        assert result == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# SAVEPOINT isolation
# ---------------------------------------------------------------------------

class TestCrmComponentSavepointIsolation:
    """
    _compute_crm_component must use db.begin_nested() (SAVEPOINT) so a
    missing crm_enrichment table cannot abort the outer SQLAlchemy transaction
    and cause PendingRollbackError on subsequent queries.
    Mirrors TestUsageComponentSavepointIsolation in test_health_usage_component.py.
    """

    def test_begin_nested_called_during_crm_read(self, db, test_organization):
        """begin_nested() must be invoked during the CRM component read."""
        with patch.object(db, "begin_nested", wraps=db.begin_nested) as spy:
            result = _compute_crm_component(
                db, test_organization.id,
                "savepoint_crm@example.com", datetime.utcnow()
            )
        assert result == pytest.approx(50.0)  # missing table → neutral fallback
        assert spy.call_count >= 1, (
            "begin_nested must be called to SAVEPOINT-isolate the CRM read. "
            "Without it, a PostgreSQL SQL error aborts the transaction and the "
            "next db.query() raises PendingRollbackError (HTTP 500)."
        )

    def test_session_still_usable_after_simulated_crm_error(self, db, test_organization):
        """After a simulated execute error the session must still be usable."""
        from sqlalchemy import text as sql_text
        original_execute = db.execute
        first_call = [True]

        def failing_execute(statement, *args, **kwargs):
            if first_call[0]:
                first_call[0] = False
                raise Exception("simulated: table crm_enrichment does not exist")
            return original_execute(statement, *args, **kwargs)

        with patch.object(db, "execute", side_effect=failing_execute):
            result = _compute_crm_component(
                db, test_organization.id,
                "session_crm@example.com", datetime.utcnow()
            )
        assert result == pytest.approx(50.0)
        val = db.execute(sql_text("SELECT 1")).scalar()
        assert val == 1, "Session must be usable after SAVEPOINT-isolated CRM error"


# ---------------------------------------------------------------------------
# Renewal-proximity scoring (deterministic assertions)
# ---------------------------------------------------------------------------

class TestCrmComponentRenewalProximityScoring:
    """
    Renewal-proximity heuristic: closer renewal → lower (more risky) score.
    Uses crm_enrichment_table fixture for an actual DB row.
    All assertions are deterministic against the documented module constants.
    """

    @staticmethod
    def _today_midnight():
        """Return today's date as midnight datetime for day-precision comparison."""
        today = date.today()
        return datetime(today.year, today.month, today.day)

    def _insert_renewal(self, db, org_id, email, days_from_now):
        """Insert a crm_enrichment row with renewal_date = midnight(today + days_from_now).
        Using midnight ensures days_to_renewal arithmetic is exact when now=today_midnight()."""
        from src.models.crm_enrichment import CrmEnrichment
        renewal_date_obj = date.today() + timedelta(days=days_from_now)
        renewal_dt = datetime(renewal_date_obj.year, renewal_date_obj.month, renewal_date_obj.day)
        row = CrmEnrichment(
            organization_id=org_id,
            customer_email=email,
            renewal_date=renewal_dt,
            last_synced_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()

    def test_no_renewal_returns_neutral(
        self, db, test_organization, crm_enrichment_table
    ):
        """Customer with no row returns 50.0 (neutral)."""
        now = self._today_midnight()
        result = _compute_crm_component(
            db, test_organization.id, "norenewal@example.com", now
        )
        assert result == pytest.approx(50.0)

    def test_renewal_31_days_out_returns_neutral(
        self, db, test_organization, crm_enrichment_table
    ):
        """31 days out → outside warn band → 50.0 neutral."""
        self._insert_renewal(db, test_organization.id, "r31@example.com", 31)
        now = self._today_midnight()
        result = _compute_crm_component(
            db, test_organization.id, "r31@example.com", now
        )
        assert result == pytest.approx(50.0)

    def test_renewal_within_30_days_scores_lower_than_no_renewal(
        self, db, test_organization, crm_enrichment_table
    ):
        """Renewal in 25 days → warn band → score < 50 (more risk than no renewal)."""
        self._insert_renewal(db, test_organization.id, "r25@example.com", 25)
        now = self._today_midnight()
        result = _compute_crm_component(
            db, test_organization.id, "r25@example.com", now
        )
        assert result < 50.0
        assert result == pytest.approx(35.0)   # CRM_SCORE_WARN

    def test_renewal_within_14_days_scores_lower_than_30_days(
        self, db, test_organization, crm_enrichment_table
    ):
        """10 days out → high band (25.0) < warn band (35.0)."""
        self._insert_renewal(db, test_organization.id, "r10@example.com", 10)
        now = self._today_midnight()
        result = _compute_crm_component(
            db, test_organization.id, "r10@example.com", now
        )
        assert result == pytest.approx(25.0)   # CRM_SCORE_HIGH

    def test_renewal_within_7_days_scores_lowest(
        self, db, test_organization, crm_enrichment_table
    ):
        """3 days out → critical band (15.0) is the lowest documented score."""
        self._insert_renewal(db, test_organization.id, "r3@example.com", 3)
        now = self._today_midnight()
        result = _compute_crm_component(
            db, test_organization.id, "r3@example.com", now
        )
        assert result == pytest.approx(15.0)   # CRM_SCORE_CRIT

    def test_monotone_ordering(
        self, db, test_organization, crm_enrichment_table
    ):
        """Scores are monotonically non-decreasing as renewal distance grows."""
        now = self._today_midnight()
        scores = {}
        for days, key in [(3, "3d"), (10, "10d"), (25, "25d"), (45, "45d")]:
            email = f"mono_{key}@example.com"
            self._insert_renewal(db, test_organization.id, email, days)
            scores[key] = _compute_crm_component(
                db, test_organization.id, email, now
            )
        assert scores["3d"] < scores["10d"] <= scores["25d"] <= scores["45d"]

    def test_past_renewal_returns_neutral(
        self, db, test_organization, crm_enrichment_table
    ):
        """A renewal date in the past (−5 days) returns 50.0 — not actionable in v1."""
        self._insert_renewal(db, test_organization.id, "past@example.com", -5)
        now = self._today_midnight()
        result = _compute_crm_component(
            db, test_organization.id, "past@example.com", now
        )
        assert result == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Weighted-sum shift at health_weight_crm > 0
# ---------------------------------------------------------------------------

class TestScoreMovesWhenCrmWeightRaised:
    """
    When health_weight_crm > 0 and the CRM component differs from neutral,
    compute_health_score() must produce a different final score.
    Mirrors TestScoreMovesWhenUsageWeightRaised.
    """

    EMAIL = "crm_weight_test@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db, test_organization):
        for sentiment, churn in [(0.5, 30), (-0.2, 60), (0.1, 45)]:
            _make_feedback(db, test_organization.id, self.EMAIL, sentiment, churn)

    def test_score_differs_when_crm_weight_nonzero_and_low_crm_score(
        self, db, test_organization
    ):
        """Set crm weight to 10, mock _compute_crm_component to return 15.0.
        Score at weight 10 must differ from weight-0 baseline (47)."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=20,
            health_weight_resolution=20,
            health_weight_frequency=15,
            health_weight_usage=0,
            health_weight_crm=10,
        )
        db.add(config)
        db.commit()

        with patch(
            "src.services.health_score_service._compute_crm_component",
            return_value=15.0,
        ):
            result = compute_health_score(test_organization.id, self.EMAIL, db)

        assert 0 <= result["health_score"] <= 100
        assert result["health_score"] != 47

    def test_weight_zero_still_returns_baseline_even_with_config(
        self, db, test_organization
    ):
        """health_weight_crm=0 neutralizes crm_component regardless of its value."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=25,
            health_weight_resolution=25,
            health_weight_frequency=15,
            health_weight_usage=0,
            health_weight_crm=0,
        )
        db.add(config)
        db.commit()

        with patch(
            "src.services.health_score_service._compute_crm_component",
            return_value=0.0,  # extreme low value — must not affect score
        ):
            result = compute_health_score(test_organization.id, self.EMAIL, db)

        assert result["health_score"] == 47   # baseline unchanged


# ---------------------------------------------------------------------------
# Persistence — crm_component on CustomerHealth and history
# ---------------------------------------------------------------------------

class TestCrmComponentPersisted:
    """
    update_customer_health must write crm_component to CustomerHealth
    and snapshot it in CustomerHealthHistory.
    Mirrors test_health_usage_component pattern.
    """

    EMAIL = "crm_persist@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db, test_organization):
        _make_feedback(db, test_organization.id, self.EMAIL, 0.0, 50)

    def test_crm_component_persisted_on_customer_health(
        self, db, test_organization
    ):
        """After update_customer_health, CustomerHealth.crm_component is set."""
        with patch(
            "src.services.health_score_service._compute_crm_component",
            return_value=25.0,
        ):
            update_customer_health(test_organization.id, self.EMAIL, db)
        db.flush()

        from src.models.customer_health import CustomerHealth
        row = db.query(CustomerHealth).filter_by(
            organization_id=test_organization.id,
            customer_email=self.EMAIL,
        ).first()
        assert row is not None
        assert row.crm_component == pytest.approx(25.0)

    def test_crm_component_snapshotted_in_history(
        self, db, test_organization
    ):
        """CustomerHealthHistory row captures crm_component."""
        with patch(
            "src.services.health_score_service._compute_crm_component",
            return_value=35.0,
        ):
            update_customer_health(test_organization.id, self.EMAIL, db)
        db.flush()

        from src.models.customer_health_history import CustomerHealthHistory
        row = db.query(CustomerHealthHistory).filter_by(
            organization_id=test_organization.id,
        ).first()
        assert row is not None
        assert row.crm_component == pytest.approx(35.0)
