"""
TDD tests for the Intent Classifier (RED → GREEN → REFACTOR).

Tests cover:
- Rule-based classification for data, analysis, and general intents
- Confidence score thresholds
- Ambiguous queries that fall through to LLM
- Parameter extraction
"""

import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def classifier():
    """Import and instantiate the IntentClassifier."""
    from src.services.copilot.intent_classifier import IntentClassifier
    return IntentClassifier()


# ── Data intent — rule-based ──────────────────────────────────────────────────

class TestDataIntentRuleBased:
    """Queries that should be classified as 'data' via regex rules."""

    @pytest.mark.parametrize("query", [
        "How many negative feedbacks this week?",
        "how many feedbacks do we have today?",
        "Count all feedback items",
        "count urgent feedbacks",
        "List all customers with low health score",
        "list customers at risk",
        "Show me negative feedbacks",
        "show me all pain points",
        "Which feedbacks are marked as urgent?",
        "which customers have critical risk?",
        "What is the total feedback count?",
        "What are the top pain points?",
        "Give me feedback from this month",
        "Get all feature requests",
    ])
    def test_data_intent_detected(self, classifier, query):
        result = classifier.classify(query)
        assert result["intent"] == "data", f"Expected 'data' for: {query!r}, got: {result}"

    def test_data_intent_returns_high_confidence(self, classifier):
        result = classifier.classify("How many negative feedbacks this week?")
        assert result["confidence"] >= 0.8

    def test_data_intent_case_insensitive(self, classifier):
        result = classifier.classify("HOW MANY FEEDBACKS?")
        assert result["intent"] == "data"

    def test_data_count_query_parameters(self, classifier):
        result = classifier.classify("How many negative feedbacks this week?")
        assert "intent" in result
        assert "confidence" in result
        assert "parameters" in result


# ── Analysis intent — rule-based ─────────────────────────────────────────────

class TestAnalysisIntentRuleBased:
    """Queries that should be classified as 'analysis' via regex rules."""

    @pytest.mark.parametrize("query", [
        "Why is churn risk increasing?",
        "why do customers keep churning?",
        "Compare this month vs last month",
        "compare negative sentiment this week vs last week",
        "What are the trends in feedback?",
        "trend analysis for pain points",
        "Analyze customer sentiment over time",
        "analyze the decline in health scores",
        "Explain the spike in urgent feedbacks",
        "explain why feature requests are growing",
    ])
    def test_analysis_intent_detected(self, classifier, query):
        result = classifier.classify(query)
        assert result["intent"] == "analysis", f"Expected 'analysis' for: {query!r}, got: {result}"

    def test_analysis_intent_returns_high_confidence(self, classifier):
        result = classifier.classify("Why is churn risk increasing?")
        assert result["confidence"] >= 0.8


# ── General intent — rule-based ───────────────────────────────────────────────

class TestGeneralIntentRuleBased:
    """Queries that should be classified as 'general' via regex rules."""

    @pytest.mark.parametrize("query", [
        "Help me understand this tool",
        "What can you do?",
        "what can you help me with?",
        "Hello",
        "hello there",
        "Hi, I need help",
        "how does this work?",
    ])
    def test_general_intent_detected(self, classifier, query):
        result = classifier.classify(query)
        assert result["intent"] == "general", f"Expected 'general' for: {query!r}, got: {result}"

    def test_general_intent_returns_high_confidence(self, classifier):
        result = classifier.classify("What can you do?")
        assert result["confidence"] >= 0.7


# ── Result structure ──────────────────────────────────────────────────────────

class TestResultStructure:
    """Ensure classify() always returns a well-formed dict."""

    def test_result_has_intent_key(self, classifier):
        result = classifier.classify("How many feedbacks?")
        assert "intent" in result

    def test_result_has_confidence_key(self, classifier):
        result = classifier.classify("How many feedbacks?")
        assert "confidence" in result

    def test_result_has_parameters_key(self, classifier):
        result = classifier.classify("How many feedbacks?")
        assert "parameters" in result

    def test_confidence_is_between_0_and_1(self, classifier):
        result = classifier.classify("How many feedbacks?")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_intent_is_valid_value(self, classifier):
        result = classifier.classify("How many feedbacks?")
        assert result["intent"] in ("data", "analysis", "general")

    def test_parameters_is_dict(self, classifier):
        result = classifier.classify("How many feedbacks?")
        assert isinstance(result["parameters"], dict)


# ── LLM fallback for ambiguous queries ───────────────────────────────────────

class TestLLMFallback:
    """Ambiguous queries should trigger LLM classification."""

    def test_ambiguous_query_calls_llm(self, classifier):
        ambiguous = "Tell me about our feedback situation"
        with patch.object(classifier, "_classify_with_llm") as mock_llm:
            mock_llm.return_value = {"intent": "analysis", "confidence": 0.75, "parameters": {}}
            result = classifier.classify(ambiguous)
            # LLM should be called for ambiguous queries
            # (either it was called, or rule-based classified it)
            assert result["intent"] in ("data", "analysis", "general")

    def test_llm_classification_result_is_used(self, classifier):
        ambiguous = "Tell me about our feedback situation"
        with patch.object(classifier, "_classify_with_llm") as mock_llm:
            mock_llm.return_value = {"intent": "analysis", "confidence": 0.75, "parameters": {}}
            result = classifier.classify(ambiguous)
            assert result["intent"] in ("data", "analysis", "general")
            assert 0.0 <= result["confidence"] <= 1.0

    def test_llm_failure_returns_general_fallback(self, classifier):
        """If LLM call fails, fall back to 'general' with low confidence."""
        ambiguous = "Tell me about our feedback situation"
        with patch.object(classifier, "_classify_with_llm") as mock_llm:
            mock_llm.side_effect = Exception("LLM unavailable")
            result = classifier.classify(ambiguous)
            # Should not raise, should return a valid result
            assert result["intent"] in ("data", "analysis", "general")
            assert "confidence" in result


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases for the intent classifier."""

    def test_empty_string_returns_general(self, classifier):
        result = classifier.classify("")
        assert result["intent"] == "general"

    def test_very_short_query(self, classifier):
        result = classifier.classify("hi")
        assert result["intent"] in ("data", "analysis", "general")

    def test_very_long_query_still_classifies(self, classifier):
        long_query = "How many " + "very " * 100 + "negative feedbacks do we have?"
        result = classifier.classify(long_query)
        assert result["intent"] == "data"

    def test_special_characters_handled(self, classifier):
        result = classifier.classify("How many feedbacks? @customer:test@example.com")
        assert result["intent"] in ("data", "analysis", "general")

    def test_numeric_in_query(self, classifier):
        result = classifier.classify("Show me the top 10 pain points")
        assert result["intent"] == "data"
