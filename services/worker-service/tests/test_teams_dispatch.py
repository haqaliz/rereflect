"""
TDD tests for Teams dispatch at the main alert pipe.

notification_dispatch.py::_dispatch_teams_alert sends a MessageCard (title +
text) to the org's active Teams webhook integrations, mirroring
_dispatch_discord_alert — same gating (Integration.type == "teams",
is_active), last_used_at / error_count / last_error bookkeeping per
integration, per-integration failure isolation (never raises out of the
dispatch).

dispatch_alert() must dispatch Slack, Discord and Teams independently, each off
its own channel preference — no piggybacking on the Slack toggle.
"""
from unittest.mock import patch, MagicMock

from src.models import Organization, Integration


def make_org(db) -> Organization:
    org = Organization(name="Teams Corp", plan="pro")
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


class TestDispatchTeamsAlert:
    """Tests for _dispatch_teams_alert() in notification_dispatch.py."""

    def test_sends_message_card_to_active_teams_integrations(self, db):
        from src.notification_dispatch import _dispatch_teams_alert

        org = make_org(db)
        make_teams_integration(db, org.id)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook") as mock_send:
                _dispatch_teams_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent feedback from acme@example.com",
                    message="Customer reported a billing bug.",
                    link="/feedbacks/123",
                )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["webhook_url"] == "https://outlook.office.com/webhook/1/abc"
        assert call_kwargs["title"] == "Urgent feedback from acme@example.com"
        assert "Customer reported a billing bug." in call_kwargs["text"]
        assert "/feedbacks/123" in call_kwargs["text"]

    def test_ignores_inactive_teams_integrations(self, db):
        from src.notification_dispatch import _dispatch_teams_alert

        org = make_org(db)
        make_teams_integration(db, org.id, is_active=False)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook") as mock_send:
                _dispatch_teams_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent",
                    message="msg",
                    link=None,
                )

        mock_send.assert_not_called()

    def test_ignores_slack_integrations(self, db):
        """Only Integration.type == 'teams' rows are dispatched to."""
        from src.notification_dispatch import _dispatch_teams_alert

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

            with patch("src.notification_dispatch.send_teams_message_webhook") as mock_send:
                _dispatch_teams_alert(
                    org_id=org.id,
                    alert_type="urgent_feedback",
                    title="Urgent",
                    message="msg",
                    link=None,
                )

        mock_send.assert_not_called()

    def test_success_writes_back_last_used_at_and_clears_error(self, db):
        from src.notification_dispatch import _dispatch_teams_alert

        org = make_org(db)
        integ = make_teams_integration(db, org.id)
        integ.error_count = 3
        integ.last_error = "previous failure"
        db.commit()

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook", return_value={"success": True}):
                _dispatch_teams_alert(
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
        """A raising Teams send is caught per-integration, logged, and does not
        abort the others — one integration fails, the next still gets a send attempt."""
        from src.notification_dispatch import _dispatch_teams_alert

        org = make_org(db)
        failing = make_teams_integration(db, org.id, webhook_url="https://outlook.office.com/webhook/1/fail")
        healthy = make_teams_integration(db, org.id, webhook_url="https://outlook.office.com/webhook/2/ok")

        def side_effect(**kwargs):
            if kwargs["webhook_url"].endswith("/fail"):
                raise Exception("Teams 400: bad webhook")
            return {"success": True}

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook", side_effect=side_effect) as mock_send:
                _dispatch_teams_alert(
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
        assert "Teams 400" in failing.last_error

        assert healthy.error_count == 0
        assert healthy.last_error is None
        assert healthy.last_used_at is not None

    def test_no_teams_integrations_is_a_noop(self, db):
        from src.notification_dispatch import _dispatch_teams_alert

        org = make_org(db)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch.send_teams_message_webhook") as mock_send:
                _dispatch_teams_alert(
                    org_id=org.id,
                    alert_type="volume_spike",
                    title="Volume spike",
                    message="msg",
                    link=None,
                )

        mock_send.assert_not_called()


class TestDispatchAlertTriggersTeams:
    """dispatch_alert() must dispatch Slack, Discord and Teams independently,
    each off its own channel preference — no piggybacking on the Slack toggle."""

    def _make_user_pref(self, db, channel_slack: bool, channel_discord: bool, channel_teams: bool) -> int:
        from src.models import User, UserAlertPreference

        org = make_org(db)
        user = User(email="user@test.com", organization_id=org.id, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)

        pref = UserAlertPreference(
            user_id=user.id,
            alert_type="urgent_feedback",
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
        from src.notification_dispatch import dispatch_alert

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch._dispatch_slack_alert") as mock_slack:
                with patch("src.notification_dispatch._dispatch_discord_alert") as mock_discord:
                    with patch("src.notification_dispatch._dispatch_teams_alert") as mock_teams:
                        dispatch_alert(
                            org_id=org_id,
                            alert_type="urgent_feedback",
                            title="Urgent feedback",
                            message="msg",
                            link="/feedbacks/1",
                        )

        return mock_slack, mock_discord, mock_teams

    def test_slack_only_preference_skips_teams_dispatch(self, db):
        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=False, channel_teams=False)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_called_once()
        mock_discord.assert_not_called()
        mock_teams.assert_not_called()

    def test_teams_only_preference_skips_slack_and_discord_dispatch(self, db):
        org_id = self._make_user_pref(db, channel_slack=False, channel_discord=False, channel_teams=True)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_not_called()
        mock_discord.assert_not_called()
        mock_teams.assert_called_once()

    def test_all_channels_enabled_dispatches_all(self, db):
        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=True, channel_teams=True)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org_id)

        mock_slack.assert_called_once()
        mock_discord.assert_called_once()
        mock_teams.assert_called_once()

    def test_no_preference_row_defaults_to_all_channels(self, db):
        from src.models import User

        org = make_org(db)
        user = User(email="user@test.com", organization_id=org.id, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)

        mock_slack, mock_discord, mock_teams = self._dispatch_with_mocks(db, org.id)

        mock_slack.assert_called_once()
        mock_discord.assert_called_once()
        mock_teams.assert_called_once()

    def test_counts_dict_includes_teams_key(self, db):
        from src.notification_dispatch import dispatch_alert

        org_id = self._make_user_pref(db, channel_slack=True, channel_discord=True, channel_teams=True)

        with patch("src.notification_dispatch.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.notification_dispatch._dispatch_slack_alert"):
                with patch("src.notification_dispatch._dispatch_discord_alert"):
                    with patch("src.notification_dispatch._dispatch_teams_alert"):
                        counts = dispatch_alert(
                            org_id=org_id,
                            alert_type="urgent_feedback",
                            title="Urgent feedback",
                            message="msg",
                            link="/feedbacks/1",
                        )

        assert counts == {"inapp": 0, "slack": 1, "discord": 1, "teams": 1, "email": 0}