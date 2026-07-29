"""
TDD tests for Discord dispatch at the main alert pipe.

notification_dispatch.py::_dispatch_slack_alert (~:501) is the main user-facing pipe
for urgent_feedback / sentiment_spike / churn_risk / volume_spike. This adds its
Discord equivalent, _dispatch_discord_alert, fanning out over active Discord
integrations and writing back last_used_at / error_count / last_error exactly like
the Slack version — or the integration-health UI silently goes stale.

Patched at the import site (src.notification_dispatch.send_discord_message_webhook)
per the spec: notification_dispatch.py imports it at module top, so patching the
definition site in src.tasks.alerts would pass while patching nothing.
"""
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from src.models import Organization, Integration


def make_org(db) -> Organization:
    org = Organization(name="Discord Corp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def make_discord_integration(db, org_id: int, webhook_url="https://discord.com/api/webhooks/1/abc", is_active=True) -> Integration:
    integ = Integration(
        organization_id=org_id,
        type="discord",
        config={"webhook_url": webhook_url, "integration_type": "webhook"},
        is_active=is_active,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


class TestDispatchDiscordAlert:
    """Tests for _dispatch_discord_alert() in notification_dispatch.py."""

    def test_sends_to_active_discord_integration_with_embeds_and_content(self, db):
        from src.notification_dispatch import _dispatch_discord_alert

        org = make_org(db)
        make_discord_integration(db, org.id)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook") as mock_send:
                _dispatch_discord_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent feedback from acme@example.com",
                    message="Customer reported a billing bug.",
                    link="/feedbacks/123",
                )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["webhook_url"] == "https://discord.com/api/webhooks/1/abc"
        # THE CONTRACT: body must carry both content and embeds.
        assert "content" in call_kwargs
        assert call_kwargs["content"]
        assert "embeds" in call_kwargs
        assert len(call_kwargs["embeds"]) >= 1
        embed = call_kwargs["embeds"][0]
        assert "Urgent feedback" in embed["title"]
        assert isinstance(embed["color"], int)  # decimal, not "#hex"

    def test_ignores_inactive_discord_integrations(self, db):
        from src.notification_dispatch import _dispatch_discord_alert

        org = make_org(db)
        make_discord_integration(db, org.id, is_active=False)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook") as mock_send:
                _dispatch_discord_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent",
                    message="msg",
                    link=None,
                )

        mock_send.assert_not_called()

    def test_ignores_slack_integrations(self, db):
        """Only Integration.type == 'discord' rows are dispatched to."""
        from src.notification_dispatch import _dispatch_discord_alert

        org = make_org(db)
        db.add(Integration(
            organization_id=org.id,
            type="slack",
            config={"webhook_url": "https://hooks.slack.com/services/x"},
            is_active=True,
        ))
        db.commit()

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook") as mock_send:
                _dispatch_discord_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent",
                    message="msg",
                    link=None,
                )

        mock_send.assert_not_called()

    def test_success_writes_back_last_used_at_and_clears_error(self, db):
        from src.notification_dispatch import _dispatch_discord_alert

        org = make_org(db)
        integ = make_discord_integration(db, org.id)
        integ.error_count = 3
        integ.last_error = "previous failure"
        db.commit()

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook", return_value={"success": True}):
                _dispatch_discord_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent",
                    message="msg",
                    link=None,
                )

        db.refresh(integ)
        assert integ.last_used_at is not None
        assert integ.error_count == 0
        assert integ.last_error is None

    def test_failure_records_error_count_and_last_error_without_aborting_others(self, db):
        """A raising Discord send is caught per-integration, logged, and does not
        abort the others — one integration fails, the next still gets a send attempt."""
        from src.notification_dispatch import _dispatch_discord_alert

        org = make_org(db)
        failing = make_discord_integration(db, org.id, webhook_url="https://discord.com/api/webhooks/1/fail")
        healthy = make_discord_integration(db, org.id, webhook_url="https://discord.com/api/webhooks/2/ok")

        def side_effect(**kwargs):
            if kwargs["webhook_url"].endswith("/fail"):
                raise Exception("Discord 400: missing embeds")
            return {"success": True}

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook", side_effect=side_effect) as mock_send:
                _dispatch_discord_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent",
                    message="msg",
                    link=None,
                )

        assert mock_send.call_count == 2  # both attempted, failure of one did not abort the other

        db.refresh(failing)
        db.refresh(healthy)

        assert failing.error_count == 1
        assert "Discord 400" in failing.last_error

        assert healthy.error_count == 0
        assert healthy.last_error is None
        assert healthy.last_used_at is not None

    def test_no_discord_integrations_is_a_noop(self, db):
        from src.notification_dispatch import _dispatch_discord_alert

        org = make_org(db)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook") as mock_send:
                _dispatch_discord_alert(
                    org_id=org.id,
                    alert_type="volume_spike",
                    title="Volume spike",
                    message="msg",
                    link=None,
                )

        mock_send.assert_not_called()


class TestDispatchAlertTriggersDiscord:
    """dispatch_alert() should trigger Discord alongside Slack for the main pipe."""

    def test_dispatch_alert_calls_discord_dispatch_when_slack_channel_enabled(self, db):
        from src.notification_dispatch import dispatch_alert
        from src.models import User, UserAlertPreference

        org = make_org(db)
        user = User(email="user@test.com", organization_id=org.id, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(UserAlertPreference(
            user_id=user.id,
            alert_type="urgent_feedback",
            is_enabled=True,
            channel_inapp=False,
            channel_slack=True,
            channel_email=False,
        ))
        db.commit()

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch._dispatch_slack_alert") as mock_slack:
                with patch("src.notification_dispatch._dispatch_discord_alert") as mock_discord:
                    dispatch_alert(
                        org_id=org.id,
                        alert_type="urgent_feedback",
                        title="Urgent feedback",
                        message="msg",
                        link="/feedbacks/1",
                    )

        mock_slack.assert_called_once()
        mock_discord.assert_called_once()
