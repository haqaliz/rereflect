"""
TDD tests for churn risk factor computation (M1.4 Phase 2):
- _compute_heuristic_churn_risk() returns Tuple[int, Dict]
- Factor dict contains all 9 keys with score/max/label
- Factor scores sum to composite score
- Labels describe the contribution clearly
- Customer-level factors return defaults when no customer_email/db
- churn_risk_factors stored on feedback after analysis
"""
import pytest
from unittest.mock import MagicMock, patch
from src.tasks.analysis import _compute_heuristic_churn_risk


EXPECTED_FACTOR_KEYS = {
    "sentiment",
    "churn_keywords",
    "frustration_keywords",
    "urgency",
    "sentiment_trend",
    "feedback_frequency",
    "resolution_time",
    "pain_severity",
    "feature_density",
}

EXPECTED_FACTOR_MAXES = {
    "sentiment": 15,
    "churn_keywords": 15,
    "frustration_keywords": 10,
    "urgency": 10,
    "sentiment_trend": 15,
    "feedback_frequency": 10,
    "resolution_time": 10,
    "pain_severity": 10,
    "feature_density": 5,
}


def make_simple_feedback(**kwargs):
    """Create a minimal MagicMock feedback object with sensible defaults."""
    fb = MagicMock()
    fb.text = kwargs.get("text", "This product is okay")
    fb.sentiment_score = kwargs.get("sentiment_score", 0.0)
    fb.is_urgent = kwargs.get("is_urgent", False)
    fb.customer_email = kwargs.get("customer_email", None)
    fb.organization_id = kwargs.get("organization_id", 1)
    fb.id = kwargs.get("id", 42)
    return fb


class TestReturnType:
    """_compute_heuristic_churn_risk() must return Tuple[int, Dict]."""

    def test_returns_tuple_not_int(self):
        """Function should return a tuple, not a plain int."""
        fb = make_simple_feedback()
        result = _compute_heuristic_churn_risk(fb)
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"

    def test_returns_two_element_tuple(self):
        """Tuple should have exactly 2 elements: (score, factors)."""
        fb = make_simple_feedback()
        result = _compute_heuristic_churn_risk(fb)
        assert len(result) == 2

    def test_first_element_is_int(self):
        """First element (score) should be an integer."""
        fb = make_simple_feedback()
        score, _ = _compute_heuristic_churn_risk(fb)
        assert isinstance(score, int)

    def test_second_element_is_dict(self):
        """Second element (factors) should be a dict."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        assert isinstance(factors, dict)


class TestFactorDictStructure:
    """The factors dict must have all 9 keys with correct sub-structure."""

    def test_factors_dict_has_all_nine_keys(self):
        """factors dict should contain all 9 expected factor keys."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        assert set(factors.keys()) == EXPECTED_FACTOR_KEYS

    def test_each_factor_has_score_key(self):
        """Each factor entry must have a 'score' key."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        for key, val in factors.items():
            assert "score" in val, f"Factor '{key}' missing 'score' key"

    def test_each_factor_has_max_key(self):
        """Each factor entry must have a 'max' key."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        for key, val in factors.items():
            assert "max" in val, f"Factor '{key}' missing 'max' key"

    def test_each_factor_has_label_key(self):
        """Each factor entry must have a 'label' key."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        for key, val in factors.items():
            assert "label" in val, f"Factor '{key}' missing 'label' key"

    def test_factor_max_values_are_correct(self):
        """Each factor's 'max' should match the PRD spec."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        for key, expected_max in EXPECTED_FACTOR_MAXES.items():
            assert factors[key]["max"] == expected_max, (
                f"Factor '{key}' expected max={expected_max}, got {factors[key]['max']}"
            )

    def test_factor_score_within_bounds(self):
        """Each factor score must be 0 <= score <= max."""
        fb = make_simple_feedback(
            text="I want to cancel, switching to competitor, this is frustrated terrible awful",
            sentiment_score=-0.9,
            is_urgent=True,
        )
        _, factors = _compute_heuristic_churn_risk(fb)
        for key, val in factors.items():
            assert 0 <= val["score"] <= val["max"], (
                f"Factor '{key}' score {val['score']} out of bounds [0, {val['max']}]"
            )

    def test_factor_label_is_nonempty_string(self):
        """Each factor label should be a non-empty string."""
        fb = make_simple_feedback()
        _, factors = _compute_heuristic_churn_risk(fb)
        for key, val in factors.items():
            assert isinstance(val["label"], str) and len(val["label"]) > 0, (
                f"Factor '{key}' has empty label"
            )


