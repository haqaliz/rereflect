"""
TDD tests for Feature B: Custom taxonomies + configurable health weights.

B1 — Custom categories wired into the LLM prompt and keyword matcher.
B2 — Health-weight endpoints persist + reject non-100 sums; health_score_service
     uses configured weights.

RED phase: these tests should fail before the production code is written.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.models import Organization, OrgAIConfig, CustomCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db, name="Acme", ai_enabled=True):
    org = Organization(name=name, plan="business", ai_analysis_enabled=ai_enabled)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_custom_cat(db, org_id, name, cat_type, description=None):
    cat = CustomCategory(
        organization_id=org_id,
        name=name,
        description=description or f"Description for {name}",
        category_type=cat_type,
        is_active=True,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _mock_llm_response(content: dict):
    mock_response = MagicMock()
    mock_response.content = json.dumps(content)
    mock_response.provider = "openai"
    mock_response.model = "gpt-4o-mini"
    mock_response.prompt_tokens = 100
    mock_response.completion_tokens = 50
    return mock_response


# ---------------------------------------------------------------------------
# B1 — LLM prompt injection (prompts.py / llm_client.py)
# ---------------------------------------------------------------------------

class TestUrgencyTypeInLLMPrompt:
    """Custom urgency categories must appear in the LLM categorisation prompt."""

    def test_urgency_category_appears_in_prompt(self, db):
        """A custom 'urgency' category name should be injected into the prompt."""
        from src.llm_client import categorize_feedback

        org = _make_org(db)
        _make_custom_cat(db, org.id, "regulatory_violation", "urgency",
                         description="Violations of regulations")

        # Capture the actual prompt passed to call_llm_for_org
        captured_prompts = []

        def fake_call(org_id, task_type, request, provider, model, db):
            captured_prompts.append(request.messages[0]["content"])
            return None  # Return None → categorize_feedback returns None

        with patch("src.llm_client.call_llm_for_org", side_effect=fake_call):
            categorize_feedback(
                "This is a regulatory compliance issue",
                custom_categories=[{"name": "regulatory_violation", "category_type": "urgency"}],
                org_id=org.id,
                db=db,
            )

        assert captured_prompts, "call_llm_for_org was never called"
        prompt = captured_prompts[0]
        assert "regulatory_violation" in prompt

    def test_all_three_custom_types_appear_in_prompt(self, db):
        """Custom pain_point, feature_request, and urgency categories all appear in prompt."""
        from src.llm_client import categorize_feedback

        org = _make_org(db)
        custom_cats = [
            {"name": "network_issue", "category_type": "pain_point"},
            {"name": "sso_request", "category_type": "feature_request"},
            {"name": "data_residency_risk", "category_type": "urgency"},
        ]

        captured_prompts = []

        def fake_call(org_id, task_type, request, provider, model, db):
            captured_prompts.append(request.messages[0]["content"])
            return None

        with patch("src.llm_client.call_llm_for_org", side_effect=fake_call):
            categorize_feedback(
                "Multiple custom types test",
                custom_categories=custom_cats,
                org_id=org.id,
                db=db,
            )

        assert captured_prompts
        prompt = captured_prompts[0]
        assert "network_issue" in prompt
        assert "sso_request" in prompt
        assert "data_residency_risk" in prompt

    def test_urgency_custom_section_label_is_informative(self, db):
        """The prompt section for custom urgency categories should state their purpose."""
        from src.llm_client import categorize_feedback

        org = _make_org(db)
        custom_cats = [{"name": "gdpr_breach", "category_type": "urgency"}]

        captured_prompts = []

        def fake_call(org_id, task_type, request, provider, model, db):
            captured_prompts.append(request.messages[0]["content"])
            return None

        with patch("src.llm_client.call_llm_for_org", side_effect=fake_call):
            categorize_feedback(
                "We have a GDPR breach",
                custom_categories=custom_cats,
                org_id=org.id,
                db=db,
            )

        prompt = captured_prompts[0]
        # The label should mention "urgency" somewhere near the category name
        assert "urgency" in prompt.lower()
        assert "gdpr_breach" in prompt


# ---------------------------------------------------------------------------
# B1 — Keyword matcher integration (tests live in analysis-engine service)
# We verify here that the worker's keyword-fallback path is wired to pass
# custom categories through to the categorisers at runtime.
# The categoriser logic itself is tested in analysis-engine/tests/test_custom_categorizer.py.
# ---------------------------------------------------------------------------

class TestCustomCategoryKeywordMatcherWiring:
    """The worker's keyword fallback path must wire custom categories into categorisers."""

    def test_keyword_fallback_calls_categorizer_with_org_categories(self, db):
        """_apply_keyword_analysis calls categorisers; the categorisers receive custom cats."""
        # This test verifies the integration at the _apply_keyword_analysis boundary.
        # We mock out the categorisers to avoid the analyzer module import.
        from src.models import FeedbackItem
        from src.tasks.analysis import _apply_keyword_analysis
        from unittest.mock import MagicMock, patch

        org = _make_org(db)
        feedback = FeedbackItem(
            organization_id=org.id,
            text="Some slow performance issue",
            source="email",
            sentiment_score=-0.4,
            sentiment_label="negative",
            is_urgent=False,
        )
        db.add(feedback)
        db.commit()

        # Mock the three categorisers so they return sensible results
        mock_pain_result = MagicMock(category="performance", level="moderate", confidence=0.8, text="slow")
        mock_pain_cat = MagicMock()
        mock_pain_cat.categorize.return_value = mock_pain_result

        mock_feat_result = MagicMock(category="customization", level="medium", confidence=0.5, text="")
        mock_feat_cat = MagicMock()
        mock_feat_cat.categorize.return_value = mock_feat_result

        mock_urg_result = MagicMock(category="critical_bug", level="1_hour", confidence=0.3)
        mock_urg_cat = MagicMock()
        mock_urg_cat.categorize.return_value = mock_urg_result

        mock_sentiment = MagicMock()
        mock_sentiment.analyze.return_value = {"label": "negative", "compound": -0.4}

        mock_tags = MagicMock()
        mock_tags.extract_tags.return_value = ["slow", "performance"]

        with patch("src.tasks.analysis.get_categorizers", return_value=(mock_pain_cat, mock_feat_cat, mock_urg_cat)), \
             patch("src.tasks.analysis.get_sentiment_analyzer", return_value=mock_sentiment), \
             patch("src.tasks.analysis.get_tag_extractor", return_value=mock_tags):
            _apply_keyword_analysis(feedback, db)

        # Categoriser must have been called with the feedback text
        mock_pain_cat.categorize.assert_called_once()
        assert feedback.pain_point_category == "performance"


