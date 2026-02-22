"""
Tests for the provider-agnostic LLM client (llm_client.py).
"""

import json
from unittest.mock import patch, MagicMock

from src.models import Organization, OrgAIConfig


class TestCategorizeFeedback:
    """Tests for categorize_feedback function."""

    def test_returns_none_when_no_org_id(self):
        """Should return None when org_id is not provided."""
        from src.llm_client import categorize_feedback

        result = categorize_feedback("Some feedback text", org_id=None, db=None)
        assert result is None

    def test_returns_none_when_no_db(self):
        """Should return None when db is not provided."""
        from src.llm_client import categorize_feedback

        result = categorize_feedback("Some feedback text", org_id=1, db=None)
        assert result is None

    def test_returns_parsed_json_on_success(self, db, ai_enabled_org):
        """Should return parsed result from LLM response."""
        from src.llm_client import categorize_feedback

        llm_response = {
            "sentiment_label": "negative",
            "sentiment_score": -0.7,
            "is_urgent": True,
            "pain_point_category": "system_crash",
            "pain_point_severity": "critical",
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": "critical_bug",
            "urgent_response_time": "immediate",
            "churn_risk_score": 75,
            "suggested_action": "Investigate crash logs and prioritize fix.",
            "tags": ["bug", "crash", "export"],
            "confidence": 0.92,
        }

        mock_response = MagicMock()
        mock_response.content = json.dumps(llm_response)
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 50

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = categorize_feedback(
                "App crashes when exporting data",
                org_id=ai_enabled_org.id,
                db=db,
            )

        assert result is not None
        assert result["sentiment_label"] == "negative"
        assert result["churn_risk_score"] == 75
        assert result["confidence"] == 0.92
        assert len(result["tags"]) == 3

    def test_clamps_churn_risk_score_above_100(self, db, ai_enabled_org):
        """Should clamp churn_risk_score to max 100."""
        from src.llm_client import categorize_feedback

        mock_response = MagicMock()
        mock_response.content = json.dumps({"churn_risk_score": 150, "confidence": 0.5, "tags": []})
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 50
        mock_response.completion_tokens = 20

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = categorize_feedback("Test feedback", org_id=ai_enabled_org.id, db=db)

        assert result["churn_risk_score"] == 100

    def test_clamps_churn_risk_score_below_0(self, db, ai_enabled_org):
        """Should clamp churn_risk_score to min 0."""
        from src.llm_client import categorize_feedback

        mock_response = MagicMock()
        mock_response.content = json.dumps({"churn_risk_score": -10, "confidence": 0.5, "tags": []})
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 50
        mock_response.completion_tokens = 20

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = categorize_feedback("Test feedback", org_id=ai_enabled_org.id, db=db)

        assert result["churn_risk_score"] == 0

    def test_truncates_tags_to_5(self, db, ai_enabled_org):
        """Should truncate tags to maximum 5."""
        from src.llm_client import categorize_feedback

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "churn_risk_score": 50,
            "confidence": 0.8,
            "tags": ["a", "b", "c", "d", "e", "f", "g"],
        })
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 50
        mock_response.completion_tokens = 20

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = categorize_feedback("Test", org_id=ai_enabled_org.id, db=db)

        assert len(result["tags"]) == 5

    def test_returns_none_when_llm_returns_none(self, db, ai_enabled_org):
        """Should return None when LLM factory returns None."""
        from src.llm_client import categorize_feedback

        with patch("src.llm_client.call_llm_for_org", return_value=None):
            result = categorize_feedback("Test feedback", org_id=ai_enabled_org.id, db=db)

        assert result is None

    def test_returns_none_on_invalid_json(self, db, ai_enabled_org):
        """Should return None when LLM returns invalid JSON."""
        from src.llm_client import categorize_feedback

        mock_response = MagicMock()
        mock_response.content = "This is not JSON"
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = categorize_feedback("Test", org_id=ai_enabled_org.id, db=db)

        assert result is None

    def test_includes_custom_categories_in_prompt(self, db, ai_enabled_org):
        """Should include custom categories when provided."""
        from src.llm_client import categorize_feedback

        mock_response = MagicMock()
        mock_response.content = json.dumps({"churn_risk_score": 30, "confidence": 0.7, "tags": []})
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 80
        mock_response.completion_tokens = 20

        custom_cats = [
            {"name": "onboarding_issues", "category_type": "pain_point"},
            {"name": "api_requests", "category_type": "feature_request"},
        ]

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response) as mock_llm:
            categorize_feedback("Test", custom_categories=custom_cats, org_id=ai_enabled_org.id, db=db)

        call_kwargs = mock_llm.call_args.kwargs
        prompt_content = call_kwargs["request"].messages[0]["content"]
        assert "onboarding_issues" in prompt_content
        assert "api_requests" in prompt_content

    def test_stores_llm_provider_and_model_in_result(self, db, ai_enabled_org):
        """Should include _llm_provider and _llm_model in the result."""
        from src.llm_client import categorize_feedback

        mock_response = MagicMock()
        mock_response.content = json.dumps({"churn_risk_score": 20, "confidence": 0.8, "tags": []})
        mock_response.provider = "anthropic"
        mock_response.model = "claude-3-5-haiku-20241022"
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 30

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = categorize_feedback("Test", org_id=ai_enabled_org.id, db=db)

        assert result["_llm_provider"] == "anthropic"
        assert result["_llm_model"] == "claude-3-5-haiku-20241022"


