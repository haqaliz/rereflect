"""
Tests for the LLM-integrated analysis pipeline.
"""

from unittest.mock import patch, MagicMock

from src.models import FeedbackItem, Organization, CustomCategory


class TestAnalyzeWithLLM:
    """Tests for _analyze_feedback_item with LLM integration."""

    def test_uses_llm_when_org_has_ai_enabled(self, db, ai_enabled_org, unanalyzed_feedback):
        """Should call OpenAI when org has ai_analysis_enabled=True."""
        from src.tasks.analysis import _analyze_feedback_item

        llm_result = {
            "sentiment_label": "negative",
            "sentiment_score": -0.7,
            "is_urgent": True,
            "pain_point_category": "system_crash",
            "pain_point_severity": "critical",
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": "critical_bug",
            "urgent_response_time": "immediate",
            "churn_risk_score": 80,
            "suggested_action": "Investigate and fix the crash.",
            "tags": ["crash", "export"],
            "confidence": 0.9,
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result):
            _analyze_feedback_item(unanalyzed_feedback, db)

        assert unanalyzed_feedback.llm_analyzed is True
        assert unanalyzed_feedback.llm_analysis_pending is False
        assert unanalyzed_feedback.sentiment_label == "negative"
        assert unanalyzed_feedback.churn_risk_score == 80
        assert unanalyzed_feedback.suggested_action == "Investigate and fix the crash."
        assert unanalyzed_feedback.pain_point_category == "system_crash"
        assert unanalyzed_feedback.is_urgent is True

    def test_falls_back_to_keyword_when_llm_fails(self, db, ai_enabled_org, unanalyzed_feedback):
        """Should use keyword analysis when OpenAI returns None."""
        from src.tasks.analysis import _analyze_feedback_item

        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis._apply_keyword_analysis") as mock_keyword:
            _analyze_feedback_item(unanalyzed_feedback, db)

        mock_keyword.assert_called_once_with(unanalyzed_feedback)
        assert unanalyzed_feedback.llm_analysis_pending is True

    def test_skips_llm_when_org_has_ai_disabled(self, db, ai_disabled_org):
        """Should use keyword analysis only when org has ai_analysis_enabled=False."""
        from src.tasks.analysis import _analyze_feedback_item

        feedback = FeedbackItem(
            organization_id=ai_disabled_org.id,
            text="This is broken!",
            source="support",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        with patch("src.tasks.analysis.categorize_feedback") as mock_llm, \
             patch("src.tasks.analysis._apply_keyword_analysis") as mock_keyword:
            _analyze_feedback_item(feedback, db)

        mock_llm.assert_not_called()
        mock_keyword.assert_called_once_with(feedback)

    def test_passes_custom_categories_to_llm(self, db, ai_enabled_org, custom_categories, unanalyzed_feedback):
        """Should pass custom categories to the LLM when they exist."""
        from src.tasks.analysis import _analyze_feedback_item

        llm_result = {
            "sentiment_label": "neutral",
            "sentiment_score": 0.0,
            "is_urgent": False,
            "pain_point_category": "onboarding_issues",
            "pain_point_severity": "moderate",
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": None,
            "urgent_response_time": None,
            "churn_risk_score": 30,
            "suggested_action": "Improve onboarding flow.",
            "tags": ["onboarding"],
            "confidence": 0.85,
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result) as mock_llm:
            _analyze_feedback_item(unanalyzed_feedback, db)

        # Verify custom categories were passed
        call_kwargs = mock_llm.call_args.kwargs
        custom_cats = call_kwargs.get("custom_categories")
        assert custom_cats is not None
        assert len(custom_cats) == 2
        cat_names = [c["name"] for c in custom_cats]
        assert "onboarding_issues" in cat_names
        assert "api_requests" in cat_names

    def test_passes_org_api_key_for_byok(self, db):
        """Should pass org's BYOK API key to categorize_feedback."""
        from src.tasks.analysis import _analyze_feedback_item

        org = Organization(
            name="BYOK Corp", plan="enterprise",
            ai_analysis_enabled=True, openai_api_key="sk-byok-key"
        )
        db.add(org)
        db.commit()

        feedback = FeedbackItem(
            organization_id=org.id,
            text="Great product!",
            source="email",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        llm_result = {
            "sentiment_label": "positive",
            "sentiment_score": 0.8,
            "is_urgent": False,
            "pain_point_category": None,
            "pain_point_severity": None,
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": None,
            "urgent_response_time": None,
            "churn_risk_score": 5,
            "suggested_action": "Acknowledge positive feedback.",
            "tags": ["positive"],
            "confidence": 0.95,
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result) as mock_llm:
            _analyze_feedback_item(feedback, db)

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["org_api_key"] == "sk-byok-key"


class TestApplyLLMResult:
    """Tests for _apply_llm_result."""

    def test_sets_all_fields_from_llm_result(self, db, ai_enabled_org):
        """Should set all feedback fields from LLM result."""
        from src.tasks.analysis import _apply_llm_result

        feedback = FeedbackItem(
            organization_id=ai_enabled_org.id,
            text="This is terrible, the app crashes constantly!",
            source="support",
        )
        db.add(feedback)
        db.commit()

        result = {
            "sentiment_label": "negative",
            "sentiment_score": -0.9,
            "is_urgent": True,
            "pain_point_category": "system_crash",
            "pain_point_severity": "critical",
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": "critical_bug",
            "urgent_response_time": "immediate",
            "churn_risk_score": 90,
            "suggested_action": "Fix immediately.",
            "tags": ["crash", "critical"],
            "confidence": 0.95,
        }

        _apply_llm_result(feedback, result)

        assert feedback.sentiment_label == "negative"
        assert feedback.sentiment_score == -0.9
        assert feedback.is_urgent is True
        assert feedback.pain_point_category == "system_crash"
        assert feedback.pain_point_severity == "critical"
        assert feedback.urgent_category == "critical_bug"
        assert feedback.churn_risk_score == 90
        assert feedback.suggested_action == "Fix immediately."
        assert feedback.llm_analyzed is True
        assert feedback.llm_analysis_pending is False
        assert feedback.categorization_confidence == 0.95

    def test_handles_null_optional_fields(self, db, ai_enabled_org):
        """Should handle null values for optional category fields."""
        from src.tasks.analysis import _apply_llm_result

        feedback = FeedbackItem(
            organization_id=ai_enabled_org.id,
            text="Everything looks good!",
            source="email",
        )
        db.add(feedback)
        db.commit()

        result = {
            "sentiment_label": "positive",
            "sentiment_score": 0.8,
            "is_urgent": False,
            "pain_point_category": None,
            "pain_point_severity": None,
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": None,
            "urgent_response_time": None,
            "churn_risk_score": 5,
            "suggested_action": "Send thank you note.",
            "tags": ["positive"],
            "confidence": 0.9,
        }

        _apply_llm_result(feedback, result)

        assert feedback.pain_point_category is None
        assert feedback.feature_request_category is None
        assert feedback.urgent_category is None
        assert feedback.llm_analyzed is True


class TestRetryLLMAnalysis:
    """Tests for retry_llm_analysis task."""

    def test_retries_pending_items(self, db, ai_enabled_org):
        """Should retry LLM analysis for items with llm_analysis_pending=True."""
        from src.tasks.analysis import retry_llm_analysis

        feedback = FeedbackItem(
            organization_id=ai_enabled_org.id,
            text="App crashes on export",
            source="support",
            sentiment_label="negative",
            sentiment_score=-0.5,
            llm_analysis_pending=True,
            llm_analyzed=False,
        )
        db.add(feedback)
        db.commit()

        llm_result = {
            "sentiment_label": "negative",
            "sentiment_score": -0.8,
            "is_urgent": True,
            "pain_point_category": "system_crash",
            "pain_point_severity": "critical",
            "feature_request_category": None,
            "feature_request_priority": None,
            "urgent_category": "critical_bug",
            "urgent_response_time": "immediate",
            "churn_risk_score": 75,
            "suggested_action": "Fix crash bug.",
            "tags": ["crash"],
            "confidence": 0.9,
        }

        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis = MagicMock()
        mock_redis.lock.return_value = mock_lock

        with patch("src.tasks.analysis.get_db_session") as mock_db_ctx, \
             patch("src.tasks.analysis.categorize_feedback", return_value=llm_result), \
             patch("src.tasks.analysis._get_redis", return_value=mock_redis):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = retry_llm_analysis()

        assert result["retried"] == 1
        assert result["failed"] == 0
        assert feedback.llm_analyzed is True
        assert feedback.llm_analysis_pending is False

    def test_returns_idle_when_no_pending_items(self, db):
        """Should return idle status when no items need retry."""
        from src.tasks.analysis import retry_llm_analysis

        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis = MagicMock()
        mock_redis.lock.return_value = mock_lock

        with patch("src.tasks.analysis.get_db_session") as mock_db_ctx, \
             patch("src.tasks.analysis._get_redis", return_value=mock_redis):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = retry_llm_analysis()

        assert result["status"] == "idle"
        assert result["retried"] == 0

    def test_counts_failed_retries(self, db, ai_enabled_org):
        """Should count items that still fail LLM analysis."""
        from src.tasks.analysis import retry_llm_analysis

        feedback = FeedbackItem(
            organization_id=ai_enabled_org.id,
            text="Something broken",
            source="support",
            sentiment_label="negative",
            sentiment_score=-0.5,
            llm_analysis_pending=True,
            llm_analyzed=False,
        )
        db.add(feedback)
        db.commit()

        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis = MagicMock()
        mock_redis.lock.return_value = mock_lock

        with patch("src.tasks.analysis.get_db_session") as mock_db_ctx, \
             patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis._get_redis", return_value=mock_redis):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = retry_llm_analysis()

        assert result["retried"] == 0
        assert result["failed"] == 1
