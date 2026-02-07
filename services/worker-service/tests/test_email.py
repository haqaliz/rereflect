"""
Tests for the worker service email module.
"""

from unittest.mock import patch, MagicMock
from src.email import _render_template, _is_email_enabled, _send_with_template, send_weekly_digest_email


class TestRenderTemplate:
    """Tests for template variable rendering."""

    def test_replaces_triple_brace_variables(self):
        """Should replace {{{VAR}}} with actual values."""
        html = "<p>Hello {{{NAME}}}, your org is {{{ORG}}}</p>"
        subject = "Report for {{{ORG}}}"

        rendered_html, rendered_subject = _render_template(html, subject, {
            "NAME": "Alice",
            "ORG": "Acme Inc",
        })

        assert rendered_html == "<p>Hello Alice, your org is Acme Inc</p>"
        assert rendered_subject == "Report for Acme Inc"

    def test_replaces_numeric_values(self):
        """Should convert integers to strings in template."""
        html = "Total: {{{COUNT}}} items, {{{PERCENT}}}%"

        rendered_html, _ = _render_template(html, "", {
            "COUNT": 42,
            "PERCENT": 85,
        })

        assert rendered_html == "Total: 42 items, 85%"

    def test_leaves_unmatched_variables(self):
        """Variables not in dict should remain unchanged."""
        html = "Hello {{{NAME}}}, balance: {{{BALANCE}}}"

        rendered_html, _ = _render_template(html, "", {"NAME": "Bob"})

        assert "Bob" in rendered_html
        assert "{{{BALANCE}}}" in rendered_html


class TestIsEmailEnabled:
    """Tests for email enabled check."""

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    def test_enabled_when_key_set(self):
        """Should return True when RESEND_API_KEY is set."""
        assert _is_email_enabled() is True

    @patch("src.email.RESEND_API_KEY", None)
    def test_disabled_when_key_missing(self):
        """Should return False when RESEND_API_KEY is not set."""
        assert _is_email_enabled() is False

    @patch("src.email.RESEND_API_KEY", "")
    def test_disabled_when_key_empty(self):
        """Should return False when RESEND_API_KEY is empty string."""
        assert _is_email_enabled() is False


class TestSendWithTemplate:
    """Tests for template-based email sending."""

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email._get_template")
    @patch("src.email._send_email")
    def test_sends_rendered_email(self, mock_send, mock_get_template):
        """Should fetch template, render variables, and send."""
        mock_get_template.return_value = (
            "<h1>Hello {{{NAME}}}</h1>",
            "Welcome {{{NAME}}}",
        )
        mock_send.return_value = True

        result = _send_with_template("user@test.com", "tmpl_123", {"NAME": "Alice"})

        assert result is True
        mock_send.assert_called_once_with(
            "user@test.com",
            "Welcome Alice",
            "<h1>Hello Alice</h1>",
        )

    def test_returns_false_when_template_id_missing(self):
        """Should return False when template_id is None."""
        result = _send_with_template("user@test.com", None, {})

        assert result is False

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email._get_template")
    def test_returns_false_when_template_fetch_fails(self, mock_get_template):
        """Should return False when template cannot be fetched."""
        mock_get_template.return_value = None

        result = _send_with_template("user@test.com", "tmpl_bad", {})

        assert result is False


class TestSendWeeklyDigestEmail:
    """Tests for the send_weekly_digest_email function."""

    @patch("src.email._send_with_template")
    def test_passes_all_variables(self, mock_send_template):
        """Should pass all digest stats as template variables."""
        mock_send_template.return_value = True

        result = send_weekly_digest_email(
            to_email="user@test.com",
            organization_name="Acme",
            week_date="Jan 27 - Feb 03, 2026",
            total_feedback=50,
            pain_points=10,
            feature_requests=5,
            positive_percent=60,
            neutral_percent=25,
            negative_percent=15,
            urgent_count=3,
        )

        assert result is True
        mock_send_template.assert_called_once()
        call_args = mock_send_template.call_args
        variables = call_args.kwargs.get("variables") or call_args[1].get("variables") or call_args[0][2]

        assert variables["ORGANIZATION_NAME"] == "Acme"
        assert variables["TOTAL_FEEDBACK"] == 50
        assert variables["PAIN_POINTS"] == 10
        assert variables["FEATURE_REQUESTS"] == 5
        assert variables["POSITIVE_PERCENT"] == 60
        assert variables["NEUTRAL_PERCENT"] == 25
        assert variables["NEGATIVE_PERCENT"] == 15
        assert variables["URGENT_COUNT"] == 3
        assert "/dashboard" in variables["DASHBOARD_URL"]
        assert "/settings/preferences" in variables["UNSUBSCRIBE_URL"]
