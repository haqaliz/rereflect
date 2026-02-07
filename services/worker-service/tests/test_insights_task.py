"""
Tests for weekly insights generation Celery task and OpenAI generate_insights.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.models import Organization, User, FeedbackItem, WeeklyInsight


class TestGenerateInsightsOpenAI:
    """Tests for the generate_insights OpenAI function."""

    @patch("src.openai_client._get_client")
    def test_returns_none_when_no_api_key(self, mock_get_client):
        """Should return None when no API key is configured."""
        mock_get_client.return_value = None
        from src.openai_client import generate_insights
        result = generate_insights(["feedback 1", "feedback 2"])
        assert result is None

    @patch("src.openai_client._get_client")
    def test_returns_validated_insights(self, mock_get_client):
        """Should parse and validate insights from GPT response."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "insights": [
                {"title": "Login issues", "description": "Many login complaints", "category": "pain_point", "priority": "high"},
                {"title": "Dark mode", "description": "Users want dark mode", "category": "feature_request", "priority": "medium"}
            ]
        }'''
        mock_client.chat.completions.create.return_value = mock_response

        from src.openai_client import generate_insights
        result = generate_insights(["complaint 1", "complaint 2"])

        assert result is not None
        assert len(result) == 2
        assert result[0]["title"] == "Login issues"
        assert result[0]["category"] == "pain_point"
        assert result[1]["priority"] == "medium"

    @patch("src.openai_client._get_client")
    def test_limits_to_5_insights(self, mock_get_client):
        """Should cap at 5 insights even if GPT returns more."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        insights_list = [
            {"title": f"Insight {i}", "description": f"Desc {i}", "category": "opportunity", "priority": "low"}
            for i in range(8)
        ]
        import json
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"insights": insights_list})
        mock_client.chat.completions.create.return_value = mock_response

        from src.openai_client import generate_insights
        result = generate_insights(["text"] * 10)

        assert result is not None
        assert len(result) == 5

    @patch("src.openai_client._get_client")
    def test_returns_none_on_empty_content(self, mock_get_client):
        """Should return None when GPT returns empty content."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response

        from src.openai_client import generate_insights
        result = generate_insights(["text"])
        assert result is None

    @patch("src.openai_client._get_client")
    def test_returns_none_on_invalid_json(self, mock_get_client):
        """Should return None when GPT returns invalid JSON."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json"
        mock_client.chat.completions.create.return_value = mock_response

        from src.openai_client import generate_insights
        result = generate_insights(["text"])
        assert result is None

    @patch("src.openai_client._get_client")
    def test_skips_invalid_insight_items(self, mock_get_client):
        """Should skip insights missing required fields."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "insights": [
                {"title": "Valid", "description": "Has both fields", "category": "opportunity", "priority": "low"},
                {"title_only": "Missing description"},
                {"description_only": "Missing title"}
            ]
        }'''
        mock_client.chat.completions.create.return_value = mock_response

        from src.openai_client import generate_insights
        result = generate_insights(["text"])
        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Valid"


