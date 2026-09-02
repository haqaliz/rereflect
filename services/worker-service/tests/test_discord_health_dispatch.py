"""
TDD tests for Discord dispatch of customer health drop/recovery alerts.

notification_dispatch.py::_dispatch_slack_health_alert (~:59) plus
build_health_alert_blocks (~:100-184) are the Slack side of this alert. This adds
build_discord_health_alert_embeds with the SAME argument list as
build_health_alert_blocks (so call sites only branch on integration.type), and
_dispatch_discord_health_alert to send it. Discord webhooks cannot render the
Slack version's actions/button block, so the customer URL goes in the embed's
"url" field instead.

Also pins the worker decrypt mirror at notification_dispatch.py:104:
_dispatch_slack_health_alert must hand send_slack_message_oauth the PLAINTEXT
token, and a missing key / corrupt ciphertext must log-and-skip the integration
(the file's local error shape) without raising.
"""
import os
from unittest.mock import patch, MagicMock

from src.models import Organization, Integration

ENCRYPTION_KEY = "F5XVApZxzOVKc2xrZlnI6ouXipDzsxflzFn2Ki_5_yk="


def _encrypt(secret: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(ENCRYPTION_KEY.encode()).encrypt(secret.encode()).decode()


COMPONENTS = {
    "churn_risk": 78,
    "sentiment": 35,
    "resolution": 60,
    "frequency": 45,
}


def make_org(db) -> Organization:
    org = Organization(name="Discord Health Corp", plan="pro")
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


# ---------------------------------------------------------------------------
# build_discord_health_alert_embeds()
# ---------------------------------------------------------------------------

class TestBuildDiscordHealthAlertEmbeds:
    def test_same_argument_list_as_slack_builder(self):
        """Call sites should only branch on integration.type, not argument shape."""
        import inspect
        from src.notification_dispatch import (
            build_health_alert_blocks,
            build_discord_health_alert_embeds,
        )

        slack_params = list(inspect.signature(build_health_alert_blocks).parameters)
        discord_params = list(inspect.signature(build_discord_health_alert_embeds).parameters)
        assert discord_params == slack_params

    def test_drop_alert_returns_embed_with_customer_and_score_fields(self):
        from src.notification_dispatch import build_discord_health_alert_embeds

        embeds = build_discord_health_alert_embeds(
            customer_email="john@acme.com",
            customer_name="John",
            old_score=65,
            new_score=42,
            old_risk_level="moderate",
            new_risk_level="at_risk",
            components=COMPONENTS,
            is_recovery=False,
        )

        assert isinstance(embeds, list)
        assert 1 <= len(embeds) <= 10  # THE CONTRACT: max 10 embeds
        embed = embeds[0]
        assert "Drop" in embed["title"] or "drop" in embed["title"].lower()
        assert isinstance(embed["color"], int)  # decimal, not "#hex"

        all_text = str(embed)
        assert "john@acme.com" in all_text
        assert "65" in all_text
        assert "42" in all_text
        assert len(embed.get("fields", [])) <= 25  # THE CONTRACT: max 25 fields

    def test_no_buttons_customer_url_is_in_embed_url_field(self):
        """Discord webhooks can't render the Slack actions/button block — the
        customer link must live in the embed's url field instead."""
        from src.notification_dispatch import build_discord_health_alert_embeds

        embeds = build_discord_health_alert_embeds(
            customer_email="john@acme.com",
            customer_name="John",
            old_score=65,
            new_score=42,
            old_risk_level="moderate",
            new_risk_level="at_risk",
            components=COMPONENTS,
            is_recovery=False,
        )

        embed = embeds[0]
        assert embed.get("url"), "customer URL must be present since Discord can't render a button"
        assert "john%40acme.com" in embed["url"] or "john@acme.com" in embed["url"]
        # No Slack-style actions/button block should leak into a Discord embed.
        assert "actions" not in embed
        assert "elements" not in embed

    def test_recovery_alert_uses_positive_color(self):
        from src.notification_dispatch import build_discord_health_alert_embeds

        drop_embeds = build_discord_health_alert_embeds(
            customer_email="john@acme.com",
            customer_name="John",
            old_score=65,
            new_score=42,
            old_risk_level="moderate",
            new_risk_level="at_risk",
            components=COMPONENTS,
            is_recovery=False,
        )
        recovery_embeds = build_discord_health_alert_embeds(
            customer_email="john@acme.com",
            customer_name="John",
            old_score=42,
            new_score=58,
            old_risk_level="at_risk",
            new_risk_level="moderate",
            components=COMPONENTS,
            is_recovery=True,
        )

        assert recovery_embeds[0]["color"] != drop_embeds[0]["color"]
        assert "Improved" in recovery_embeds[0]["title"] or "improved" in recovery_embeds[0]["title"].lower()

    def test_description_is_truncated_not_erroring(self):
        """THE CONTRACT: description <= 4096 chars, truncate rather than error."""
        from src.notification_dispatch import build_discord_health_alert_embeds

        huge_components = {f"driver_{i}": i for i in range(500)}
        embeds = build_discord_health_alert_embeds(
            customer_email="john@acme.com",
            customer_name="John",
            old_score=65,
            new_score=42,
            old_risk_level="moderate",
            new_risk_level="at_risk",
            components=huge_components,
            is_recovery=False,
        )
        description = embeds[0].get("description", "")
        assert len(description) <= 4096


# ---------------------------------------------------------------------------
# _dispatch_discord_health_alert()
# ---------------------------------------------------------------------------

class TestDispatchDiscordHealthAlert:
    def test_sends_embeds_and_content_to_active_discord_integrations(self, db):
        from src.notification_dispatch import _dispatch_discord_health_alert

        org = make_org(db)
        make_discord_integration(db, org.id)

        embeds = [{"title": "Customer Health Drop", "color": 15548997}]

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook") as mock_send:
                _dispatch_discord_health_alert(org.id, embeds, "Customer health drop: john@acme.com")

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["webhook_url"] == "https://discord.com/api/webhooks/1/abc"
        assert call_kwargs["embeds"] == embeds
        assert call_kwargs["content"] == "Customer health drop: john@acme.com"

    def test_ignores_slack_and_inactive_integrations(self, db):
        from src.notification_dispatch import _dispatch_discord_health_alert

        org = make_org(db)
        db.add(Integration(
            organization_id=org.id, type="slack",
            config={"webhook_url": "https://hooks.slack.com/services/x"}, is_active=True,
        ))
        make_discord_integration(db, org.id, is_active=False)
        db.commit()

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook") as mock_send:
                _dispatch_discord_health_alert(org.id, [{"title": "x"}], "content")

        mock_send.assert_not_called()

    def test_failure_on_one_integration_does_not_abort_the_others(self, db):
        from src.notification_dispatch import _dispatch_discord_health_alert

        org = make_org(db)
        make_discord_integration(db, org.id, webhook_url="https://discord.com/api/webhooks/1/fail")
        make_discord_integration(db, org.id, webhook_url="https://discord.com/api/webhooks/2/ok")

        def side_effect(**kwargs):
            if kwargs["webhook_url"].endswith("/fail"):
                raise Exception("boom")
            return {"success": True}

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_discord_message_webhook", side_effect=side_effect) as mock_send:
                _dispatch_discord_health_alert(org.id, [{"title": "x"}], "content")

        assert mock_send.call_count == 2


# ---------------------------------------------------------------------------
# _dispatch_slack_health_alert() -- OAuth token decryption (worker decrypt mirrors)
# ---------------------------------------------------------------------------

class TestDispatchSlackHealthAlert:
    """_dispatch_slack_health_alert (notification_dispatch.py:104) must decrypt
    integrations.oauth_access_token before sending; a missing key or corrupt
    ciphertext logs and skips the integration (the file's local error shape —
    there is no channel_errors dict on this path) without raising."""

    def _make_slack_oauth_integration(self, db, org_id: int, token: str) -> Integration:
        integ = Integration(
            organization_id=org_id,
            type="slack",
            config={"integration_type": "oauth", "channel_id": "C1"},
            oauth_access_token=token,
            is_active=True,
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)
        return integ

    def test_plaintext_token_reaches_send_slack_message_oauth(self, db):
        from src.notification_dispatch import _dispatch_slack_health_alert

        org = make_org(db)
        integ = self._make_slack_oauth_integration(db, org.id, _encrypt("xoxb-health-dispatch"))
        assert "xoxb-health-dispatch" not in integ.oauth_access_token

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "health drop"}}]

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.tasks.alerts.send_slack_message_oauth") as mock_send, \
                 patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
                _dispatch_slack_health_alert(org.id, blocks, "health drop text")

        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["access_token"] == "xoxb-health-dispatch"
        assert mock_send.call_args.kwargs["channel_id"] == "C1"

    def test_missing_key_logs_and_skips_without_sending(self, db):
        from src.notification_dispatch import _dispatch_slack_health_alert

        org = make_org(db)
        self._make_slack_oauth_integration(db, org.id, _encrypt("xoxb-health-dispatch"))

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.tasks.alerts.send_slack_message_oauth") as mock_send, \
                 patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ""}):
                _dispatch_slack_health_alert(org.id, [{"type": "section"}], "text")

        mock_send.assert_not_called()

    def test_corrupt_ciphertext_logs_and_skips_without_sending(self, db):
        from src.notification_dispatch import _dispatch_slack_health_alert

        org = make_org(db)
        self._make_slack_oauth_integration(db, org.id, "garbage-not-fernet")

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.tasks.alerts.send_slack_message_oauth") as mock_send, \
                 patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
                _dispatch_slack_health_alert(org.id, [{"type": "section"}], "text")

        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# dispatch_health_drop_alert() wiring
