"""
TDD tests for backtest and backfill scripts (M1.4 Phase 7).

Tests cover core logic of both scripts, not the CLI wrapper.
"""
import csv
import io
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Backtest script tests
# ---------------------------------------------------------------------------

class TestChurnDetection:
    """Tests for the churn detection logic used in backtest."""

    def test_customer_with_no_feedback_in_30_days_is_churned(self, db: Session, test_organization: Organization):
        """A customer whose last_feedback_at is older than cutoff is considered churned."""
        from scripts.backtest_churn import is_churned

        old_date = datetime.utcnow() - timedelta(days=35)
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="old@example.com",
            health_score=70,
            risk_level="healthy",
            churn_risk_component=20,
            sentiment_component=70,
            resolution_component=50,
            frequency_component=50,
            feedback_count=5,
            last_feedback_at=old_date,
        )
        db.add(health)
        db.commit()

        assert is_churned(health, churn_days=30) is True

    def test_customer_with_recent_feedback_is_not_churned(self, db: Session, test_organization: Organization):
        """A customer whose last_feedback_at is within the window is not churned."""
        from scripts.backtest_churn import is_churned

        recent_date = datetime.utcnow() - timedelta(days=5)
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="recent@example.com",
            health_score=50,
            risk_level="at_risk",
            churn_risk_component=60,
            sentiment_component=40,
            resolution_component=50,
            frequency_component=50,
            feedback_count=3,
            last_feedback_at=recent_date,
        )
        db.add(health)
        db.commit()

        assert is_churned(health, churn_days=30) is False

    def test_customer_with_none_last_feedback_is_churned(self, db: Session, test_organization: Organization):
        """A customer with no last_feedback_at is considered churned."""
        from scripts.backtest_churn import is_churned

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="none@example.com",
            health_score=70,
            risk_level="healthy",
            churn_risk_component=20,
            sentiment_component=70,
            resolution_component=50,
            frequency_component=50,
            feedback_count=0,
            last_feedback_at=None,
        )
        db.add(health)
        db.commit()

        assert is_churned(health, churn_days=30) is True

    def test_churn_boundary_exactly_at_cutoff_is_not_churned(self, db: Session, test_organization: Organization):
        """A customer whose last feedback is exactly at the cutoff is NOT churned (boundary inclusive)."""
        from scripts.backtest_churn import is_churned

        exact_cutoff = datetime.utcnow() - timedelta(days=30)
        # Add a small delta to ensure it's right at boundary, not past it
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="boundary@example.com",
            health_score=60,
            risk_level="moderate",
            churn_risk_component=50,
            sentiment_component=60,
            resolution_component=50,
            frequency_component=50,
            feedback_count=2,
            last_feedback_at=exact_cutoff + timedelta(seconds=1),
        )
        db.add(health)
        db.commit()

        assert is_churned(health, churn_days=30) is False


class TestMetricsComputation:
    """Tests for precision/recall/F1/accuracy computation."""

    def test_perfect_prediction_gives_1_0_for_all_metrics(self):
        """All TP, no FP/FN: precision=recall=F1=accuracy=1.0."""
        from scripts.backtest_churn import compute_metrics

        metrics = compute_metrics(tp=10, fp=0, fn=0, tn=10)
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0
        assert metrics["accuracy"] == 1.0

    def test_zero_true_positives_gives_zero_precision_recall_f1(self):
        """No TP: precision=recall=F1=0."""
        from scripts.backtest_churn import compute_metrics

        metrics = compute_metrics(tp=0, fp=5, fn=5, tn=10)
        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1"] == 0.0

    def test_accuracy_computation(self):
        """Accuracy = (TP + TN) / total."""
        from scripts.backtest_churn import compute_metrics

        metrics = compute_metrics(tp=8, fp=2, fn=1, tn=9)
        total = 8 + 2 + 1 + 9
        expected_acc = (8 + 9) / total
        assert abs(metrics["accuracy"] - expected_acc) < 0.0001

    def test_f1_is_harmonic_mean_of_precision_and_recall(self):
        """F1 = 2 * P * R / (P + R)."""
        from scripts.backtest_churn import compute_metrics

        metrics = compute_metrics(tp=6, fp=2, fn=4, tn=8)
        precision = 6 / (6 + 2)
        recall = 6 / (6 + 4)
        expected_f1 = 2 * precision * recall / (precision + recall)
        assert abs(metrics["f1"] - expected_f1) < 0.0001

    def test_all_zeros_returns_zero_metrics(self):
        """Edge case: all zeros."""
        from scripts.backtest_churn import compute_metrics

        metrics = compute_metrics(tp=0, fp=0, fn=0, tn=0)
        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1"] == 0.0
        assert metrics["accuracy"] == 0.0