class TestGenerateWeeklyInsightsTask:
    """Tests for the generate_weekly_insights Celery task."""

    @patch("src.tasks.insights.get_db_session")
    @patch("src.tasks.insights.generate_insights")
    def test_generates_insights_for_ai_enabled_org(self, mock_gen, mock_db_session, db):
        """Should generate and store insights for AI-enabled orgs."""
        org = Organization(name="AI Corp", plan="pro", ai_analysis_enabled=True)
        db.add(org)
        db.commit()
        db.refresh(org)

        now = datetime.utcnow()
        for i in range(5):
            db.add(FeedbackItem(
                organization_id=org.id,
                text=f"Feedback {i}",
                source="manual",
                created_at=now - timedelta(days=1),
            ))
        db.commit()

        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gen.return_value = [
            {"title": "Test Insight", "description": "Desc", "category": "opportunity", "priority": "low"},
        ]

        from src.tasks.insights import generate_weekly_insights
        result = generate_weekly_insights()

        assert result["status"] == "complete"
        assert result["generated"] == 1

        insight = db.query(WeeklyInsight).filter(
            WeeklyInsight.organization_id == org.id,
        ).first()
        assert insight is not None
        assert len(insight.insights) == 1
        assert insight.insights[0]["title"] == "Test Insight"

    @patch("src.tasks.insights.get_db_session")
    @patch("src.tasks.insights.generate_insights")
    def test_skips_org_with_too_few_feedback(self, mock_gen, mock_db_session, db):
        """Should skip orgs with fewer than 3 feedback items."""
        org = Organization(name="Small Corp", plan="pro", ai_analysis_enabled=True)
        db.add(org)
        db.commit()
        db.refresh(org)

        now = datetime.utcnow()
        db.add(FeedbackItem(
            organization_id=org.id,
            text="Only one feedback",
            source="manual",
            created_at=now - timedelta(days=1),
        ))
        db.commit()

        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        from src.tasks.insights import generate_weekly_insights
        result = generate_weekly_insights()

        assert result["skipped"] == 1
        assert result["generated"] == 0
        mock_gen.assert_not_called()

    @patch("src.tasks.insights.get_db_session")
    def test_skips_ai_disabled_orgs(self, mock_db_session, db):
        """Should not generate insights for AI-disabled orgs."""
        org = Organization(name="No AI Corp", plan="pro", ai_analysis_enabled=False)
        db.add(org)
        db.commit()

        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        from src.tasks.insights import generate_weekly_insights
        result = generate_weekly_insights()

        assert result["status"] == "no_organizations"

    @patch("src.tasks.insights.get_db_session")
    @patch("src.tasks.insights.generate_insights")
    def test_skips_when_openai_returns_none(self, mock_gen, mock_db_session, db):
        """Should skip when OpenAI returns None (API failure)."""
        org = Organization(name="API Fail Corp", plan="pro", ai_analysis_enabled=True)
        db.add(org)
        db.commit()
        db.refresh(org)

        now = datetime.utcnow()
        for i in range(5):
            db.add(FeedbackItem(
                organization_id=org.id,
                text=f"Feedback {i}",
                source="manual",
                created_at=now - timedelta(days=1),
            ))
        db.commit()

        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gen.return_value = None

        from src.tasks.insights import generate_weekly_insights
        result = generate_weekly_insights()

        assert result["skipped"] == 1
        assert result["generated"] == 0

    @patch("src.tasks.insights.get_db_session")
    def test_no_organizations(self, mock_db_session, db):
        """Should handle case with no AI-enabled organizations."""
        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        from src.tasks.insights import generate_weekly_insights
        result = generate_weekly_insights()

        assert result["status"] == "no_organizations"


class TestWeeklyDigestWithInsights:
    """Tests that weekly digest includes insights HTML."""

    @patch("src.tasks.alerts.get_db_session")
    @patch("src.email.send_weekly_digest_email")
    def test_digest_includes_insights_html(self, mock_send, mock_db_session, db):
        """When insights exist, digest should pass insights_html to email."""
        org = Organization(name="Test Corp", plan="pro")
        db.add(org)
        db.commit()
        db.refresh(org)

        user = User(
            email="user@test.com",
            organization_id=org.id,
            role="owner",
            weekly_digest_enabled=True,
        )
        db.add(user)
        db.commit()

        now = datetime.utcnow()
        for i in range(3):
            db.add(FeedbackItem(
                organization_id=org.id,
                text=f"Feedback {i}",
                source="manual",
                sentiment_label="positive",
                sentiment_score=0.9,
                created_at=now - timedelta(days=1),
            ))

        # Add weekly insight
        db.add(WeeklyInsight(
            organization_id=org.id,
            week_start=now - timedelta(days=7),
            week_end=now,
            insights=[
                {"title": "Insight A", "description": "Detail A", "category": "opportunity", "priority": "high"},
            ],
            generated_at=now,
        ))
        db.commit()

        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_send.return_value = True

        from src.tasks.alerts import send_weekly_digests
        result = send_weekly_digests()

        assert result["sent"] == 1
        # Check that insights_html was passed
        call_kwargs = mock_send.call_args[1]
        assert "insights_html" in call_kwargs
        assert "Insight A" in call_kwargs["insights_html"]
        assert "Detail A" in call_kwargs["insights_html"]

    @patch("src.tasks.alerts.get_db_session")
    @patch("src.email.send_weekly_digest_email")
    def test_digest_empty_insights_when_none(self, mock_send, mock_db_session, db):
        """When no insights exist, digest should pass empty string."""
        org = Organization(name="No Insight Corp", plan="pro")
        db.add(org)
        db.commit()
        db.refresh(org)

        user = User(
            email="noinsight@test.com",
            organization_id=org.id,
            role="owner",
            weekly_digest_enabled=True,
        )
        db.add(user)
        db.commit()

        now = datetime.utcnow()
        for i in range(3):
            db.add(FeedbackItem(
                organization_id=org.id,
                text=f"Feedback {i}",
                source="manual",
                sentiment_label="neutral",
                sentiment_score=0.1,
                created_at=now - timedelta(days=1),
            ))
        db.commit()

        mock_db_session.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_send.return_value = True

        from src.tasks.alerts import send_weekly_digests
        result = send_weekly_digests()

        assert result["sent"] == 1
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["insights_html"] == ""
