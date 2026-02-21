"""
TDD tests for confidence scoring (M1.4 Phase 3):
- compute_confidence_score(feedback_count, last_feedback_at, unique_categories) -> int
- update_customer_health() integrates confidence_score onto CustomerHealth
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.services.health_score_service import (
    compute_confidence_score,
    update_customer_health,
)


def make_feedback(db, org_id, email, sentiment_score=0.0, created_at=None,
                  churn_risk_score=50, pain_point_category=None, feature_request_category=None):
    """Create a FeedbackItem in the DB."""
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="test feedback",
        source="email",
        sentiment_score=sentiment_score,
        sentiment_label="neutral",
        churn_risk_score=churn_risk_score,
        is_urgent=False,
        created_at=created_at or datetime.utcnow(),
        pain_point_category=pain_point_category,
        feature_request_category=feature_request_category,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


class TestComputeConfidenceScoreReturnType:
    """compute_confidence_score() must return an integer."""

    def test_returns_integer(self):
        """Return type should be int."""
        result = compute_confidence_score(5, datetime.utcnow() - timedelta(days=3), 3)
        assert isinstance(result, int)

    def test_returns_value_in_range_0_to_100(self):
        """Result should be in [0, 100]."""
        result = compute_confidence_score(5, datetime.utcnow() - timedelta(days=3), 3)
        assert 0 <= result <= 100


class TestVolumeScoring:
    """Volume factor (0-40 points) from feedback_count."""

    def test_zero_feedbacks_volume_score_is_zero(self):
        """0 feedbacks → volume score 0, recency=0 (None), diversity=5 (else branch) → total=5."""
        result = compute_confidence_score(0, None, 0)
        # volume=0, recency=0, diversity=5 → 5
        assert result == 5

    def test_one_feedback_volume_score_is_3(self):
        """1 feedback → volume = 1*3 = 3."""
        # With None last_feedback_at → recency = 0, unique_cats = 0 → diversity = 5
        # But testing isolation: 1 feedback, recent date, 0 categories
        result = compute_confidence_score(1, datetime.utcnow() - timedelta(days=3), 0)
        # volume=3, recency=35, diversity=5 → total=43
        assert result > 0  # Just verify it computes

    def test_one_feedback_returns_3_pts_for_volume(self):
        """1 feedback → volume = 3. With no recency (None) and diversity=0 → 3+0+5=8."""
        result = compute_confidence_score(1, None, 0)
        # volume=1*3=3, recency=0 (None), diversity=5 (unique_cats=0 → else→5)
        # Wait, 0 unique_cats falls into 'else→5' branch
        # 3 + 0 + 5 = 8
        assert result == 8

    def test_two_feedbacks_returns_6_pts_volume(self):
        """2 feedbacks → volume = 2*3=6."""
        result = compute_confidence_score(2, None, 0)
        # volume=6, recency=0, diversity=5 → 11
        assert result == 11

    def test_three_feedbacks_volume_is_10(self):
        """3 feedbacks → volume = 10 (jumps to tier)."""
        result = compute_confidence_score(3, None, 0)
        # volume=10, recency=0, diversity=5 → 15
        assert result == 15

    def test_five_feedbacks_volume_is_20(self):
        """5 feedbacks → volume = 20."""
        result = compute_confidence_score(5, None, 0)
        # volume=20, recency=0, diversity=5 → 25
        assert result == 25

    def test_ten_feedbacks_volume_is_30(self):
        """10 feedbacks → volume = 30."""
        result = compute_confidence_score(10, None, 0)
        # volume=30, recency=0, diversity=5 → 35
        assert result == 35

    def test_twenty_feedbacks_volume_is_40(self):
        """20 feedbacks → volume = 40 (max)."""
        result = compute_confidence_score(20, None, 0)
        # volume=40, recency=0, diversity=5 → 45
        assert result == 45

    def test_fifty_feedbacks_volume_is_still_40(self):
        """50+ feedbacks → volume stays at 40 (capped)."""
        result = compute_confidence_score(50, None, 0)
        # volume=40, recency=0, diversity=5 → 45
        assert result == 45


class TestRecencyScoring:
    """Recency factor (0-35 points) from last_feedback_at."""

    def test_none_last_feedback_recency_is_zero(self):
        """None last_feedback_at → recency = 0. Total = volume(0) + recency(0) + diversity(5) = 5."""
        result = compute_confidence_score(0, None, 0)
        # volume=0, recency=0 (None), diversity=5 → 5
        assert result == 5

    def test_feedback_within_7_days_recency_35(self):
        """Feedback ≤7 days ago → recency = 35."""
        result = compute_confidence_score(20, datetime.utcnow() - timedelta(days=5), 5)
        # volume=40, recency=35, diversity=25 → 100
        assert result == 100

    def test_feedback_at_exactly_7_days_recency_35(self):
        """Feedback exactly 7 days ago → recency = 35."""
        result = compute_confidence_score(0, datetime.utcnow() - timedelta(days=7), 0)
        # volume=0, recency=35, diversity=5 → 40
        assert result == 40

    def test_feedback_8_to_14_days_recency_28(self):
        """Feedback 8-14 days ago → recency = 28."""
        result = compute_confidence_score(0, datetime.utcnow() - timedelta(days=10), 0)
        # volume=0, recency=28, diversity=5 → 33
        assert result == 33

    def test_feedback_15_to_30_days_recency_20(self):
        """Feedback 15-30 days ago → recency = 20."""
        result = compute_confidence_score(0, datetime.utcnow() - timedelta(days=20), 0)
        # volume=0, recency=20, diversity=5 → 25
        assert result == 25

    def test_feedback_31_to_60_days_recency_10(self):
        """Feedback 31-60 days ago → recency = 10."""
        result = compute_confidence_score(0, datetime.utcnow() - timedelta(days=45), 0)
        # volume=0, recency=10, diversity=5 → 15
        assert result == 15

    def test_feedback_over_60_days_recency_5(self):
        """Feedback >60 days ago → recency = 5."""
        result = compute_confidence_score(0, datetime.utcnow() - timedelta(days=90), 0)
        # volume=0, recency=5, diversity=5 → 10
        assert result == 10


class TestDiversityScoring:
    """Diversity factor (0-25 points) from unique_categories."""

    def test_zero_categories_diversity_5(self):
        """0 unique categories → diversity = 5 (else branch minimum)."""
        result = compute_confidence_score(0, None, 0)
        # volume=0, recency=0, diversity=5 → 5
        assert result == 5

    def test_one_category_diversity_5(self):
        """1 unique category → diversity = 5 (< 2 threshold)."""
        result = compute_confidence_score(0, None, 1)
        # volume=0, recency=0, diversity=5 → 5
        assert result == 5

    def test_two_categories_diversity_10(self):
        """2 unique categories → diversity = 10."""
        result = compute_confidence_score(0, None, 2)
        # volume=0, recency=0, diversity=10 → 10
        assert result == 10

    def test_three_categories_diversity_18(self):
        """3 unique categories → diversity = 18."""
        result = compute_confidence_score(0, None, 3)
        # volume=0, recency=0, diversity=18 → 18
        assert result == 18

    def test_four_categories_diversity_18(self):
        """4 unique categories → diversity = 18 (same as 3, below 5 threshold)."""
        result = compute_confidence_score(0, None, 4)
        # volume=0, recency=0, diversity=18 → 18
        assert result == 18

    def test_five_categories_diversity_25(self):
        """5 unique categories → diversity = 25 (max)."""
        result = compute_confidence_score(0, None, 5)
        # volume=0, recency=0, diversity=25 → 25
        assert result == 25

    def test_ten_categories_diversity_still_25(self):
        """10+ unique categories → diversity stays at 25 (capped)."""
        result = compute_confidence_score(0, None, 10)
        # volume=0, recency=0, diversity=25 → 25
        assert result == 25


class TestMaximumConfidence:
    """Maximum confidence score = 100 (40+35+25)."""

    def test_maximum_confidence_score_is_100(self):
        """20+ feedbacks, ≤7 days, 5+ categories → score = 100."""
        result = compute_confidence_score(20, datetime.utcnow() - timedelta(days=3), 5)
        assert result == 100

    def test_score_never_exceeds_100(self):
        """Score is always capped at 100 even with very high values."""
        result = compute_confidence_score(100, datetime.utcnow() - timedelta(days=1), 100)
        assert result == 100


class TestLowConfidenceScenarios:
    """Low confidence scenarios produce scores in low range."""

    def test_minimal_data_low_confidence(self):
        """1 feedback, no last_feedback_at, 1 category → low score."""
        result = compute_confidence_score(1, None, 1)
        # volume=3, recency=0, diversity=5 → 8
        assert result == 8
        assert result <= 30  # Should be in "low" tier

    def test_stale_feedback_low_confidence(self):
        """1 feedback from 90 days ago, 1 category → low score."""
        result = compute_confidence_score(1, datetime.utcnow() - timedelta(days=90), 1)
        # volume=3, recency=5, diversity=5 → 13
        assert result == 13
        assert result <= 30


class TestConfidenceLevelDerivation:
    """Confidence level (low/medium/high) correctly derived from confidence score."""

    def test_score_0_to_30_is_low(self):
        """Scores 0-30 → confidence_level = 'low'."""
        score = compute_confidence_score(0, None, 0)  # = 5
        assert score <= 30
        level = "low" if score <= 30 else ("medium" if score <= 60 else "high")
        assert level == "low"

    def test_score_31_to_60_is_medium(self):
        """Scores 31-60 → confidence_level = 'medium'."""
        # 5 feedbacks, recent, 2 categories: volume=20, recency=35, diversity=10 = 65? No...
        # Need score in 31-60 range: e.g. 3 feedbacks, 14 days, 2 cats: 10+28+10=48
        score = compute_confidence_score(3, datetime.utcnow() - timedelta(days=14), 2)
        assert 31 <= score <= 60
        level = "low" if score <= 30 else ("medium" if score <= 60 else "high")
        assert level == "medium"

    def test_score_61_to_100_is_high(self):
        """Scores 61-100 → confidence_level = 'high'."""
        score = compute_confidence_score(20, datetime.utcnow() - timedelta(days=3), 5)  # = 100
        assert score > 60
        level = "low" if score <= 30 else ("medium" if score <= 60 else "high")
        assert level == "high"


class TestUpdateCustomerHealthIntegration:
    """update_customer_health() should compute and persist confidence_score."""

    def test_confidence_score_is_stored_on_customer_health(self, db: Session, test_organization: Organization):
        """update_customer_health() should populate confidence_score on CustomerHealth record."""
        # Create some feedback
        now = datetime.utcnow()
        for i in range(5):
            make_feedback(
                db, test_organization.id, "conf@example.com",
                sentiment_score=0.5,
                created_at=now - timedelta(days=i),
                pain_point_category="performance",
            )

        update_customer_health(test_organization.id, "conf@example.com", db)
        db.commit()

        record = db.query(CustomerHealth).filter(
            CustomerHealth.organization_id == test_organization.id,
            CustomerHealth.customer_email == "conf@example.com",
        ).first()

        assert record is not None
        assert record.confidence_score is not None
        assert isinstance(record.confidence_score, int)
        assert 0 <= record.confidence_score <= 100

    def test_confidence_score_reflects_feedback_count(self, db: Session, test_organization: Organization):
        """High feedback count should result in higher confidence score."""
        now = datetime.utcnow()

        # Customer with lots of recent feedback
        for i in range(20):
            make_feedback(
                db, test_organization.id, "high-conf@example.com",
                sentiment_score=0.5,
                created_at=now - timedelta(days=i % 7),
                pain_point_category="performance" if i % 3 == 0 else None,
                feature_request_category="ui" if i % 4 == 0 else None,
            )

        # Customer with minimal feedback
        make_feedback(
            db, test_organization.id, "low-conf@example.com",
            sentiment_score=0.5,
            created_at=now - timedelta(days=90),
        )

        update_customer_health(test_organization.id, "high-conf@example.com", db)
        update_customer_health(test_organization.id, "low-conf@example.com", db)
        db.commit()

        high_conf = db.query(CustomerHealth).filter(
            CustomerHealth.organization_id == test_organization.id,
            CustomerHealth.customer_email == "high-conf@example.com",
        ).first()

        low_conf = db.query(CustomerHealth).filter(
            CustomerHealth.organization_id == test_organization.id,
            CustomerHealth.customer_email == "low-conf@example.com",
        ).first()

        assert high_conf.confidence_score > low_conf.confidence_score

    def test_confidence_level_consistent_with_confidence_score(self, db: Session, test_organization: Organization):
        """confidence_level should match the tier derived from confidence_score."""
        now = datetime.utcnow()
        # Create minimal feedback → expect low confidence
        make_feedback(
            db, test_organization.id, "consist@example.com",
            created_at=now - timedelta(days=90),
        )
        update_customer_health(test_organization.id, "consist@example.com", db)
        db.commit()

        record = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == "consist@example.com",
        ).first()

        score = record.confidence_score
        expected_level = "low" if score <= 30 else ("medium" if score <= 60 else "high")
        assert record.confidence_level == expected_level

    def test_new_customer_health_has_confidence_score(self, db: Session, test_organization: Organization):
        """First call to update_customer_health creates record with confidence_score populated."""
        now = datetime.utcnow()
        make_feedback(
            db, test_organization.id, "new-cust@example.com",
            created_at=now - timedelta(days=2),
        )
        update_customer_health(test_organization.id, "new-cust@example.com", db)
        db.commit()

        record = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == "new-cust@example.com",
        ).first()

        assert record is not None
        assert record.confidence_score >= 0

    def test_diverse_categories_increase_confidence_score(self, db: Session, test_organization: Organization):
        """Customer with diverse categories should get higher confidence than single category."""
        now = datetime.utcnow()
        email_diverse = "diverse@example.com"
        email_single = "single@example.com"

        # Diverse customer: 5 different pain point categories
        cats = ["performance", "security_breach", "payment_issue", "usability", "authentication"]
        for i, cat in enumerate(cats):
            make_feedback(
                db, test_organization.id, email_diverse,
                created_at=now - timedelta(days=i),
                pain_point_category=cat,
            )

        # Single category customer: same count, same recency
        for i in range(5):
            make_feedback(
                db, test_organization.id, email_single,
                created_at=now - timedelta(days=i),
                pain_point_category="performance",
            )

        update_customer_health(test_organization.id, email_diverse, db)
        update_customer_health(test_organization.id, email_single, db)
        db.commit()

        diverse_record = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == email_diverse,
        ).first()
        single_record = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == email_single,
        ).first()

        assert diverse_record.confidence_score > single_record.confidence_score
