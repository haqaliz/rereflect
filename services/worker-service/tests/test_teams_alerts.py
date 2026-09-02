"""
TDD tests for Teams alert support (worker-service).

Covers:
- send_teams_message_webhook() in src/tasks/alerts.py

Per THE CONTRACT (docs/planning/teams-notifications/worker-dispatch/spec.md):
worker-service's sender RAISES on failure (response.raise_for_status(), nothing
caught here) — mirror send_discord_message_webhook / send_slack_message_webhook
(raising), NOT the backend-api sender of the same name (which catches and
returns {"success": False}). The MessageCard body must match the backend's
build_teams_message_card shape exactly (worker cannot import backend-api, so the
shape is duplicated deliberately and pinned here).
"""
import httpx
import pytest
from unittest.mock import patch, MagicMock


class TestSendTeamsMessageWebhook:
    """Tests for send_teams_message_webhook() in src/tasks/alerts.py."""

    def test_posts_message_card_to_webhook_url(self):
        from src.tasks.alerts import send_teams_message_webhook

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock(status_code=200)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            result = send_teams_message_webhook(
                "https://outlook.office.com/webhook/123/abc",
                "Customer health drop: john@acme.com",
                "Health score dropped from 65 to 42 (moderate to at_risk).",
                summary="Customer health drop: john@acme.com",
            )

            mock_client_cls.assert_called_once_with(timeout=10)
            mock_client.post.assert_called_once()
            call_args, call_kwargs = mock_client.post.call_args
            assert call_args[0] == "https://outlook.office.com/webhook/123/abc"

            payload = call_kwargs["json"]
            # MessageCard shape — pinned to the backend's build_teams_message_card.
            assert payload["@type"] == "MessageCard"
            assert payload["@context"] == "http://schema.org/extensions"
            assert payload["summary"] == "Customer health drop: john@acme.com"
            assert payload["title"] == "Customer health drop: john@acme.com"
            assert "65" in payload["text"]
            assert payload["themeColor"] == "6264A7"

            mock_response.raise_for_status.assert_called_once()
            assert result["success"] is True
            assert result["status_code"] == 200

    def test_summary_defaults_to_title_when_omitted(self):
        """Same shape as the backend's build_teams_message_card: summary falls
        back to title, so the card is never rendered without a summary."""
        from src.tasks.alerts import send_teams_message_webhook

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock(status_code=200)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            send_teams_message_webhook(
                "https://outlook.office.com/webhook/123/abc",
                "Customer health drop: john@acme.com",
                "Health score dropped from 65 to 42.",
            )

            payload = mock_client.post.call_args.kwargs["json"]
            assert payload["summary"] == "Customer health drop: john@acme.com"

    def test_raises_on_http_error_nothing_caught(self):
        """The worker sender must RAISE on failure — the opposite of the backend sender."""
        from src.tasks.alerts import send_teams_message_webhook

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock(status_code=400)
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request", request=MagicMock(), response=mock_response
            )
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                send_teams_message_webhook(
                    "https://outlook.office.com/webhook/123/abc",
                    "Title",
                    "Text",
                )

    def test_signature_requires_webhook_url_title_text_summary_optional(self):
        """summary is the only optional parameter — title and text are required."""
        import inspect
        from src.tasks.alerts import send_teams_message_webhook

        sig = inspect.signature(send_teams_message_webhook)
        params = list(sig.parameters.values())
        assert [p.name for p in params] == ["webhook_url", "title", "text", "summary"]
        for p in params[:3]:
            assert p.default is inspect.Parameter.empty
        assert params[3].default == ""