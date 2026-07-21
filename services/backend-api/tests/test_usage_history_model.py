"""
TDD tests for the CustomerUsageHistory model — usage-history-snapshot aspect.

RED phase: these tests should fail until src/models/customer_usage_history.py
exists and is exported from src/models/__init__.py.

Covers:
  AC 6  — FK ondelete=CASCADE (asserted on the backend-api model + a
          behavioural companion test).
  AC 8  — composite lookback index exists on
          (organization_id, customer_email, snapshot_date), structurally.
  AC 13 — health scores are unaffected by this aspect: it writes only to a
          new table that compute_health_score() never reads.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.models.organization import Organization


class TestCustomerUsageHistoryImportable:
    def test_importable_from_module(self):
        from src.models.customer_usage_history import CustomerUsageHistory
        assert CustomerUsageHistory is not None

    def test_exported_from_models_init(self):
        from src.models import CustomerUsageHistory
        assert CustomerUsageHistory is not None

    def test_table_name(self):
        from src.models.customer_usage_history import CustomerUsageHistory
        assert CustomerUsageHistory.__tablename__ == "customer_usage_history"


class TestCustomerUsageHistoryCreate:
    def test_can_be_created_with_full_payload(
        self, db: Session, test_organization: Organization
    ):
        from src.models.customer_usage_history import CustomerUsageHistory

        row = CustomerUsageHistory(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
            snapshot_date=date(2026, 7, 22),
            active_days_7d=5,
            active_days_14d=9,
            active_days_30d=20,
            login_count_30d=18,
            distinct_feature_count=3,
            usage_score=72,
            last_active_at=datetime(2026, 7, 22, 8, 0, 0),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        assert row.id is not None
        assert row.organization_id == test_organization.id
        assert row.customer_email == "alice@example.com"
        assert row.snapshot_date == date(2026, 7, 22)
        assert row.active_days_7d == 5
        assert row.active_days_14d == 9
        assert row.active_days_30d == 20
        assert row.login_count_30d == 18
        assert row.distinct_feature_count == 3
        assert row.usage_score == 72
        assert row.last_active_at == datetime(2026, 7, 22, 8, 0, 0)
        assert row.created_at is not None

    def test_payload_columns_are_nullable(
        self, db: Session, test_organization: Organization
    ):
        """A row with only the required identity fields is valid — payload is
        all nullable, so a customer with no rollup fields yet can still be
        snapshotted."""
        from src.models.customer_usage_history import CustomerUsageHistory

        row = CustomerUsageHistory(
            organization_id=test_organization.id,
            customer_email="bare@example.com",
            snapshot_date=date(2026, 7, 22),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.id is not None

    def test_unique_constraint_org_email_date(
        self, db: Session, test_organization: Organization
    ):
        from src.models.customer_usage_history import CustomerUsageHistory
        from sqlalchemy.exc import IntegrityError

        row1 = CustomerUsageHistory(
            organization_id=test_organization.id,
            customer_email="dup@example.com",
            snapshot_date=date(2026, 7, 22),
        )
        db.add(row1)
        db.commit()

        row2 = CustomerUsageHistory(
            organization_id=test_organization.id,
            customer_email="dup@example.com",
            snapshot_date=date(2026, 7, 22),
        )
        db.add(row2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_same_email_different_orgs_coexist(
        self, db: Session, test_organization: Organization
    ):
        """AC 5: two organizations with the same customer_email on the same
        snapshot_date are distinguishable rows, not a constraint violation."""
        from src.models.customer_usage_history import CustomerUsageHistory

        other_org = Organization(name="Other Co", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        row1 = CustomerUsageHistory(
            organization_id=test_organization.id,
            customer_email="shared@example.com",
            snapshot_date=date(2026, 7, 22),
            usage_score=10,
        )
        row2 = CustomerUsageHistory(
            organization_id=other_org.id,
            customer_email="shared@example.com",
            snapshot_date=date(2026, 7, 22),
            usage_score=90,
        )
        db.add_all([row1, row2])
        db.commit()

        org_scoped = (
            db.query(CustomerUsageHistory)
            .filter_by(organization_id=test_organization.id, customer_email="shared@example.com")
            .all()
        )
        assert len(org_scoped) == 1
        assert org_scoped[0].usage_score == 10


class TestCustomerUsageHistoryForeignKeyCascade:
    """AC 6: FK ondelete=CASCADE, asserted on the backend-api model."""

    def test_organization_id_fk_declares_ondelete_cascade(self):
        from src.models.customer_usage_history import CustomerUsageHistory

        fks = list(CustomerUsageHistory.__table__.columns["organization_id"].foreign_keys)
        assert fks, "organization_id must declare a ForeignKey to organizations.id"
        assert fks[0].ondelete == "CASCADE", (
            f"organization_id FK must be ondelete='CASCADE', got {fks[0].ondelete!r}"
        )

    def test_cascade_delete_removes_history_rows(
        self, db: Session, test_organization: Organization
    ):
        """Behavioural companion to the structural FK check above. SQLite does
        not enforce FK constraints without PRAGMA foreign_keys=ON, so — same
        pattern as test_churn_models.py's org-cascade tests — the child row
        is deleted alongside the org to mimic the ON DELETE CASCADE behaviour
        that PostgreSQL enforces in production from the declared FK."""
        from src.models.customer_usage_history import CustomerUsageHistory

        org = Organization(name="DeleteMe", plan="pro")
        db.add(org)
        db.commit()
        db.refresh(org)

        row = CustomerUsageHistory(
            organization_id=org.id,
            customer_email="gone@example.com",
            snapshot_date=date(2026, 7, 22),
        )
        db.add(row)
        db.commit()
        row_id = row.id

        db.delete(row)
        db.delete(org)
        db.commit()

        remaining = (
            db.query(CustomerUsageHistory)
            .filter(CustomerUsageHistory.id == row_id)
            .count()
        )
        assert remaining == 0


class TestCustomerUsageHistoryLookbackIndex:
    """AC 8: composite index on (organization_id, customer_email, snapshot_date)."""

    def test_composite_index_declared_on_model(self):
        from src.models.customer_usage_history import CustomerUsageHistory

        indexes = CustomerUsageHistory.__table__.indexes
        matching = [
            ix for ix in indexes
            if [c.name for c in ix.columns] == [
                "organization_id", "customer_email", "snapshot_date",
            ]
        ]
        assert matching, (
            f"No index declared on (organization_id, customer_email, "
            f"snapshot_date); got {[[c.name for c in ix.columns] for ix in indexes]}"
        )


class TestHealthScoresUnaffectedByUsageHistoryTable:
    """AC 13: this aspect writes only to a new table; compute_health_score()
    must produce identical output whether or not customer_usage_history rows
    exist, at any usage weight."""

    EMAIL = "usage_history_char@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db: Session, test_organization: Organization):
        from src.models.feedback import FeedbackItem
        from src.models.customer_usage import CustomerUsage
        from src.services.usage_score_service import compute_usage_score

        for sentiment, churn in [(0.5, 30), (-0.2, 60), (0.1, 45)]:
            fb = FeedbackItem(
                organization_id=test_organization.id,
                customer_email=self.EMAIL,
                text="usage history characterization",
                source="email",
                sentiment_score=sentiment,
                sentiment_label="neutral",
                churn_risk_score=churn,
                is_urgent=False,
                created_at=datetime.utcnow(),
            )
            db.add(fb)

        rollup = CustomerUsage(
            organization_id=test_organization.id,
            customer_email=self.EMAIL,
            last_active_at=datetime.utcnow() - timedelta(days=1),
            active_days_7d=6, active_days_14d=12, active_days_30d=25,
            login_count_30d=40,
            distinct_feature_count=5,
        )
        rollup.usage_score = compute_usage_score(rollup)
        db.add(rollup)
        db.commit()

    @pytest.mark.parametrize("usage_weight", [0, 10, 30])
    def test_health_score_identical_with_and_without_history_rows(
        self, db: Session, test_organization: Organization, usage_weight: int
    ):
        from src.models.org_ai_config import OrgAIConfig
        from src.models.customer_usage_history import CustomerUsageHistory
        from src.services.health_score_service import compute_health_score

        remaining = 100 - usage_weight
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=remaining // 2,
            health_weight_sentiment=remaining - (remaining // 2),
            health_weight_resolution=0,
            health_weight_frequency=0,
            health_weight_usage=usage_weight,
            health_weight_crm=0,
        )
        db.add(config)
        db.commit()

        before = compute_health_score(test_organization.id, self.EMAIL, db)

        # Now populate the new table — this aspect's entire footprint.
        for days_ago, score in [(20, 40), (14, 55), (7, 65)]:
            db.add(CustomerUsageHistory(
                organization_id=test_organization.id,
                customer_email=self.EMAIL,
                snapshot_date=date.today() - timedelta(days=days_ago),
                usage_score=score,
                active_days_7d=3, active_days_14d=6, active_days_30d=15,
                login_count_30d=20, distinct_feature_count=2,
            ))
        db.commit()

        after = compute_health_score(test_organization.id, self.EMAIL, db)

        assert after == before, (
            f"compute_health_score() changed after adding customer_usage_history "
            f"rows at usage_weight={usage_weight}: before={before} after={after}"
        )