class TestScoreConsistency:
    """The composite score must equal the sum of all factor scores."""

    def test_composite_score_equals_sum_of_factor_scores(self):
        """score == sum of all factor['score'] values (before cap at 100)."""
        fb = make_simple_feedback(
            text="The product is okay",
            sentiment_score=0.0,
            is_urgent=False,
        )
        score, factors = _compute_heuristic_churn_risk(fb)
        factor_sum = sum(v["score"] for v in factors.values())
        # The composite score is min(factor_sum, 100)
        assert score == min(factor_sum, 100)

    def test_high_risk_feedback_score_matches_factor_sum(self):
        """For high-risk feedback, score should equal capped factor sum."""
        fb = make_simple_feedback(
            text="I'm canceling and switching to alternative, this is frustrated and terrible",
            sentiment_score=-0.8,
            is_urgent=True,
        )
        score, factors = _compute_heuristic_churn_risk(fb)
        factor_sum = sum(v["score"] for v in factors.values())
        assert score == min(factor_sum, 100)

    def test_score_capped_at_100(self):
        """Even when factor sum exceeds 100, composite score is capped at 100."""
        fb = make_simple_feedback(
            text="cancel leaving quit switch competitor refund waste terrible awful horrible frustrated disappointed unacceptable",
            sentiment_score=-0.9,
            is_urgent=True,
        )
        score, _ = _compute_heuristic_churn_risk(fb)
        assert score <= 100


class TestSentimentFactor:
    """Sentiment factor labels and scores match PRD spec."""

    def test_very_negative_sentiment_scores_15(self):
        """Sentiment < -0.5 should score 15 (max)."""
        fb = make_simple_feedback(sentiment_score=-0.8)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment"]["score"] == 15

    def test_moderately_negative_sentiment_scores_10(self):
        """Sentiment in [-0.5, -0.2) should score 10."""
        fb = make_simple_feedback(sentiment_score=-0.3)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment"]["score"] == 10

    def test_slightly_negative_sentiment_scores_5(self):
        """Sentiment in [-0.2, 0) should score 5."""
        fb = make_simple_feedback(sentiment_score=-0.1)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment"]["score"] == 5

    def test_positive_sentiment_scores_0(self):
        """Positive sentiment should score 0."""
        fb = make_simple_feedback(sentiment_score=0.5)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment"]["score"] == 0

    def test_none_sentiment_scores_0(self):
        """None sentiment should score 0."""
        fb = make_simple_feedback(sentiment_score=None)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment"]["score"] == 0

    def test_very_negative_sentiment_label_descriptive(self):
        """Very negative sentiment should have a descriptive label."""
        fb = make_simple_feedback(sentiment_score=-0.8)
        _, factors = _compute_heuristic_churn_risk(fb)
        label = factors["sentiment"]["label"].lower()
        assert any(word in label for word in ["negative", "very"]), (
            f"Expected 'negative'/'very' in label, got: {factors['sentiment']['label']}"
        )

    def test_neutral_positive_sentiment_label_mentions_neutral_or_positive(self):
        """Non-negative sentiment label should mention neutral or positive."""
        fb = make_simple_feedback(sentiment_score=0.5)
        _, factors = _compute_heuristic_churn_risk(fb)
        label = factors["sentiment"]["label"].lower()
        assert any(word in label for word in ["neutral", "positive"]), (
            f"Expected 'neutral'/'positive' in label, got: {factors['sentiment']['label']}"
        )


class TestUrgencyFactor:
    """Urgency factor reflects is_urgent flag."""

    def test_urgent_feedback_scores_10(self):
        """is_urgent=True should score 10."""
        fb = make_simple_feedback(is_urgent=True)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["urgency"]["score"] == 10

    def test_non_urgent_feedback_scores_0(self):
        """is_urgent=False should score 0."""
        fb = make_simple_feedback(is_urgent=False)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["urgency"]["score"] == 0

    def test_urgent_label_mentions_urgent(self):
        """Urgent factor label should mention 'urgent'."""
        fb = make_simple_feedback(is_urgent=True)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert "urgent" in factors["urgency"]["label"].lower()