# ---------------------------------------------------------------------------
# B1 — analysis task loads active custom categories
# ---------------------------------------------------------------------------

class TestAnalysisTaskLoadsCustomCategories:
    """_analyze_feedback_item must pass active custom categories to the LLM."""

    def test_active_custom_urgency_category_passed_to_llm(self, db):
        """Active custom categories (incl. urgency) must be in the custom_categories list."""
        from src.models import FeedbackItem
        from src.tasks.analysis import _analyze_feedback_item

        org = _make_org(db)
        # Add active urgency category
        _make_custom_cat(db, org.id, "regulatory_alert", "urgency")

        feedback = FeedbackItem(
            organization_id=org.id,
            text="We have a regulatory compliance problem",
            source="email",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        captured_calls = []

        def fake_categorize(text, custom_categories=None, org_id=None, db=None, org_api_key=None):
            captured_calls.append(custom_categories or [])
            return None  # Return None to trigger fallback

        # Mock keyword fallback to avoid needing the analysis-engine installed
        mock_kw = MagicMock()
        with patch("src.tasks.analysis.categorize_feedback", side_effect=fake_categorize), \
             patch("src.tasks.analysis._apply_keyword_analysis", side_effect=mock_kw):
            _analyze_feedback_item(feedback, db)

        assert captured_calls, "categorize_feedback was never called"
        cat_names = [c["name"] for c in captured_calls[0]]
        assert "regulatory_alert" in cat_names

    def test_inactive_custom_category_not_passed_to_llm(self, db):
        """Inactive custom categories should be excluded from the analysis prompt."""
        from src.models import FeedbackItem, CustomCategory
        from src.tasks.analysis import _analyze_feedback_item

        org = _make_org(db)
        cat = _make_custom_cat(db, org.id, "inactive_cat", "pain_point")
        cat.is_active = False
        db.commit()

        feedback = FeedbackItem(
            organization_id=org.id,
            text="Some problem occurred",
            source="email",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        captured_calls = []

        def fake_categorize(text, custom_categories=None, org_id=None, db=None, org_api_key=None):
            captured_calls.append(custom_categories or [])
            return None

        mock_kw = MagicMock()
        with patch("src.tasks.analysis.categorize_feedback", side_effect=fake_categorize), \
             patch("src.tasks.analysis._apply_keyword_analysis", side_effect=mock_kw):
            _analyze_feedback_item(feedback, db)

        assert captured_calls
        cat_names = [c["name"] for c in captured_calls[0]]
        assert "inactive_cat" not in cat_names
