"""
TDD tests for Discord alert support (Track B — worker-service).

Covers:
- send_discord_message_webhook() in src/tasks/alerts.py (B1)
- Discord embed builder + dispatch at all three alert sites (B2/B3)

Per THE CONTRACT (docs/planning/discord-notifications/alert-pipe/spec.md):
worker-service's sender RAISES on failure (unlike the backend-api sender, which
catches and returns {"success": False}). That asymmetry is deliberate — mirror
send_slack_message_webhook (raising), not the backend's send_discord_message.
"""
import httpx
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# B1 — send_discord_message_webhook()
# ---------------------------------------------------------------------------

class TestSendDiscordMessageWebhook:
    """Tests for send_discord_message_webhook() in src/tasks/alerts.py."""

    def test_posts_content_and_embeds_to_webhook_url(self):
        from src.tasks.alerts import send_discord_message_webhook

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock(status_code=204)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            embeds = [{"title": "Urgent feedback", "color": 15548997}]
            result = send_discord_message_webhook(
                "https://discord.com/api/webhooks/123/abc",
                embeds,
                "Rereflect: urgent feedback",
            )

            mock_client.post.assert_called_once()
            call_args, call_kwargs = mock_client.post.call_args
            assert call_args[0] == "https://discord.com/api/webhooks/123/abc"

            payload = call_kwargs["json"]
            # THE CONTRACT: body must always carry both content and embeds,
            # or Discord returns 400.
            assert payload["content"] == "Rereflect: urgent feedback"
            assert payload["embeds"] == embeds

            mock_response.raise_for_status.assert_called_once()
            assert result["success"] is True
            assert result["status_code"] == 204

    def test_raises_on_http_error_nothing_caught(self):
        """The worker sender must RAISE on failure — the opposite of the backend sender."""
        from src.tasks.alerts import send_discord_message_webhook

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock(status_code=400)
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request", request=MagicMock(), response=mock_response
            )
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                send_discord_message_webhook(
                    "https://discord.com/api/webhooks/123/abc", [], "content"
                )

    def test_content_is_a_required_positional_argument(self):
        """Matches the contract: content has no default, unlike the backend sender."""
        import inspect
        from src.tasks.alerts import send_discord_message_webhook

        sig = inspect.signature(send_discord_message_webhook)
        params = list(sig.parameters.values())
        assert [p.name for p in params] == ["webhook_url", "embeds", "content"]
        for p in params:
            assert p.default is inspect.Parameter.empty