class TestChurnKeywordsFactor:
    """Churn keywords factor: up to 15 pts based on keyword matches."""

    def test_no_churn_keywords_scores_0(self):
        """Text with no churn keywords should score 0."""
        fb = make_simple_feedback(text="The product works fine and I am happy")
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["churn_keywords"]["score"] == 0

    def test_one_churn_keyword_scores_5(self):
        """1 churn keyword should score 5."""
        fb = make_simple_feedback(text="I want to cancel my account")
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["churn_keywords"]["score"] == 5

    def test_three_churn_keywords_scores_15(self):
        """3+ churn keywords should score 15 (max)."""
        fb = make_simple_feedback(text="cancel switch leaving quit")
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["churn_keywords"]["score"] == 15

    def test_churn_keywords_label_mentions_count(self):
        """Label should mention the number of churn keywords found."""
        fb = make_simple_feedback(text="I want to cancel and switch")
        _, factors = _compute_heuristic_churn_risk(fb)
        label = factors["churn_keywords"]["label"]
        # Should mention 2 keywords found
        assert "2" in label or "churn keyword" in label.lower()


class TestFrustrationKeywordsFactor:
    """Frustration keywords factor: up to 10 pts."""

    def test_no_frustration_keywords_scores_0(self):
        """No frustration keywords → score 0."""
        fb = make_simple_feedback(text="The product is fine")
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["frustration_keywords"]["score"] == 0

    def test_one_frustration_keyword_scores_5(self):
        """1 frustration keyword → score 5."""
        fb = make_simple_feedback(text="I am frustrated with this product")
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["frustration_keywords"]["score"] == 5

    def test_two_frustration_keywords_scores_10(self):
        """2+ frustration keywords → score 10 (max)."""
        fb = make_simple_feedback(text="This is terrible and horrible")
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["frustration_keywords"]["score"] == 10


class TestCustomerLevelFactorsWithoutDB:
    """Customer-level factors (sentiment_trend, feedback_frequency, etc.) default to 0 when no customer_email or db."""

    def test_no_customer_email_returns_zero_customer_factors(self):
        """Without customer_email, all 5 customer-level factors should score 0."""
        fb = make_simple_feedback(customer_email=None)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment_trend"]["score"] == 0
        assert factors["feedback_frequency"]["score"] == 0
        assert factors["resolution_time"]["score"] == 0
        assert factors["pain_severity"]["score"] == 0
        assert factors["feature_density"]["score"] == 0

    def test_no_db_returns_zero_customer_factors(self):
        """Without db session, all 5 customer-level factors should score 0."""
        fb = make_simple_feedback(customer_email="user@example.com")
        _, factors = _compute_heuristic_churn_risk(fb, db=None)
        assert factors["sentiment_trend"]["score"] == 0
        assert factors["feedback_frequency"]["score"] == 0
        assert factors["resolution_time"]["score"] == 0
        assert factors["pain_severity"]["score"] == 0
        assert factors["feature_density"]["score"] == 0

    def test_no_customer_email_still_returns_all_nine_factors(self):
        """Even without customer_email, all 9 factor keys must be present."""
        fb = make_simple_feedback(customer_email=None)
        _, factors = _compute_heuristic_churn_risk(fb)
        assert set(factors.keys()) == EXPECTED_FACTOR_KEYS

    def test_no_customer_email_text_factors_still_computed(self):
        """Without customer_email, text-based factors (sentiment, keywords, urgency) are still computed."""
        fb = make_simple_feedback(
            text="I want to cancel this terrible product",
            sentiment_score=-0.8,
            is_urgent=True,
            customer_email=None,
        )
        _, factors = _compute_heuristic_churn_risk(fb)
        assert factors["sentiment"]["score"] == 15
        assert factors["urgency"]["score"] == 10
        assert factors["churn_keywords"]["score"] >= 5


class TestBackwardCompatibility:
    """Ensure existing behavior still works after the signature change."""

    def test_very_negative_sentiment_with_keywords_and_urgency_scores_high(self):
        """High-risk feedback (negative sentiment + churn keywords + urgency) produces elevated score."""
        fb = make_simple_feedback(
            text="I'm canceling my subscription, this is terrible",
            sentiment_score=-0.8,
            is_urgent=True,
        )
        score, _ = _compute_heuristic_churn_risk(fb)
        # sentiment(15) + urgency(10) + cancel(5) + terrible(5) = 35
        assert score >= 30

    def test_neutral_feedback_low_score(self):
        """Neutral/positive feedback should still produce low composite score."""
        fb = make_simple_feedback(
            text="The product is okay, nothing special",
            sentiment_score=0.1,
            is_urgent=False,
        )
        score, _ = _compute_heuristic_churn_risk(fb)
        assert score < 40

    def test_positive_feedback_zero_score(self):
        """Positive feedback with no keywords should score 0."""
        fb = make_simple_feedback(
            text="Love this product, great work!",
            sentiment_score=0.9,
            is_urgent=False,
        )
        score, _ = _compute_heuristic_churn_risk(fb)
        assert score == 0
