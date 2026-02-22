"""
Tests for _store_analysis_result — stores LLM analysis on CustomerHealth records.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestStoreAnalysisResult:
    """Tests for _store_analysis_result in insights.py."""

    def _make_customer(self):
        """Build a mock CustomerHealth record."""
        customer = MagicMock()
        customer.id = 1
        customer.customer_email = "test@example.com"
        customer.health_score = 30
        customer.llm_analysis_data = None
        customer.llm_raw_response = None
        customer.llm_analyzed_at = None
        customer.llm_analysis = None
        customer.llm_provider = None
        customer.llm_model = None
        return customer

    def _make_result(self, provider="anthropic", model="claude-haiku-4-5"):
        """Build a mock analysis result dict as returned by generate_customer_analysis."""
        return {
            "analysis": "Customer shows signs of churn risk due to repeated complaints.",
            "recommended_actions": ["Schedule a call", "Offer discount"],
            "risk_drivers": ["Negative sentiment", "Repeated issues"],
            "estimated_urgency": "this_week",
            "analysis_type": "churn_risk",
            "_raw_response": {
                "provider": provider,
                "model": model,
                "raw_content": '{"analysis": "..."}',
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        }

    @patch("src.tasks.insights.dispatch_alert")
    def test_stores_llm_provider_and_model_from_raw_response(self, mock_dispatch):
        """_store_analysis_result should set llm_provider and llm_model on CustomerHealth."""
        from src.tasks.insights import _store_analysis_result

        db = MagicMock()
        customer = self._make_customer()
        result = self._make_result(provider="anthropic", model="claude-haiku-4-5")

        _store_analysis_result(db, customer, result, org_id=1)

        assert customer.llm_provider == "anthropic"
        assert customer.llm_model == "claude-haiku-4-5"

    @patch("src.tasks.insights.dispatch_alert")
    def test_stores_openai_provider_and_model(self, mock_dispatch):
        """Should work with OpenAI provider/model."""
        from src.tasks.insights import _store_analysis_result

        db = MagicMock()
        customer = self._make_customer()
        result = self._make_result(provider="openai", model="gpt-4o-mini")

        _store_analysis_result(db, customer, result, org_id=1)

        assert customer.llm_provider == "openai"
        assert customer.llm_model == "gpt-4o-mini"

    @patch("src.tasks.insights.dispatch_alert")
    def test_handles_missing_raw_response_gracefully(self, mock_dispatch):
        """Should not crash when _raw_response is missing."""
        from src.tasks.insights import _store_analysis_result

        db = MagicMock()
        customer = self._make_customer()
        result = {
            "analysis": "Some analysis",
            "recommended_actions": [],
            "risk_drivers": [],
            "estimated_urgency": "this_month",
            "analysis_type": "churn_risk",
        }

        _store_analysis_result(db, customer, result, org_id=1)

        assert customer.llm_provider is None
        assert customer.llm_model is None

    @patch("src.tasks.insights.dispatch_alert")
    def test_stores_structured_analysis_data(self, mock_dispatch):
        """Should store structured analysis data on the customer."""
        from src.tasks.insights import _store_analysis_result

        db = MagicMock()
        customer = self._make_customer()
        result = self._make_result()

        _store_analysis_result(db, customer, result, org_id=1)

        assert customer.llm_analysis_data["analysis"] == "Customer shows signs of churn risk due to repeated complaints."
        assert customer.llm_analysis_data["analysis_type"] == "churn_risk"
        assert len(customer.llm_analysis_data["recommended_actions"]) == 2

    @patch("src.tasks.insights.dispatch_alert")
    def test_stores_legacy_pipe_separated_text(self, mock_dispatch):
        """Should maintain legacy llm_analysis pipe-separated format."""
        from src.tasks.insights import _store_analysis_result

        db = MagicMock()
        customer = self._make_customer()
        result = self._make_result()

        _store_analysis_result(db, customer, result, org_id=1)

        assert "Customer shows signs of churn risk" in customer.llm_analysis
        assert "Actions:" in customer.llm_analysis
        assert "Urgency:" in customer.llm_analysis
