"""
Tests for the weekly digest Celery task.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.models import Organization, User, FeedbackItem


class TestSendWeeklyDigests:
    """Tests for send_weekly_digests task."""

    def test_sends_digest_to_opted_in_users(self, db, test_org, test_user, recent_feedback):
        """Should send digest email to users with weekly_digest_enabled=True."""
        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_send_email.return_value = True

            result = send_weekly_digests()

            assert result["status"] == "complete"
            assert result["sent"] == 1
            mock_send_email.assert_called_once()

            call_kwargs = mock_send_email.call_args.kwargs
            assert call_kwargs["to_email"] == "user@test.com"
            assert call_kwargs["organization_name"] == "Test Corp"
            assert call_kwargs["total_feedback"] == 3
            assert call_kwargs["pain_points"] == 1
            assert call_kwargs["feature_requests"] == 1
            assert call_kwargs["urgent_count"] == 1

    def test_skips_opted_out_users(self, db, test_org, opted_out_user, recent_feedback):
        """Should not send digest to users with weekly_digest_enabled=False."""
        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_send_email.return_value = True

            result = send_weekly_digests()

            assert result["sent"] == 0
            mock_send_email.assert_not_called()

    def test_skips_orgs_with_no_recent_feedback(self, db, test_org, test_user, old_feedback):
        """Should skip orgs that have no feedback in the past 7 days."""
        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = send_weekly_digests()

            assert result["skipped"] == 1
            assert result["sent"] == 0
            mock_send_email.assert_not_called()

    def test_returns_no_organizations(self, db):
        """Should return early when no organizations exist."""
        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = send_weekly_digests()

            assert result["status"] == "no_organizations"
            assert result["sent"] == 0
            mock_send_email.assert_not_called()

    def test_counts_email_failures_as_errors(self, db, test_org, test_user, recent_feedback):
        """Should count failed email sends as errors."""
        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_send_email.return_value = False  # Simulate email failure

            result = send_weekly_digests()

            assert result["errors"] == 1
            assert result["sent"] == 0

    def test_calculates_sentiment_percentages(self, db, test_org, test_user, recent_feedback):
        """Should correctly calculate sentiment percentages from feedback."""
        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_send_email.return_value = True

            send_weekly_digests()

            call_kwargs = mock_send_email.call_args.kwargs
            # 3 feedbacks: 1 positive, 1 neutral, 1 negative = 33% each
            assert call_kwargs["positive_percent"] == 33
            assert call_kwargs["neutral_percent"] == 33
            # negative_pct = 100 - 33 - 33 = 34
            assert call_kwargs["negative_percent"] == 34

    def test_sends_to_multiple_users_in_same_org(self, db, test_org, test_user, recent_feedback):
        """Should send digest to all opted-in users in an org."""
        # Add a second opted-in user
        user2 = User(
            email="user2@test.com",
            organization_id=test_org.id,
            role="member",
            weekly_digest_enabled=True,
        )
        db.add(user2)
        db.commit()

        from src.tasks.alerts import send_weekly_digests

        with patch("src.tasks.alerts.get_db_session") as mock_db_ctx, \
             patch("src.email.send_weekly_digest_email") as mock_send_email:
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_send_email.return_value = True

            result = send_weekly_digests()

            assert result["sent"] == 2
            assert mock_send_email.call_count == 2
