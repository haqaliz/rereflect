"""
Tests for weekly insights generation Celery task.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.models import Organization, User, FeedbackItem, WeeklyInsight


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
