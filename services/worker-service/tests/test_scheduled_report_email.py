"""
Tests for the scheduled-report email renderer and sender (worker-email-delivery).

Report dict contract consumed by `render_scheduled_report_email`:

    {
        "organization_name": str,       # org name, appears in the subject
        "report_type": str,             # executive_summary | customer_health |
                                        # feature_prioritization | churn_risk
        "date_range_days": int,         # 7 | 30 | 90
        "title": str,                   # report title (top of the HTML body)
        "narrative": str | None,        # optional data-led summary paragraphs
        "sections": [
            {
                "heading": str,
                "data": {
                    "type": "table",    # columns + rows
                    "columns": [str, ...],
                    "rows": [[cell, ...], ...],
                } | {
                    "type": "series",   # one row per point, dict of label/value
                    "rows": [{str: scalar, ...}, ...],
                },
            },
            ...
        ],
    }
"""

from unittest.mock import MagicMock, patch

import pytest

from src.email import APP_URL
from src.services.scheduled_report_email import render_scheduled_report_email


def _table_report(**overrides):
    report = {
        "organization_name": "Acme Inc",
        "report_type": "executive_summary",
        "date_range_days": 30,
        "title": "Executive Summary — Aug 1 to Aug 30, 2026",
        "narrative": (
            "Feedback volume is up this period.\n\n"
            "Urgent items remain concentrated in onboarding."
        ),
        "sections": [
            {
                "heading": "Overview",
                "data": {
                    "type": "table",
                    "columns": ["Metric", "Value"],
                    "rows": [
                        ["Total Feedback", "142"],
                        ["Urgent Items", "9"],
                    ],
                },
            },
        ],
    }
    report.update(overrides)
    return report


def _series_report(**overrides):
    report = {
        "organization_name": "Acme Inc",
        "report_type": "customer_health",
        "date_range_days": 7,
        "title": "Customer Health Report — Aug 18 to Aug 25, 2026",
        "narrative": None,
        "sections": [
            {
                "heading": "Health Score Trends",
                "data": {
                    "type": "series",
                    "rows": [
                        {"date": "2026-08-18", "avg_score": 74.2},
                        {"date": "2026-08-25", "avg_score": 71.8},
                    ],
                },
            },
        ],
    }
    report.update(overrides)
    return report


class TestRendererSubject:
    """Subject format: `[<org name>] <Type label> report (<range label>)`."""

    @pytest.mark.parametrize(
        "report_type,label",
        [
            ("executive_summary", "Executive Summary"),
            ("customer_health", "Customer Health"),
            ("feature_prioritization", "Feature Prioritization"),
            ("churn_risk", "Churn Risk"),
        ],
    )
    def test_subject_uses_type_label(self, report_type, label):
        result = render_scheduled_report_email(_table_report(report_type=report_type))
        assert result["subject"] == f"[Acme Inc] {label} report (Last 30 days)"

    @pytest.mark.parametrize(
        "date_range_days,label",
        [
            (7, "Last 7 days"),
            (30, "Last 30 days"),
            (90, "Last 90 days"),
        ],
    )
    def test_subject_uses_range_label(self, date_range_days, label):
        result = render_scheduled_report_email(
            _table_report(date_range_days=date_range_days)
        )
        assert result["subject"] == f"[Acme Inc] Executive Summary report ({label})"

    def test_subject_capped_at_150_chars(self):
        report = _table_report(organization_name="A" * 300)
        result = render_scheduled_report_email(report)
        assert len(result["subject"]) <= 150