class TestOptimalThreshold:
    """Tests for optimal threshold search."""

    def test_optimal_threshold_finds_best_f1(self):
        """find_optimal_threshold should return the threshold that maximizes F1."""
        from scripts.backtest_churn import find_optimal_threshold

        # Create simple mock data: 5 customers with known scores
        # Churn risk score >= 60 perfectly predicts churn (customers 3,4,5 churned with scores 60,70,80)
        records = [
            {"churn_risk_score": 20, "actually_churned": False},
            {"churn_risk_score": 30, "actually_churned": False},
            {"churn_risk_score": 60, "actually_churned": True},
            {"churn_risk_score": 70, "actually_churned": True},
            {"churn_risk_score": 80, "actually_churned": True},
        ]

        best_threshold, best_f1 = find_optimal_threshold(records, score_key="churn_risk_score")
        # Threshold of 55-60 should achieve F1=1.0 (perfect separation)
        assert best_f1 == 1.0
        assert best_threshold <= 60

    def test_optimal_threshold_searches_range_20_to_80(self):
        """Threshold search should cover 20-80 in steps of 5."""
        from scripts.backtest_churn import find_optimal_threshold

        thresholds_tested = []
        records = [
            {"churn_risk_score": 50, "actually_churned": True},
        ]

        # We can't easily introspect which thresholds were tested, but we can verify
        # the returned threshold is in the expected range
        best_threshold, _ = find_optimal_threshold(records, score_key="churn_risk_score")
        assert 20 <= best_threshold <= 80


