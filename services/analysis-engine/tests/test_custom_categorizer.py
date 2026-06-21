"""
TDD tests for Feature B1: custom category augmentation of keyword categorisers.

Tests cover PainPointCategorizer, FeatureRequestCategorizer, and UrgentCategorizer
after the add_custom_categories() method is introduced.

Run from analysis-engine service root:
    python3 -c "import sys,pytest; sys.exit(pytest.main(['tests/test_custom_categorizer.py','-q']))"
"""

import pytest
from src.analyzer.categorizer import (
    PainPointCategorizer,
    FeatureRequestCategorizer,
    UrgentCategorizer,
)


# ---------------------------------------------------------------------------
# PainPointCategorizer + custom categories
# ---------------------------------------------------------------------------

class TestPainPointCategorizerCustom:
    def test_custom_pain_point_category_matches_feedback(self):
        """A custom pain_point category is recognised via description-derived keywords."""
        categorizer = PainPointCategorizer()
        custom_cats = [
            {
                "name": "network_outage",
                "category_type": "pain_point",
                "description": "network outage connectivity down",
            }
        ]
        categorizer.add_custom_categories(custom_cats)

        result = categorizer.categorize("We have a network outage and connectivity is down")
        assert result.category == "network_outage"

    def test_built_in_categories_still_work_after_adding_custom(self):
        """Built-in categories must still take priority over weak custom entries."""
        categorizer = PainPointCategorizer()
        custom_cats = [
            {
                "name": "my_custom_category",
                "category_type": "pain_point",
                "description": "some custom thing xyzzy",
            }
        ]
        categorizer.add_custom_categories(custom_cats)

        # "crash" + "freeze" — strong built-in match → system_crash wins
        result = categorizer.categorize("The app crashes and freezes every time")
        assert result.category == "system_crash"

    def test_general_custom_category_does_not_break_categoriser(self):
        """A 'general' type entry should be silently ignored."""
        categorizer = PainPointCategorizer()
        custom_cats = [
            {"name": "general_feedback", "category_type": "general", "description": "general misc"},
        ]
        categorizer.add_custom_categories(custom_cats)
        result = categorizer.categorize("Some feedback text")
        assert result is not None
        assert result.category != "general_feedback"

    def test_non_pain_point_custom_cats_not_added_to_pain_point_categoriser(self):
        """feature_request and urgency entries must be ignored by PainPointCategorizer."""
        categorizer = PainPointCategorizer()
        custom_cats = [
            {"name": "sso_request", "category_type": "feature_request", "description": "sso login"},
            {"name": "gdpr_issue", "category_type": "urgency", "description": "gdpr violation"},
        ]
        categorizer.add_custom_categories(custom_cats)
        assert "sso_request" not in categorizer.CATEGORIES
        assert "gdpr_issue" not in categorizer.CATEGORIES

    def test_custom_category_without_description_uses_name_as_keyword(self):
        """A custom category with no description should use its name as a keyword."""
        categorizer = PainPointCategorizer()
        # Use a unique name that does not match any built-in keywords
        custom_cats = [
            {"name": "billing_latency", "category_type": "pain_point", "description": ""},
        ]
        categorizer.add_custom_categories(custom_cats)
        assert "billing_latency" in categorizer.CATEGORIES
        keywords = categorizer.CATEGORIES["billing_latency"]["keywords"]
        # Name-derived keyword: "billing latency" (hyphen replaced by space)
        assert any("billing" in kw or "billing latency" in kw for kw in keywords)


# ---------------------------------------------------------------------------
# FeatureRequestCategorizer + custom categories
# ---------------------------------------------------------------------------

class TestFeatureRequestCategorizerCustom:
    def test_custom_feature_request_category_matches_feedback(self):
        """A custom feature_request category is recognised via description-derived keywords."""
        categorizer = FeatureRequestCategorizer()
        custom_cats = [
            {
                "name": "sso_login",
                "category_type": "feature_request",
                "description": "sso single sign-on saml login",
            }
        ]
        categorizer.add_custom_categories(custom_cats)

        result = categorizer.categorize("Please add SSO single sign-on support")
        assert result.category == "sso_login"

    def test_pain_point_and_urgency_cats_not_added_to_feature_request_categoriser(self):
        """Only feature_request entries apply here."""
        categorizer = FeatureRequestCategorizer()
        custom_cats = [
            {"name": "network_outage", "category_type": "pain_point", "description": "network"},
            {"name": "gdpr_alert", "category_type": "urgency", "description": "gdpr"},
        ]
        categorizer.add_custom_categories(custom_cats)
        assert "network_outage" not in categorizer.CATEGORIES
        assert "gdpr_alert" not in categorizer.CATEGORIES

    def test_add_multiple_custom_feature_request_categories(self):
        """Multiple custom entries can be added in one call."""
        categorizer = FeatureRequestCategorizer()
        custom_cats = [
            {"name": "bulk_upload", "category_type": "feature_request",
             "description": "bulk upload import files csv"},
            {"name": "gantt_chart", "category_type": "feature_request",
             "description": "gantt chart timeline project management"},
        ]
        categorizer.add_custom_categories(custom_cats)
        assert "bulk_upload" in categorizer.CATEGORIES
        assert "gantt_chart" in categorizer.CATEGORIES


# ---------------------------------------------------------------------------
# UrgentCategorizer + custom categories
# ---------------------------------------------------------------------------

class TestUrgentCategorizerCustom:
    def test_custom_urgency_category_matches_feedback(self):
        """A custom urgency category is recognised via description-derived keywords."""
        categorizer = UrgentCategorizer()
        custom_cats = [
            {
                "name": "gdpr_violation",
                "category_type": "urgency",
                "description": "gdpr violation privacy regulation breach",
            }
        ]
        categorizer.add_custom_categories(custom_cats)

        result = categorizer.categorize("We have a GDPR violation that requires immediate attention")
        assert result.category == "gdpr_violation"

    def test_pain_point_and_feature_cats_not_added_to_urgent_categoriser(self):
        """Only urgency entries apply here."""
        categorizer = UrgentCategorizer()
        custom_cats = [
            {"name": "slow_perf", "category_type": "pain_point", "description": "slow"},
            {"name": "dark_mode", "category_type": "feature_request", "description": "dark mode"},
        ]
        categorizer.add_custom_categories(custom_cats)
        assert "slow_perf" not in categorizer.CATEGORIES
        assert "dark_mode" not in categorizer.CATEGORIES

    def test_custom_urgency_default_response_time(self):
        """Custom urgency categories should default to '4_hours' response time."""
        categorizer = UrgentCategorizer()
        custom_cats = [
            {
                "name": "regulatory_alert",
                "category_type": "urgency",
                "description": "regulatory compliance risk",
            }
        ]
        categorizer.add_custom_categories(custom_cats)
        assert categorizer.CATEGORIES["regulatory_alert"]["response_time"] == "4_hours"

    def test_empty_custom_categories_list(self):
        """Passing empty list must not modify CATEGORIES."""
        categorizer = UrgentCategorizer()
        original_count = len(categorizer.CATEGORIES)
        categorizer.add_custom_categories([])
        assert len(categorizer.CATEGORIES) == original_count