class TestRendererHtml:
    """HTML body: title, narrative, sections, footer."""

    def test_html_contains_title(self):
        result = render_scheduled_report_email(_table_report())
        assert "Executive Summary — Aug 1 to Aug 30, 2026" in result["html"]

    def test_html_contains_narrative_when_present(self):
        result = render_scheduled_report_email(_table_report())
        html = result["html"]
        assert "Feedback volume is up this period." in html
        assert "Urgent items remain concentrated in onboarding." in html

    def test_html_omits_narrative_when_none(self):
        result = render_scheduled_report_email(_table_report(narrative=None))
        html = result["html"]
        assert "None" not in html

    def test_table_section_renders_heading_columns_and_rows(self):
        result = render_scheduled_report_email(_table_report())
        html = result["html"]
        assert "Overview" in html
        assert "Metric" in html and "Value" in html
        assert "Total Feedback" in html and "142" in html
        assert "Urgent Items" in html and "9" in html

    def test_series_section_renders_heading_and_row_values(self):
        result = render_scheduled_report_email(_series_report())
        html = result["html"]
        assert "Health Score Trends" in html
        assert "2026-08-18" in html and "74.2" in html
        assert "2026-08-25" in html and "71.8" in html

    def test_footer_links_reports_page(self):
        result = render_scheduled_report_email(_table_report())
        html = result["html"]
        assert f'href="{APP_URL}/reports"' in html

    def test_footer_links_notification_settings(self):
        result = render_scheduled_report_email(_table_report())
        html = result["html"]
        assert f'href="{APP_URL}/settings/notifications"' in html

    def test_footer_states_view_full_report_for_charts(self):
        result = render_scheduled_report_email(_table_report())
        assert "view the full report for charts" in result["html"].lower()


class TestRendererEdgeCases:
    """Defensive rendering: unknown shapes, escaping."""

    def test_unknown_data_shape_renders_fallback_without_raising(self):
        report = _table_report(
            sections=[
                {
                    "heading": "Mystery Section",
                    "data": {"type": "pie", "slices": [{"label": "x", "value": 1}]},
                }
            ]
        )
        result = render_scheduled_report_email(report)
        assert "Mystery Section" in result["html"]

    def test_section_with_no_data_renders_fallback_without_raising(self):
        report = _table_report(sections=[{"heading": "Empty Section"}])
        result = render_scheduled_report_email(report)
        assert "Empty Section" in result["html"]

    def test_no_sections_key_does_not_raise(self):
        report = _table_report()
        del report["sections"]
        result = render_scheduled_report_email(report)
        assert result["subject"]

    def test_escapes_user_derived_section_text(self):
        malicious = "<script>alert('xss')</script> & \"quoted\" 'single'"
        report = _table_report(
            sections=[
                {
                    "heading": "Top Pain Points",
                    "data": {
                        "type": "table",
                        "columns": ["Category", "Count"],
                        "rows": [[malicious, "1"]],
                    },
                },
                {
                    "heading": "Trend",
                    "data": {
                        "type": "series",
                        "rows": [{"date": "2026-08-25", "avg_score": malicious}],
                    },
                },
            ]
        )
        result = render_scheduled_report_email(report)
        html = result["html"]
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html
        assert "&quot;" in html
        assert "&#x27;" in html


class TestSendScheduledReportEmail:
    """Sender: BYOK Resend path, delegating to _send_email."""

    @patch("src.email.RESEND_API_KEY", None)
    @patch("src.email.requests.post")
    def test_no_key_returns_false_and_does_not_call_resend(self, mock_post):
        from src.email import send_scheduled_report_email

        result = send_scheduled_report_email(
            "ops@acme.com",
            "Acme Inc",
            "[Acme Inc] Executive Summary report (Last 30 days)",
            "<h1>Executive Summary</h1>",
        )

        assert result is False
        mock_post.assert_not_called()

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email.requests.post")
    def test_mocked_200_returns_true_with_correct_payload(self, mock_post):
        from src.email import send_scheduled_report_email

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = send_scheduled_report_email(
            "ops@acme.com",
            "Acme Inc",
            "[Acme Inc] Executive Summary report (Last 30 days)",
            "<h1>Executive Summary</h1>",
        )

        assert result is True
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["to"] == ["ops@acme.com"]
        assert payload["subject"] == "[Acme Inc] Executive Summary report (Last 30 days)"
        assert payload["html"] == "<h1>Executive Summary</h1>"

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email.requests.post")
    def test_mocked_5xx_returns_false(self, mock_post):
        from src.email import send_scheduled_report_email

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "boom"
        mock_post.return_value = mock_response

        result = send_scheduled_report_email(
            "ops@acme.com",
            "Acme Inc",
            "[Acme Inc] Executive Summary report (Last 30 days)",
            "<h1>Executive Summary</h1>",
        )

        assert result is False
        mock_post.assert_called_once()