class TestCsvOutput:
    """Tests for CSV output generation."""

    def test_csv_has_correct_columns(self):
        """CSV output should have all required column headers."""
        from scripts.backtest_churn import build_csv_rows

        records = [
            {
                "customer_email": "test@example.com",
                "feedback_count": 5,
                "last_churn_risk_score": 70,
                "last_health_score": 40,
                "predicted_churn_by_risk": True,
                "predicted_churn_by_health": True,
                "actually_churned": True,
                "days_since_last_feedback": 45,
                "correct_risk": True,
                "correct_health": True,
            }
        ]

        buf = io.StringIO()
        build_csv_rows(records, buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        headers = reader.fieldnames

        expected_columns = {
            "customer_email",
            "feedback_count",
            "last_churn_risk_score",
            "last_health_score",
            "predicted_churn_by_risk",
            "predicted_churn_by_health",
            "actually_churned",
            "days_since_last_feedback",
            "correct_risk",
            "correct_health",
        }
        assert set(headers) == expected_columns

    def test_csv_has_correct_data_row(self):
        """CSV output rows should contain the correct data."""
        from scripts.backtest_churn import build_csv_rows

        records = [
            {
                "customer_email": "user@example.com",
                "feedback_count": 3,
                "last_churn_risk_score": 80,
                "last_health_score": 30,
                "predicted_churn_by_risk": True,
                "predicted_churn_by_health": True,
                "actually_churned": True,
                "days_since_last_feedback": 60,
                "correct_risk": True,
                "correct_health": True,
            }
        ]

        buf = io.StringIO()
        build_csv_rows(records, buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        row = next(reader)

        assert row["customer_email"] == "user@example.com"
        assert row["feedback_count"] == "3"
        assert row["last_churn_risk_score"] == "80"
        assert row["actually_churned"] == "True"


class TestInsufficientDataWarning:
    """Tests for the insufficient data warning."""

    def test_returns_warning_when_fewer_than_20_customers(self):
        """Should return a warning when fewer than 20 customers are evaluated."""
        from scripts.backtest_churn import check_data_sufficiency

        warning = check_data_sufficiency(customer_count=15)
        assert warning is not None
        assert "insufficient" in warning.lower() or "warning" in warning.lower() or "fewer" in warning.lower()

    def test_no_warning_when_20_or_more_customers(self):
        """Should return None when at least 20 customers are evaluated."""
        from scripts.backtest_churn import check_data_sufficiency

        warning = check_data_sufficiency(customer_count=20)
        assert warning is None

    def test_no_warning_when_many_customers(self):
        """Should return None when many customers are evaluated."""
        from scripts.backtest_churn import check_data_sufficiency

        warning = check_data_sufficiency(customer_count=500)
        assert warning is None


# ---------------------------------------------------------------------------
# Backfill script tests
# ---------------------------------------------------------------------------

class TestBackfillChurnFactors:
    """Tests for the backfill_churn_factors script."""

    def test_backfill_updates_items_with_null_churn_risk_factors(self, db: Session, test_organization: Organization):
        """Items with NULL churn_risk_factors but a churn_risk_score should be updated."""
        from scripts.backfill_churn_factors import get_items_to_backfill

        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="backfill@example.com",
            text="Test feedback",
            source="email",
            sentiment_score=-0.5,
            sentiment_label="negative",
            is_urgent=False,
            churn_risk_score=50,
            churn_risk_factors=None,  # NULL factors - needs backfill
        )
        db.add(fb)
        db.commit()

        items = get_items_to_backfill(db, org_id=None)
        assert any(i.id == fb.id for i in items)

    def test_backfill_skips_items_that_already_have_factors(self, db: Session, test_organization: Organization):
        """Items that already have churn_risk_factors should NOT be returned for backfill."""
        from scripts.backfill_churn_factors import get_items_to_backfill

        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="already@example.com",
            text="Test feedback",
            source="email",
            sentiment_score=-0.5,
            sentiment_label="negative",
            is_urgent=False,
            churn_risk_score=60,
            churn_risk_factors={"sentiment": {"score": 10, "max": 15, "label": "Negative"}},
        )
        db.add(fb)
        db.commit()

        items = get_items_to_backfill(db, org_id=None)
        assert not any(i.id == fb.id for i in items)

    def test_backfill_filters_by_org_id_when_provided(self, db: Session, test_organization: Organization):
        """When org_id is provided, only return items from that org."""
        from scripts.backfill_churn_factors import get_items_to_backfill

        # Create a second org
        other_org = Organization(name="Other Org Backfill", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        fb_other_org = FeedbackItem(
            organization_id=other_org.id,
            customer_email="other@example.com",
            text="Test feedback",
            source="email",
            sentiment_score=-0.5,
            sentiment_label="negative",
            is_urgent=False,
            churn_risk_score=50,
            churn_risk_factors=None,
        )
        fb_this_org = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="this@example.com",
            text="Test feedback",
            source="email",
            sentiment_score=-0.5,
            sentiment_label="negative",
            is_urgent=False,
            churn_risk_score=50,
            churn_risk_factors=None,
        )
        db.add(fb_other_org)
        db.add(fb_this_org)
        db.commit()

        items = get_items_to_backfill(db, org_id=test_organization.id)
        emails = [i.customer_email for i in items]
        assert "this@example.com" in emails
        assert "other@example.com" not in emails

    def test_backfill_skips_items_without_churn_risk_score(self, db: Session, test_organization: Organization):
        """Items that have never been scored (NULL churn_risk_score) should be skipped."""
        from scripts.backfill_churn_factors import get_items_to_backfill

        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="unscored@example.com",
            text="Test feedback",
            source="email",
            sentiment_score=0.0,
            sentiment_label="neutral",
            is_urgent=False,
            churn_risk_score=None,  # Never scored
            churn_risk_factors=None,
        )
        db.add(fb)
        db.commit()

        items = get_items_to_backfill(db, org_id=None)
        assert not any(i.id == fb.id for i in items)

    def test_dry_run_does_not_update_database(self, db: Session, test_organization: Organization):
        """In dry-run mode, no changes should be written to the database."""
        from scripts.backfill_churn_factors import run_backfill

        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="dryrun@example.com",
            text="I want to cancel my subscription",
            source="email",
            sentiment_score=-0.8,
            sentiment_label="negative",
            is_urgent=True,
            churn_risk_score=70,
            churn_risk_factors=None,
        )
        db.add(fb)
        db.commit()
        fb_id = fb.id

        run_backfill(db, org_id=test_organization.id, batch_size=100, dry_run=True)

        # Reload from db and confirm factors still NULL
        db.expire_all()
        refreshed = db.query(FeedbackItem).filter(FeedbackItem.id == fb_id).first()
        assert refreshed.churn_risk_factors is None

    def test_run_backfill_sets_churn_risk_factors(self, db: Session, test_organization: Organization):
        """run_backfill should set churn_risk_factors on items with NULL factors."""
        from scripts.backfill_churn_factors import run_backfill

        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="fillme@example.com",
            text="I want to cancel my subscription, this is terrible",
            source="email",
            sentiment_score=-0.8,
            sentiment_label="negative",
            is_urgent=True,
            churn_risk_score=70,
            churn_risk_factors=None,
        )
        db.add(fb)
        db.commit()
        fb_id = fb.id

        run_backfill(db, org_id=test_organization.id, batch_size=100, dry_run=False)

        db.expire_all()
        refreshed = db.query(FeedbackItem).filter(FeedbackItem.id == fb_id).first()
        assert refreshed.churn_risk_factors is not None
        assert isinstance(refreshed.churn_risk_factors, dict)

    def test_run_backfill_returns_count_of_updated_items(self, db: Session, test_organization: Organization):
        """run_backfill should return the count of items updated."""
        from scripts.backfill_churn_factors import run_backfill

        for i in range(3):
            fb = FeedbackItem(
                organization_id=test_organization.id,
                customer_email=f"batch{i}@example.com",
                text="Cancel my subscription now",
                source="email",
                sentiment_score=-0.6,
                sentiment_label="negative",
                is_urgent=False,
                churn_risk_score=55,
                churn_risk_factors=None,
            )
            db.add(fb)
        db.commit()

        count = run_backfill(db, org_id=test_organization.id, batch_size=100, dry_run=False)
        assert count >= 3
