"""
TDD tests for Teams dispatch of customer health drop/recovery alerts.

notification_dispatch.py::_dispatch_teams_health_alert sends a MessageCard
(title + text) to the org's active Teams webhook integrations, mirroring
_dispatch_discord_health_alert — same gating (Integration.type == "teams",
is_active), per-integration failure isolation (never raises out of the
dispatch), single commit.

dispatch_health_drop_alert() must gate Teams on its own channel_teams
preference, exactly like slack/discord — no piggybacking on another toggle.
"""
from unittest.mock import patch, MagicMock

from src.models import Organization, Integration

COMPONENTS = {
    "churn_risk": 78,
    "sentiment": 35,
    "resolution": 60,
    "frequency": 45,
}


def make_org(db) -> Organization:
    org = Organization(name="Teams Health Corp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def make_teams_integration(db, org_id: int, webhook_url="https://outlook.office.com/webhook/1/abc", is_active=True) -> Integration:
    integ = Integration(
        organization_id=org_id,
        type="teams",
        config={"webhook_url": webhook_url, "integration_type": "webhook"},
        is_active=is_active,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


class TestDispatchTeamsHealthAlert:
    """Tests for _dispatch_teams_health_alert() in notification_dispatch.py."""

    def test_sends_title_and_text_to_active_teams_integrations(self, db):
        from src.notification_dispatch import _dispatch_teams_health_alert

        org = make_org(db)
        make_teams_integration(db, org.id)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook") as mock_send:
                _dispatch_teams_health_alert(
                    org.id,
                    "Customer health drop: john@acme.com",
                    "Customer health drop: john@acme.com",
                )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["webhook_url"] == "https://outlook.office.com/webhook/1/abc"
        assert call_kwargs["title"] == "Customer health drop: john@acme.com"
        assert call_kwargs["text"] == "Customer health drop: john@acme.com"

    def test_ignores_slack_and_inactive_integrations(self, db):
        from src.notification_dispatch import _dispatch_teams_health_alert

        org = make_org(db)
        db.add(Integration(
            organization_id=org.id, type="slack",
            config={"webhook_url": "https://hooks.slack.com/services/x"}, is_active=True,
        ))
        make_teams_integration(db, org.id, is_active=False)
        db.commit()

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook") as mock_send:
                _dispatch_teams_health_alert(org.id, "Title", "Text")

        mock_send.assert_not_called()

    def test_failure_on_one_integration_does_not_abort_the_others(self, db):
        from src.notification_dispatch import _dispatch_teams_health_alert

        org = make_org(db)
        make_teams_integration(db, org.id, webhook_url="https://outlook.office.com/webhook/1/fail")
        make_teams_integration(db, org.id, webhook_url="https://outlook.office.com/webhook/2/ok")

        def side_effect(**kwargs):
            if kwargs["webhook_url"].endswith("/fail"):
                raise Exception("boom")
            return {"success": True}

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook", side_effect=side_effect) as mock_send:
                _dispatch_teams_health_alert(org.id, "Title", "Text")

        assert mock_send.call_count == 2


class TestDispatchHealthDropAlertTriggersTeams:
    """dispatch_health_drop_alert() must dispatch Slack, Discord and Teams
    independently, each off its own channel preference — no piggybacking on
    the Slack toggle."""

    def _make_user_pref(self, db, channel_slack: bool, channel_discord: bool, channel_teams: bool) -> int:
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
            channel_discord=channel_discord,
            channel_teams=channel_teams,
            channel_email=False,
        )
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
                        with patch("src.notification_dispatch._dispatch_teams_health_alert") as mock_teams:
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

        return mock_slack, mock_discord, mock_teams

    def test_slack_only_preference_skips_teams_dispatch(self, db):
        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=False, channel_teams=False)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_called_once()
        assert mock_slack.call_args.args[0] == org_id
        mock_discord.assert_not_called()
        mock_teams.assert_not_called()

    def test_teams_only_preference_skips_slack_and_discord_dispatch(self, db):
        org_id = self._make_user_pref(db, channel_slack=False, channel_discord=False, channel_teams=True)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_not_called()
        mock_discord.assert_not_called()
        mock_teams.assert_called_once()
        assert mock_teams.call_args.args[0] == org_id

    def test_all_channels_enabled_dispatches_all(self, db):
        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=True, channel_teams=True)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_called_once()
        assert mock_slack.call_args.args[0] == org_id
        mock_discord.assert_called_once()
        assert mock_discord.call_args.args[0] == org_id
        mock_teams.assert_called_once()
        assert mock_teams.call_args.args[0] == org_id

    def test_no_preference_row_defaults_to_all_channels(self, db):
        from src.models import User

        org = make_org(db)
        user = User(email="user@test.com", organization_id=org.id, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org.id)

        mock_slack.assert_called_once()
        assert mock_slack.call_args.args[0] == org.id
        mock_discord.assert_called_once()
        assert mock_discord.call_args.args[0] == org.id
        mock_teams.assert_called_once()
        assert mock_teams.call_args.args[0] == org.id

    def test_counts_dict_includes_teams_key(self, db):
        from src.notification_dispatch import dispatch_health_drop_alert

        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=True, channel_teams=True)

        with patch("src.notification_dispatch._get_redis_client") as mock_redis:
            mock_redis.return_value.get.return_value = None
            with patch("src.notification_dispatch._check_org_plan") as mock_plan:
                mock_plan.return_value = True
                with patch("src.notification_dispatch._dispatch_slack_health_alert"):
                    with patch("src.notification_dispatch._dispatch_discord_health_alert"):
                        with patch("src.notification_dispatch._dispatch_teams_health_alert"):
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

        assert counts == {"inapp": 0, "slack": 1, "discord": 1, "teams": 1, "email": 0}