# ---------------------------------------------------------------------------

class TestDispatchHealthDropAlertTriggersDiscord:
    """dispatch_health_drop_alert() must dispatch Slack and Discord independently,
    each off its own channel preference — no piggybacking on the Slack toggle.

    Same four-way matrix as the main pipe: slack-only, discord-only, both, and
    no-pref-row defaults.
    """

    def _make_user_pref(self, db, channel_slack: bool, channel_discord: bool) -> int:
        from src.models import User, UserAlertPreference

        org = make_org(db)
        user = User(email="user@test.com", organization_id=org.id, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)

        pref = UserAlertPreference(
            user_id=user.id,
            alert_type="customer_health_drop",
            is_enabled=True,
            channel_inapp=False,
            channel_slack=channel_slack,
            channel_email=False,
        )
        pref.channel_discord = channel_discord
        pref.channel_teams = False
        db.add(pref)
        db.commit()
        db.refresh(pref)
        return org.id

    def _dispatch_with_mocks(self, db, org_id: int):
        from src.notification_dispatch import dispatch_health_drop_alert

        with patch("src.notification_dispatch._get_redis_client") as mock_redis:
            mock_redis.return_value.get.return_value = None
            with patch("src.notification_dispatch._check_org_plan") as mock_plan:
                mock_plan.return_value = True
                with patch("src.notification_dispatch._dispatch_slack_health_alert") as mock_slack:
                    with patch("src.notification_dispatch._dispatch_discord_health_alert") as mock_discord:
                        dispatch_health_drop_alert(
                            org_id=org_id,
                            customer_email="john@acme.com",
                            customer_name="John",
                            old_score=65,
                            new_score=42,
                            old_risk_level="moderate",
                            new_risk_level="at_risk",
                            components=COMPONENTS,
                            db=db,
                        )

        return mock_slack, mock_discord

    def test_slack_only_preference_skips_discord_dispatch(self, db):
        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=False)

        mock_slack, mock_discord = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_called_once()
        assert mock_slack.call_args.args[0] == org_id
        mock_discord.assert_not_called()

    def test_discord_only_preference_skips_slack_dispatch(self, db):
        org_id = self._make_user_pref(db, channel_slack=False, channel_discord=True)

        mock_slack, mock_discord = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_not_called()
        mock_discord.assert_called_once()
        assert mock_discord.call_args.args[0] == org_id

    def test_both_channels_enabled_dispatches_both(self, db):
        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=True)

        mock_slack, mock_discord = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_called_once()
        assert mock_slack.call_args.args[0] == org_id
        mock_discord.assert_called_once()
        assert mock_discord.call_args.args[0] == org_id

    def test_no_preference_row_defaults_to_slack_and_discord(self, db):
        from src.models import User

        org = make_org(db)
        user = User(email="user@test.com", organization_id=org.id, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)

        mock_slack, mock_discord = self._dispatch_with_mocks(db, org.id)

        mock_slack.assert_called_once()
        assert mock_slack.call_args.args[0] == org.id
        mock_discord.assert_called_once()
        assert mock_discord.call_args.args[0] == org.id

    def test_counts_dict_includes_discord_key(self, db):
        from src.notification_dispatch import dispatch_health_drop_alert

        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=True)

        with patch("src.notification_dispatch._get_redis_client") as mock_redis:
            mock_redis.return_value.get.return_value = None
            with patch("src.notification_dispatch._check_org_plan") as mock_plan:
                mock_plan.return_value = True
                with patch("src.notification_dispatch._dispatch_slack_health_alert"):
                    with patch("src.notification_dispatch._dispatch_discord_health_alert"):
                        counts = dispatch_health_drop_alert(
                            org_id=org_id,
                            customer_email="john@acme.com",
                            customer_name="John",
                            old_score=65,
                            new_score=42,
                            old_risk_level="moderate",
                            new_risk_level="at_risk",
                            components=COMPONENTS,
                            db=db,
                        )

        assert counts == {"inapp": 0, "slack": 1, "discord": 1, "teams": 0, "email": 0}
