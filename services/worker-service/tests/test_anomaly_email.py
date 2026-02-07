"""
Tests for anomaly alert email sending.
"""

from unittest.mock import patch, MagicMock

from src.email import send_anomaly_alert_email


class TestSendAnomalyAlertEmail:
    """Tests for send_anomaly_alert_email."""

    @patch("src.email._send_with_template")
    def test_sends_with_correct_template_and_variables(self, mock_send):
        """Should call _send_with_template with anomaly alert template and all variables."""
        mock_send.return_value = True

        with patch("src.email.TEMPLATE_ANOMALY_ALERT", "tmpl_anomaly_123"):
            result = send_anomaly_alert_email(
                to_email="user@test.com",
                organization_name="Test Corp",
                severity="CRITICAL",
                current_negative_pct="55",
                baseline_negative_pct="15",
                deviation_pct="40",
                feedback_count="50",
            )

        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to"] == "user@test.com"
        assert call_kwargs["template_id"] == "tmpl_anomaly_123"
        variables = call_kwargs["variables"]
        assert variables["ORGANIZATION_NAME"] == "Test Corp"
        assert variables["SEVERITY"] == "CRITICAL"
        assert variables["CURRENT_NEGATIVE_PCT"] == "55"
        assert variables["BASELINE_NEGATIVE_PCT"] == "15"
        assert variables["DEVIATION_PCT"] == "40"
        assert variables["FEEDBACK_COUNT"] == "50"
        assert "DASHBOARD_URL" in variables
        assert "SETTINGS_URL" in variables

    @patch("src.email._send_with_template")
    def test_includes_dashboard_and_settings_urls(self, mock_send):
        """Should include dashboard and settings URLs in template variables."""
        mock_send.return_value = True

        with patch("src.email.TEMPLATE_ANOMALY_ALERT", "tmpl_123"), \
             patch("src.email.APP_URL", "https://app.rereflect.ca"):
            send_anomaly_alert_email(
                to_email="user@test.com",
                organization_name="Corp",
                severity="WARNING",
                current_negative_pct="30",
                baseline_negative_pct="10",
                deviation_pct="20",
                feedback_count="25",
            )

        variables = mock_send.call_args.kwargs["variables"]
        assert variables["DASHBOARD_URL"] == "https://app.rereflect.ca/dashboard"
        assert variables["SETTINGS_URL"] == "https://app.rereflect.ca/settings/preferences"

    @patch("src.email._send_with_template")
    def test_returns_false_when_template_not_configured(self, mock_send):
        """Should return False when TEMPLATE_ANOMALY_ALERT is not set."""
        mock_send.return_value = False

        with patch("src.email.TEMPLATE_ANOMALY_ALERT", None):
            result = send_anomaly_alert_email(
                to_email="user@test.com",
                organization_name="Corp",
                severity="WARNING",
                current_negative_pct="30",
                baseline_negative_pct="10",
                deviation_pct="20",
                feedback_count="25",
            )

        assert result is False
