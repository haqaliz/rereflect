"""
scheduled_report_email — HTML renderer for scheduled AI reports (worker).

Renders a generated report dict into a plain-HTML email body, following the
worker's raw `_send_email` path (BYOK Resend, no template — mirrors
`send_deletion_request_email`). The operator's template registry is not
required to change.

Report dict contract (produced by the scheduled-generation aspect):

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

Charts are NOT rendered in email: chart sections carry their underlying data
(table/series), which is what this renderer shows, and the footer says so
honestly ("view the full report for charts"). All user-derived text values are
HTML-escaped before embedding.
"""

import html
from typing import Any, Dict

from src.email import APP_URL

REPORT_TYPE_LABELS: Dict[str, str] = {
    "executive_summary": "Executive Summary",
    "customer_health": "Customer Health",
    "feature_prioritization": "Feature Prioritization",
    "churn_risk": "Churn Risk",
}

DATE_RANGE_LABELS: Dict[int, str] = {
    7: "Last 7 days",
    30: "Last 30 days",
    90: "Last 90 days",
}

SUBJECT_MAX_LENGTH = 150

_FALLBACK_NOTE = (
    "This data is not available in email — view the full report for charts."
)


def _escape(value: Any) -> str:
    """HTML-escape user-derived text values (feedback content, customer data)."""
    return html.escape(str(value), quote=True)


def _type_label(report_type: str) -> str:
    return REPORT_TYPE_LABELS.get(report_type, report_type.replace("_", " ").title())


def _range_label(date_range_days: Any) -> str:
    try:
        days = int(date_range_days)
    except (TypeError, ValueError):
        days = 30
    return DATE_RANGE_LABELS.get(days, f"Last {days} days")


def _render_table(data: Dict[str, Any]) -> str:
    columns = data.get("columns") or []
    rows = data.get("rows") or []

    head = "".join(f"<th>{_escape(c)}</th>" for c in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_escape(c)}</td>" for c in (row or []))
        body_rows.append(f"<tr>{cells}</tr>")

    return (
        "<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\" "
        "style=\"border-collapse:collapse;font-size:14px;width:100%;\">"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def _render_series(data: Dict[str, Any]) -> str:
    rows = data.get("rows") or []
    items = []
    for row in rows:
        if isinstance(row, dict):
            pairs = ", ".join(
                f"{_escape(key)}: {_escape(value)}" for key, value in row.items()
            )
        else:
            pairs = _escape(row)
        items.append(f"<li>{pairs}</li>")
    return f"<ul>{''.join(items)}</ul>"


def _render_section(section: Dict[str, Any]) -> str:
    heading = section.get("heading") or "Section"
    data = section.get("data") or {}
    data_type = data.get("type")

    if data_type == "table":
        body = _render_table(data)
    elif data_type == "series":
        body = _render_series(data)
    else:
        body = f"<p><em>{_escape(_FALLBACK_NOTE)}</em></p>"

    return (
        "<section style=\"margin-bottom:24px;\">"
        f"<h2 style=\"font-size:16px;margin-bottom:8px;\">{_escape(heading)}</h2>"
        f"{body}</section>"
    )


def _render_sections(sections: Any) -> str:
    if not isinstance(sections, list):
        return ""
    return "".join(_render_section(s) for s in sections if isinstance(s, dict))


def render_scheduled_report_email(report: Dict[str, Any]) -> Dict[str, str]:
    """Render a report dict into `{"subject": str, "html": str}` for _send_email."""
    organization_name = report.get("organization_name", "")
    report_type = report.get("report_type", "executive_summary")
    date_range_days = report.get("date_range_days", 30)

    subject = (
        f"[{organization_name}] {_type_label(report_type)} report "
        f"({_range_label(date_range_days)})"
    )
    subject = subject[:SUBJECT_MAX_LENGTH]

    title = report.get("title") or (
        f"{_type_label(report_type)} report ({_range_label(date_range_days)})"
    )

    narrative_html = ""
    narrative = report.get("narrative")
    if narrative:
        paragraphs = "".join(
            f"<p style=\"font-size:14px;line-height:1.6;\">{_escape(p)}</p>"
            for p in str(narrative).split("\n\n")
        )
        narrative_html = (
            "<div style=\"margin-bottom:24px;\">"
            f"{paragraphs}</div>"
        )

    footer = (
        "<hr style=\"border:none;border-top:1px solid #e5e5e5;margin:32px 0 16px;\"/>"
        "<p style=\"font-size:12px;color:#666;\">"
        "This email shows tables and lists — "
        "<strong>view the full report for charts</strong>."
        "</p>"
        "<p style=\"font-size:12px;color:#666;\">"
        f"<a href=\"{APP_URL}/reports\">Reports</a>"
        " &middot; "
        f"<a href=\"{APP_URL}/settings/notifications\">Notification settings</a>"
        "</p>"
    )

    html_body = (
        "<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',"
        "Roboto,sans-serif;color:#1a1a1a;max-width:640px;margin:0 auto;\">"
        f"<h1 style=\"font-size:20px;margin-bottom:16px;\">{_escape(title)}</h1>"
        f"{narrative_html}"
        f"{_render_sections(report.get('sections'))}"
        f"{footer}</div>"
    )

    return {"subject": subject, "html": html_body}