"""
Tests for outbound email alert dispatch.
TDD: Tests written BEFORE implementation.
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.models.user_alert_preference import UserAlertPreference
from src.api.auth import hash_password


# ── Helpers ──────────────────────────────────────────────────────────────────

def _seed_pref(db: Session, user_id: int, alert_type: str, is_enabled: bool = True,
               channel_email: bool = False, channel_inapp: bool = True):
    """Seed a single alert preference for a user."""
    pref = UserAlertPreference(
        user_id=user_id,
        alert_type=alert_type,
        is_enabled=is_enabled,
        channel_email=channel_email,
        channel_slack=False,
        channel_inapp=channel_inapp,
        threshold_value=None,
    )
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


# ── send_alert_email tests ──────────────────────────────────────────────────

class TestSendAlertEmail:
    """Tests for the send_alert_email function in email_service.py."""

    def test_sends_email_for_urgent_feedback(self):
        """send_alert_email should call _send_email with correct subject for urgent_feedback."""
        with patch("src.services.email_service.RESEND_API_KEY", "test-key"), \
             patch("src.services.email_service.TEMPLATE_ALERT_NOTIFICATION", "tmpl-123"), \
             patch("src.services.email_service._get_template") as mock_get_template, \
             patch("src.services.email_service._send_email_with_from") as mock_send:
            mock_get_template.return_value = ("<html>{{{ALERT_TITLE}}}</html>", "{{{ALERT_TITLE}}}")
            mock_send.return_value = True

            from src.services.email_service import send_alert_email
            result = send_alert_email(
                to_email="user@example.com",
                alert_type="urgent_feedback",
                alert_data={"title": "Urgent feedback detected", "description": "A customer reported a critical issue."},
            )

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["from_email"] == "Rereflect Alerts <alerts@rereflect.ca>"
            assert "[Rereflect] Urgent feedback detected" in call_args[1]["subject"]

    def test_sends_email_for_sentiment_spike(self):
        """send_alert_email should use correct subject for sentiment_spike."""
        with patch("src.services.email_service.RESEND_API_KEY", "test-key"), \
             patch("src.services.email_service.TEMPLATE_ALERT_NOTIFICATION", "tmpl-123"), \
             patch("src.services.email_service._get_template") as mock_get_template, \
             patch("src.services.email_service._send_email_with_from") as mock_send:
            mock_get_template.return_value = ("<html>{{{ALERT_TITLE}}}</html>", "{{{ALERT_TITLE}}}")
            mock_send.return_value = True

            from src.services.email_service import send_alert_email
            result = send_alert_email(
                to_email="user@example.com",
                alert_type="sentiment_spike",
                alert_data={"title": "Sentiment spike alert", "description": "Negative sentiment increased by 45%."},
            )

            assert result is True
            call_args = mock_send.call_args
            assert "[Rereflect] Sentiment spike alert" in call_args[1]["subject"]

    def test_sends_email_for_churn_risk(self):
        """send_alert_email should use correct subject for churn_risk."""
        with patch("src.services.email_service.RESEND_API_KEY", "test-key"), \
             patch("src.services.email_service.TEMPLATE_ALERT_NOTIFICATION", "tmpl-123"), \
             patch("src.services.email_service._get_template") as mock_get_template, \
             patch("src.services.email_service._send_email_with_from") as mock_send:
            mock_get_template.return_value = ("<html>{{{ALERT_TITLE}}}</html>", "{{{ALERT_TITLE}}}")
            mock_send.return_value = True

            from src.services.email_service import send_alert_email
            result = send_alert_email(
                to_email="user@example.com",
                alert_type="churn_risk",
                alert_data={"title": "Churn risk detected", "description": "Customer showing signs of churn."},
            )

            assert result is True
            call_args = mock_send.call_args
            assert "[Rereflect] Churn risk detected" in call_args[1]["subject"]

    def test_sends_email_for_volume_spike(self):
        """send_alert_email should use correct subject for volume_spike."""
        with patch("src.services.email_service.RESEND_API_KEY", "test-key"), \
             patch("src.services.email_service.TEMPLATE_ALERT_NOTIFICATION", "tmpl-123"), \
             patch("src.services.email_service._get_template") as mock_get_template, \
             patch("src.services.email_service._send_email_with_from") as mock_send:
            mock_get_template.return_value = ("<html>{{{ALERT_TITLE}}}</html>", "{{{ALERT_TITLE}}}")
            mock_send.return_value = True

            from src.services.email_service import send_alert_email
            result = send_alert_email(
                to_email="user@example.com",
                alert_type="volume_spike",
                alert_data={"title": "Feedback volume spike", "description": "Feedback volume is 3x the normal rate."},
            )

            assert result is True
            call_args = mock_send.call_args
            assert "[Rereflect] Feedback volume spike" in call_args[1]["subject"]

    def test_returns_false_when_api_key_not_configured(self):
        """send_alert_email should return False when RESEND_API_KEY is not set."""
        with patch("src.services.email_service.RESEND_API_KEY", None), \
             patch("src.services.email_service.TEMPLATE_ALERT_NOTIFICATION", "tmpl-123"):
            from src.services.email_service import send_alert_email
            result = send_alert_email(
                to_email="user@example.com",
                alert_type="urgent_feedback",
                alert_data={"title": "Test", "description": "Test"},
            )
            assert result is False

    def test_returns_false_when_template_not_configured(self):
        """send_alert_email should return False when template ID is not set."""
        with patch("src.services.email_service.RESEND_API_KEY", "test-key"), \
             patch("src.services.email_service.TEMPLATE_ALERT_NOTIFICATION", None):
            from src.services.email_service import send_alert_email
            result = send_alert_email(
                to_email="user@example.com",
                alert_type="urgent_feedback",
                alert_data={"title": "Test", "description": "Test"},
            )
            assert result is False


# ── Notification dispatch wiring tests ──────────────────────────────────────

class TestEmailDispatchWiring:
    """Tests for email dispatch wiring in notification_dispatch_helpers.py."""

    def test_sends_email_when_channel_email_enabled(self, db: Session, test_user: User, test_organization: Organization):
        """When user has channel_email=True, send_alert_email should be called."""
        _seed_pref(db, test_user.id, "urgent_feedback", is_enabled=True, channel_email=True)

        with patch("src.notification_dispatch_helpers.send_alert_email") as mock_send:
            mock_send.return_value = True

            from src.notification_dispatch_helpers import _create_targeted_notifications
            _create_targeted_notifications(
                db,
                org_id=test_organization.id,
                target_user_ids=[test_user.id],
                alert_type="urgent_feedback",
                title="Urgent feedback detected",
                message="A customer reported a critical issue.",
                link="/feedbacks/1",
            )

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["to_email"] == test_user.email
            assert call_args[1]["alert_type"] == "urgent_feedback"

    def test_no_email_when_channel_email_disabled(self, db: Session, test_user: User, test_organization: Organization):
        """When user has channel_email=False, send_alert_email should NOT be called."""
        _seed_pref(db, test_user.id, "urgent_feedback", is_enabled=True, channel_email=False)

        with patch("src.notification_dispatch_helpers.send_alert_email") as mock_send:
            from src.notification_dispatch_helpers import _create_targeted_notifications
            _create_targeted_notifications(
                db,
                org_id=test_organization.id,
                target_user_ids=[test_user.id],
                alert_type="urgent_feedback",
                title="Urgent feedback detected",
                message="A customer reported a critical issue.",
                link="/feedbacks/1",
            )

            mock_send.assert_not_called()

    def test_no_email_when_alert_disabled(self, db: Session, test_user: User, test_organization: Organization):
        """When user has is_enabled=False, no email should be sent regardless of channel_email."""
        _seed_pref(db, test_user.id, "urgent_feedback", is_enabled=False, channel_email=True)

        with patch("src.notification_dispatch_helpers.send_alert_email") as mock_send:
            from src.notification_dispatch_helpers import _create_targeted_notifications
            _create_targeted_notifications(
                db,
                org_id=test_organization.id,
                target_user_ids=[test_user.id],
                alert_type="urgent_feedback",
                title="Urgent feedback detected",
                message="A customer reported a critical issue.",
                link="/feedbacks/1",
            )

            mock_send.assert_not_called()

    def test_multiple_users_different_preferences(self, db: Session, test_organization: Organization):
        """Multiple users with different preferences get correct email dispatch."""
        user1 = User(
            email="user1@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        user2 = User(
            email="user2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        # user1 has email enabled, user2 has email disabled
        _seed_pref(db, user1.id, "urgent_feedback", is_enabled=True, channel_email=True)
        _seed_pref(db, user2.id, "urgent_feedback", is_enabled=True, channel_email=False)

        with patch("src.notification_dispatch_helpers.send_alert_email") as mock_send:
            mock_send.return_value = True

            from src.notification_dispatch_helpers import _create_targeted_notifications
            _create_targeted_notifications(
                db,
                org_id=test_organization.id,
                target_user_ids=[user1.id, user2.id],
                alert_type="urgent_feedback",
                title="Urgent feedback detected",
                message="A customer reported a critical issue.",
                link="/feedbacks/1",
            )

            # Only user1 should get email
            assert mock_send.call_count == 1
            call_args = mock_send.call_args
            assert call_args[1]["to_email"] == "user1@example.com"
