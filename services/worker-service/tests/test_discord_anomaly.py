"""
TDD tests for Discord dispatch of sentiment anomaly alerts.

tasks/anomaly.py::_send_anomaly_slack (~:219) is NOT wired into
notification_dispatch.py (that routing moved to notification_dispatch.dispatch_alert
per TestDispatchAnomalyAlerts) and is easy to forget when adding Discord support.
This adds its Discord counterpart, _send_anomaly_discord, patched at the import site
(src.tasks.anomaly.send_discord_message_webhook) since anomaly.py imports it at
module top.
"""
from unittest.mock import patch, MagicMock

from src.models import Organization, Integration


def make_org(db) -> Organization:
    org = Organization(name="Anomaly Discord Corp", plan="pro")
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


def make_anomaly(severity="warning"):
    return MagicMock(
        id=123,
        severity=severity,
        current_negative_pct=40.0,
        baseline_negative_pct=10.0,
        deviation_pct=30.0,
        feedback_count=10,
    )


class TestSendAnomalyDiscord:
    """Tests for _send_anomaly_discord() in src/tasks/anomaly.py."""

    def test_sends_content_and_embeds_to_active_discord_integration(self, db):
        from src.tasks.anomaly import _send_anomaly_discord

        org = make_org(db)
        make_discord_integration(db, org.id)
        anomaly = make_anomaly()

        with patch("src.tasks.anomaly.send_discord_message_webhook") as mock_send:
            _send_anomaly_discord(db, org, anomaly)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["webhook_url"] == "https://discord.com/api/webhooks/1/abc"

        # THE CONTRACT: body must carry both content and embeds.
        assert call_kwargs["content"]
        embeds = call_kwargs["embeds"]
        assert len(embeds) >= 1
        embed = embeds[0]
        assert isinstance(embed["color"], int)
        assert "40" in embed["description"] or "40" in str(embed)

    def test_no_discord_integrations_is_a_noop(self, db):
        from src.tasks.anomaly import _send_anomaly_discord

        org = make_org(db)
        anomaly = make_anomaly()

        with patch("src.tasks.anomaly.send_discord_message_webhook") as mock_send:
            _send_anomaly_discord(db, org, anomaly)

        mock_send.assert_not_called()

    def test_ignores_slack_and_inactive_integrations(self, db):
        from src.tasks.anomaly import _send_anomaly_discord

        org = make_org(db)
        db.add(Integration(
            organization_id=org.id, type="slack",
            config={"webhook_url": "https://hooks.slack.com/services/x"}, is_active=True,
        ))
        make_discord_integration(db, org.id, is_active=False)
        db.commit()
        anomaly = make_anomaly()

        with patch("src.tasks.anomaly.send_discord_message_webhook") as mock_send:
            _send_anomaly_discord(db, org, anomaly)

        mock_send.assert_not_called()

    def test_failure_on_one_integration_does_not_abort_the_others(self, db):
        from src.tasks.anomaly import _send_anomaly_discord

        org = make_org(db)
        make_discord_integration(db, org.id, webhook_url="https://discord.com/api/webhooks/1/fail")
        make_discord_integration(db, org.id, webhook_url="https://discord.com/api/webhooks/2/ok")
        anomaly = make_anomaly(severity="critical")

        def side_effect(**kwargs):
            if kwargs["webhook_url"].endswith("/fail"):
                raise Exception("Discord 400: missing embeds")
            return {"success": True}

        with patch("src.tasks.anomaly.send_discord_message_webhook", side_effect=side_effect) as mock_send:
            # Must not raise — failure of one integration is caught, logged, and
            # does not abort the others.
            _send_anomaly_discord(db, org, anomaly)

        assert mock_send.call_count == 2