class TestGenerateInsightsLLMClient:
    """Tests for generate_insights function."""

    def test_returns_none_when_no_org_id(self):
        """Should return None when org_id is not provided."""
        from src.llm_client import generate_insights

        result = generate_insights(["feedback 1", "feedback 2"], org_id=None, db=None)
        assert result is None

    def test_returns_validated_insights(self, db, ai_enabled_org):
        """Should parse and validate insights from LLM response."""
        from src.llm_client import generate_insights

        insights_data = {
            "insights": [
                {"title": "Login issues", "description": "Many login complaints", "category": "pain_point", "priority": "high"},
                {"title": "Dark mode", "description": "Users want dark mode", "category": "feature_request", "priority": "medium"},
            ]
        }

        mock_response = MagicMock()
        mock_response.content = json.dumps(insights_data)
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 200
        mock_response.completion_tokens = 100

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = generate_insights(
                ["complaint 1", "complaint 2"],
                org_id=ai_enabled_org.id,
                db=db,
            )

        assert result is not None
        assert len(result) == 2
        assert result[0]["title"] == "Login issues"
        assert result[0]["category"] == "pain_point"
        assert result[1]["priority"] == "medium"

    def test_limits_to_5_insights(self, db, ai_enabled_org):
        """Should cap at 5 insights even if LLM returns more."""
        from src.llm_client import generate_insights

        insights_list = [
            {"title": f"Insight {i}", "description": f"Desc {i}", "category": "opportunity", "priority": "low"}
            for i in range(8)
        ]

        mock_response = MagicMock()
        mock_response.content = json.dumps({"insights": insights_list})
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 200
        mock_response.completion_tokens = 150

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = generate_insights(["text"] * 10, org_id=ai_enabled_org.id, db=db)

        assert result is not None
        assert len(result) == 5

    def test_returns_none_when_llm_returns_none(self, db, ai_enabled_org):
        """Should return None when LLM factory returns None."""
        from src.llm_client import generate_insights

        with patch("src.llm_client.call_llm_for_org", return_value=None):
            result = generate_insights(["text"], org_id=ai_enabled_org.id, db=db)

        assert result is None

    def test_returns_none_on_invalid_json(self, db, ai_enabled_org):
        """Should return None when LLM returns invalid JSON."""
        from src.llm_client import generate_insights

        mock_response = MagicMock()
        mock_response.content = "not json"
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = generate_insights(["text"], org_id=ai_enabled_org.id, db=db)

        assert result is None

    def test_skips_invalid_insight_items(self, db, ai_enabled_org):
        """Should skip insights missing required fields."""
        from src.llm_client import generate_insights

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "insights": [
                {"title": "Valid", "description": "Has both fields", "category": "opportunity", "priority": "low"},
                {"title_only": "Missing description"},
                {"description_only": "Missing title"},
            ]
        })
        mock_response.provider = "openai"
        mock_response.model = "gpt-4o-mini"
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 80

        with patch("src.llm_client.call_llm_for_org", return_value=mock_response):
            result = generate_insights(["text"], org_id=ai_enabled_org.id, db=db)

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Valid"
