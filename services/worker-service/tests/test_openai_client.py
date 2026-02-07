"""
Tests for the OpenAI integration client.
"""

import json
from unittest.mock import patch, MagicMock

from src.openai_client import categorize_feedback, _get_client


class TestGetClient:
    """Tests for _get_client helper."""

    def test_returns_none_when_no_api_key(self):
        """Should return None when no API key is configured."""
        with patch("src.openai_client.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            client = _get_client(org_api_key=None)
            assert client is None

    def test_uses_org_key_over_system_key(self):
        """Should prefer org BYOK key over system key."""
        with patch("src.openai_client.OpenAI") as mock_openai:
            _get_client(org_api_key="sk-org-key")
            mock_openai.assert_called_once_with(api_key="sk-org-key")

    def test_uses_system_key_when_no_org_key(self):
        """Should use system key when no org key provided."""
        with patch("src.openai_client.settings") as mock_settings, \
             patch("src.openai_client.OpenAI") as mock_openai:
            mock_settings.openai_api_key = "sk-system-key"
            _get_client(org_api_key=None)
            mock_openai.assert_called_once_with(api_key="sk-system-key")


class TestCategorizeFeedback:
    """Tests for categorize_feedback function."""

    def _mock_openai_response(self, content: dict):
        """Helper to create a mock OpenAI response."""
        mock_message = MagicMock()
        mock_message.content = json.dumps(content)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    def test_returns_none_when_no_api_key(self):
        """Should return None when no API key is available."""
        with patch("src.openai_client.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = categorize_feedback("Some feedback text")
            assert result is None

    def test_returns_parsed_json_on_success(self):
        """Should return parsed JSON from OpenAI response."""
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

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_openai_response(llm_response)

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("App crashes when exporting data")

        assert result is not None
        assert result["sentiment_label"] == "negative"
        assert result["churn_risk_score"] == 75
        assert result["confidence"] == 0.92
        assert len(result["tags"]) == 3

    def test_clamps_churn_risk_score(self):
        """Should clamp churn_risk_score to 0-100 range."""
        llm_response = {
            "churn_risk_score": 150,
            "confidence": 0.5,
            "tags": [],
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_openai_response(llm_response)

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("Test feedback")

        assert result["churn_risk_score"] == 100

    def test_clamps_negative_churn_risk_score(self):
        """Should clamp negative churn_risk_score to 0."""
        llm_response = {
            "churn_risk_score": -10,
            "confidence": 0.5,
            "tags": [],
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_openai_response(llm_response)

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("Test feedback")

        assert result["churn_risk_score"] == 0

    def test_truncates_tags_to_5(self):
        """Should truncate tags to maximum 5."""
        llm_response = {
            "churn_risk_score": 50,
            "confidence": 0.8,
            "tags": ["a", "b", "c", "d", "e", "f", "g"],
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_openai_response(llm_response)

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("Test")

        assert len(result["tags"]) == 5

    def test_handles_api_error_gracefully(self):
        """Should return None on OpenAI API error."""
        from openai import APIError

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIError(
            message="Rate limit exceeded",
            request=MagicMock(),
            body=None,
        )

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("Test feedback")

        assert result is None

    def test_handles_invalid_json_response(self):
        """Should return None when OpenAI returns invalid JSON."""
        mock_message = MagicMock()
        mock_message.content = "This is not JSON"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("Test")

        assert result is None

    def test_includes_custom_categories_in_prompt(self):
        """Should include custom categories in the prompt when provided."""
        llm_response = {
            "churn_risk_score": 30,
            "confidence": 0.7,
            "tags": [],
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_openai_response(llm_response)

        custom_cats = [
            {"name": "onboarding_issues", "category_type": "pain_point"},
            {"name": "api_requests", "category_type": "feature_request"},
        ]

        with patch("src.openai_client._get_client", return_value=mock_client):
            categorize_feedback("Test", custom_categories=custom_cats)

        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "onboarding_issues" in prompt
        assert "api_requests" in prompt

    def test_handles_empty_content_response(self):
        """Should return None when OpenAI returns empty content."""
        mock_message = MagicMock()
        mock_message.content = None
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.openai_client._get_client", return_value=mock_client):
            result = categorize_feedback("Test")

        assert result is None
