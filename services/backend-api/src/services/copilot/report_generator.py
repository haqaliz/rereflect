"""
Report Generator — generates structured report data for On-Demand AI Reports (M2.4).

Supports 4 report types:
- executive_summary: High-level overview for leadership
- customer_health:   Per-cohort customer health for CS teams
- feature_prioritization: Data-driven feature prioritization for product teams
- churn_risk:        Deep dive into churn signals

Each _build_* method returns:
    {"title": str, "sections": [{"heading", "narrative", "data", "chart"}, ...]}

Each _query_* method returns raw data dicts for use in section building and LLM prompts.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Report type keywords ──────────────────────────────────────────────────────

_EXECUTIVE_PATTERNS = [
    r"\bexecutive\b",
    r"\bsummary\b",
    r"\boverview\b",
    r"\bmonthly\s+summary\b",
    r"\bweekly\s+summary\b",
    r"\bquarterly\s+review\b",  # only if not also matching churn/health/feature
]

_HEALTH_PATTERNS = [
    r"\bcustomer\s+health\b",
    r"\bhealth\s+report\b",
    r"\bhealth\s+score\b",
    r"\bhealth\b",
]

_FEATURE_PATTERNS = [
    r"\bfeature\s+request\b",
    r"\bfeature\b",
    r"\bprioritiz",
    r"\bpriorities\b",
]

_CHURN_PATTERNS = [
    r"\bchurn\b",
    r"\battrition\b",
    r"\brisk\s+analysis\b",
]

# ── Date range keywords ───────────────────────────────────────────────────────

_DATE_7_PATTERNS = [
    r"\blast\s+7\s+days?\b",
    r"\bthis\s+week\b",
    r"\bpast\s+7\s+days?\b",
]

_DATE_30_PATTERNS = [
    r"\blast\s+30\s+days?\b",
    r"\bthis\s+month\b",
    r"\bpast\s+30\s+days?\b",
    r"\blast\s+month\b",
]

_DATE_90_PATTERNS = [
    r"\blast\s+90\s+days?\b",
    r"\bthis\s+quarter\b",
    r"\bquarterly\b",
    r"\bpast\s+90\s+days?\b",
    r"\blast\s+quarter\b",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


class ReportGenerator:
    """
    Generates structured report data by querying the database.

    Usage:
        generator = ReportGenerator()
        result = generator._build_executive_summary(db, org_id, 30)
        # result = {"title": "...", "sections": [...]}
    """

    # ── Public helpers ────────────────────────────────────────────────────────

    def extract_report_type(self, query: str) -> str:
        """
        Extract the report type from a natural-language query.

        Returns one of: executive_summary | customer_health |
                        feature_prioritization | churn_risk
        """
        q = query.lower()

        if _matches_any(q, _CHURN_PATTERNS):
            return "churn_risk"
        if _matches_any(q, _HEALTH_PATTERNS):
            return "customer_health"
        if _matches_any(q, _FEATURE_PATTERNS):
            return "feature_prioritization"
        # executive / summary / overview / quarterly → executive_summary
        return "executive_summary"

    def extract_date_range(self, query: str) -> int:
        """
        Extract the date range (in days) from a natural-language query.

        Returns 7, 30, or 90. Defaults to 30.
        """
        if _matches_any(query, _DATE_7_PATTERNS):
            return 7
        if _matches_any(query, _DATE_90_PATTERNS):
            return 90
        if _matches_any(query, _DATE_30_PATTERNS):
            return 30
        return 30

    # ── Entry point ───────────────────────────────────────────────────────────

    def generate(
        self,
        db: Session,
        org_id: int,
        report_type: str,
        date_range_days: int,
        stream_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Generate a full report dict without LLM (data-only).

        Returns:
            {"title": str, "sections": [...]}
        """
        builders = {
            "executive_summary": self._build_executive_summary,
            "customer_health": self._build_customer_health,
            "feature_prioritization": self._build_feature_prioritization,
            "churn_risk": self._build_churn_risk,
        }
        builder = builders.get(report_type, self._build_executive_summary)
        return builder(db, org_id, date_range_days)

    # ── Build methods (return {title, sections}) ──────────────────────────────

    def _build_executive_summary(self, db: Session, org_id: int, date_range_days: int) -> dict:
        data = self._query_executive_summary_data(db, org_id, date_range_days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=date_range_days)
        title = (
            f"Executive Summary — "
            f"{start_date.strftime('%b %-d')} to {end_date.strftime('%b %-d, %Y')}"
        )
        sections = [
            {
                "heading": "Overview",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Metric", "Value"],
                    "rows": [
                        ["Total Feedback", data["total_feedback"]],
                        ["Urgent Items", data["urgent_count"]],
                        ["At-Risk Customers", data["at_risk_count"]],
                    ],
                },
                "chart": None,
            },
            {
                "heading": "Sentiment Analysis",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Sentiment", "Count"],
                    "rows": [[row["sentiment_label"], row["count"]] for row in data["sentiment_distribution"]],
                },
                "chart": {"type": "pie", "data": data["sentiment_distribution"]},
            },
            {
                "heading": "Top Pain Points",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Category", "Count"],
                    "rows": [[row["category"], row["count"]] for row in data["top_pain_points"]],
                },
                "chart": None,
            },
            {
                "heading": "Feature Requests",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Category", "Count"],
                    "rows": [[row["category"], row["count"]] for row in data["top_feature_requests"]],
                },
                "chart": None,
            },
        ]
        return {"title": title, "sections": sections}

    def _build_customer_health(self, db: Session, org_id: int, date_range_days: int) -> dict:
        data = self._query_customer_health_data(db, org_id, date_range_days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=date_range_days)
        title = (
            f"Customer Health Report — "
            f"{start_date.strftime('%b %-d')} to {end_date.strftime('%b %-d, %Y')}"
        )
        sections = [
            {
                "heading": "Health Distribution",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Risk Level", "Count"],
                    "rows": [[row["risk_level"], row["count"]] for row in data["health_distribution"]],
                },
                "chart": {"type": "donut", "data": data["health_distribution"]},
            },
            {
                "heading": "At-Risk Customers",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Email", "Health Score", "Risk Level"],
                    "rows": [
                        [c["email"], c["health_score"], c["risk_level"]]
                        for c in data["at_risk_customers"]
                    ],
                },
                "chart": None,
            },
            {
                "heading": "Health Score Trends",
                "narrative": "",
                "data": {"type": "series", "rows": data["health_score_trend"]},
                "chart": {"type": "line", "data": data["health_score_trend"]},
            },
        ]
        return {"title": title, "sections": sections}

    def _build_feature_prioritization(self, db: Session, org_id: int, date_range_days: int) -> dict:
        data = self._query_feature_prioritization_data(db, org_id, date_range_days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=date_range_days)
        title = (
            f"Feature Request Prioritization — "
            f"{start_date.strftime('%b %-d')} to {end_date.strftime('%b %-d, %Y')}"
        )
        sections = [
            {
                "heading": "Request Volume",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Metric", "Value"],
                    "rows": [["Total Feature Requests", data["total_requests"]]],
                },
                "chart": None,
            },
            {
                "heading": "Top Requests by Frequency",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Category", "Count", "Unique Customers"],
                    "rows": [
                        [row["category"], row["count"], row.get("unique_customers", 0)]
                        for row in data["feature_requests"]
                    ],
                },
                "chart": {"type": "bar", "data": data["feature_requests"]},
            },
            {
                "heading": "Requests by Source",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Source", "Count"],
                    "rows": [[row["source"], row["count"]] for row in data["requests_by_source"]],
                },
                "chart": None,
            },
            {
                "heading": "Priority Matrix",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Priority", "Count"],
                    "rows": [[row["priority"], row["count"]] for row in data["priority_distribution"]],
                },
                "chart": None,
            },
        ]
        return {"title": title, "sections": sections}

    def _build_churn_risk(self, db: Session, org_id: int, date_range_days: int) -> dict:
        data = self._query_churn_risk_data(db, org_id, date_range_days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=date_range_days)
        title = (
            f"Churn Risk Analysis — "
            f"{start_date.strftime('%b %-d')} to {end_date.strftime('%b %-d, %Y')}"
        )
        sections = [
            {
                "heading": "Risk Overview",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Risk Level", "Count"],
                    "rows": [[row["risk_level"], row["count"]] for row in data["risk_overview"]],
                },
                "chart": {"type": "donut", "data": data["risk_overview"]},
            },
            {
                "heading": "High-Risk Customer Details",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Email", "Health Score", "Risk Level"],
                    "rows": [
                        [c["email"], c["health_score"], c["risk_level"]]
                        for c in data["high_risk_customers"]
                    ],
                },
                "chart": None,
            },
            {
                "heading": "Churn Trends",
                "narrative": "",
                "data": {"type": "series", "rows": data["churn_trend"]},
                "chart": {"type": "line", "data": data["churn_trend"]},
            },
            {
                "heading": "Category Correlation",
                "narrative": "",
                "data": {
                    "type": "table",
                    "columns": ["Pain Point Category", "Avg Churn Risk", "Count"],
                    "rows": [
                        [row["category"], row.get("avg_churn_risk", 0), row["count"]]
                        for row in data["category_correlation"]
                    ],
                },
                "chart": None,
            },
        ]
        return {"title": title, "sections": sections}

    # ── Data query methods ────────────────────────────────────────────────────

    def _query_executive_summary_data(self, db: Session, org_id: int, date_range_days: int) -> dict:
        """
        Fetch all data needed for an Executive Summary report.
        """
        start = datetime.utcnow() - timedelta(days=date_range_days)

        # 1. Total feedback count
        total_row = db.execute(
            text(
                "SELECT COUNT(*) FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start"
            ),
            {"org": org_id, "start": start},
        ).fetchone()
        total_feedback = total_row[0] if total_row else 0

        # 2. Sentiment distribution
        sentiment_rows = db.execute(
            text(
                "SELECT sentiment_label, COUNT(*) as cnt "
                "FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start "
                "  AND sentiment_label IS NOT NULL "
                "GROUP BY sentiment_label"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        sentiment_distribution = [
            {"sentiment_label": row[0], "count": row[1]} for row in sentiment_rows
        ]

        # 3. Top 5 pain points
        pain_rows = db.execute(
            text(
                "SELECT pain_point_category, COUNT(*) as cnt "
                "FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start "
                "  AND pain_point_category IS NOT NULL "
                "GROUP BY pain_point_category "
                "ORDER BY cnt DESC LIMIT 5"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        top_pain_points = [{"category": row[0], "count": row[1]} for row in pain_rows]

        # 4. Top 5 feature requests
        feature_rows = db.execute(
            text(
                "SELECT feature_request_category, COUNT(*) as cnt "
                "FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start "
                "  AND feature_request_category IS NOT NULL "
                "GROUP BY feature_request_category "
                "ORDER BY cnt DESC LIMIT 5"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        top_feature_requests = [{"category": row[0], "count": row[1]} for row in feature_rows]

        # 5. Urgent count
        urgent_row = db.execute(
            text(
                "SELECT COUNT(*) FROM feedback_items "
                "WHERE organization_id = :org AND is_urgent = true AND created_at >= :start"
            ),
            {"org": org_id, "start": start},
        ).fetchone()
        urgent_count = urgent_row[0] if urgent_row else 0

        # 6. At-risk + critical customer count
        at_risk_row = db.execute(
            text(
                "SELECT COUNT(*) FROM customer_health_scores "
                "WHERE organization_id = :org "
                "  AND risk_level IN ('at_risk', 'critical')"
            ),
            {"org": org_id},
        ).fetchone()
        at_risk_count = at_risk_row[0] if at_risk_row else 0

        return {
            "total_feedback": total_feedback,
            "sentiment_distribution": sentiment_distribution,
            "top_pain_points": top_pain_points,
            "top_feature_requests": top_feature_requests,
            "urgent_count": urgent_count,
            "at_risk_count": at_risk_count,
        }

    def _query_customer_health_data(self, db: Session, org_id: int, date_range_days: int) -> dict:
        """
        Fetch all data needed for a Customer Health report.
        """
        # 1. Health distribution by risk level
        dist_rows = db.execute(
            text(
                "SELECT risk_level, COUNT(*) as cnt "
                "FROM customer_health_scores "
                "WHERE organization_id = :org "
                "GROUP BY risk_level "
                "ORDER BY cnt DESC"
            ),
            {"org": org_id},
        ).fetchall()
        health_distribution = [{"risk_level": row[0], "count": row[1]} for row in dist_rows]

        # 2. At-risk and critical customers (top 20 ordered by health_score ASC)
        at_risk_rows = db.execute(
            text(
                "SELECT customer_email, health_score, risk_level "
                "FROM customer_health_scores "
                "WHERE organization_id = :org "
                "  AND risk_level IN ('at_risk', 'critical') "
                "ORDER BY health_score ASC LIMIT 20"
            ),
            {"org": org_id},
        ).fetchall()
        at_risk_customers = [
            {"email": row[0], "health_score": row[1], "risk_level": row[2]}
            for row in at_risk_rows
        ]

        # 3. Average health score trend (by date updated)
        trend_rows = db.execute(
            text(
                "SELECT DATE(updated_at) as day, AVG(health_score) as avg_score "
                "FROM customer_health_scores "
                "WHERE organization_id = :org "
                "GROUP BY day "
                "ORDER BY day"
            ),
            {"org": org_id},
        ).fetchall()
        health_score_trend = [
            {"date": str(row[0]), "avg_score": round(row[1], 1) if row[1] else 0}
            for row in trend_rows
        ]

        return {
            "health_distribution": health_distribution,
            "at_risk_customers": at_risk_customers,
            "health_score_trend": health_score_trend,
        }

    def _query_feature_prioritization_data(self, db: Session, org_id: int, date_range_days: int) -> dict:
        """
        Fetch all data needed for a Feature Request Prioritization report.
        """
        start = datetime.utcnow() - timedelta(days=date_range_days)

        # 1. Feature requests by category with unique customer count
        feature_rows = db.execute(
            text(
                "SELECT feature_request_category, "
                "       COUNT(*) as cnt, "
                "       COUNT(DISTINCT customer_email) as unique_customers "
                "FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start "
                "  AND feature_request_category IS NOT NULL "
                "GROUP BY feature_request_category "
                "ORDER BY cnt DESC"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        feature_requests = [
            {"category": row[0], "count": row[1], "unique_customers": row[2]}
            for row in feature_rows
        ]

        # 2. Total feature request count
        total_requests = sum(r["count"] for r in feature_requests)

        # 3. Requests by source
        source_rows = db.execute(
            text(
                "SELECT source, COUNT(*) as cnt "
                "FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start "
                "  AND feature_request_category IS NOT NULL "
                "GROUP BY source "
                "ORDER BY cnt DESC"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        requests_by_source = [{"source": row[0], "count": row[1]} for row in source_rows]

        # 4. Priority distribution
        priority_rows = db.execute(
            text(
                "SELECT feature_request_priority, COUNT(*) as cnt "
                "FROM feedback_items "
                "WHERE organization_id = :org AND created_at >= :start "
                "  AND feature_request_priority IS NOT NULL "
                "GROUP BY feature_request_priority "
                "ORDER BY cnt DESC"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        priority_distribution = [{"priority": row[0], "count": row[1]} for row in priority_rows]

        return {
            "feature_requests": feature_requests,
            "total_requests": total_requests,
            "requests_by_source": requests_by_source,
            "priority_distribution": priority_distribution,
        }

    def _query_churn_risk_data(self, db: Session, org_id: int, date_range_days: int) -> dict:
        """
        Fetch all data needed for a Churn Risk Analysis report.
        """
        start = datetime.utcnow() - timedelta(days=date_range_days)

        # 1. Risk level overview
        risk_rows = db.execute(
            text(
                "SELECT risk_level, COUNT(*) as cnt "
                "FROM customer_health_scores "
                "WHERE organization_id = :org "
                "GROUP BY risk_level "
                "ORDER BY cnt DESC"
            ),
            {"org": org_id},
        ).fetchall()
        risk_overview = [{"risk_level": row[0], "count": row[1]} for row in risk_rows]

        # 2. Top 10 highest-risk customers (lowest health score)
        high_risk_rows = db.execute(
            text(
                "SELECT customer_email, health_score, risk_level "
                "FROM customer_health_scores "
                "WHERE organization_id = :org "
                "ORDER BY health_score ASC LIMIT 10"
            ),
            {"org": org_id},
        ).fetchall()
        high_risk_customers = [
            {"email": row[0], "health_score": row[1], "risk_level": row[2]}
            for row in high_risk_rows
        ]

        # 3. Churn risk score trend (avg churn_risk_score over time)
        trend_rows = db.execute(
            text(
                "SELECT DATE(updated_at) as day, AVG(health_score) as avg_score "
                "FROM customer_health_scores "
                "WHERE organization_id = :org "
                "GROUP BY day "
                "ORDER BY day"
            ),
            {"org": org_id},
        ).fetchall()
        churn_trend = [
            {"date": str(row[0]), "avg_score": round(row[1], 1) if row[1] else 0}
            for row in trend_rows
        ]

        # 4. Pain point categories correlated with churn risk (churn_risk_score > 50)
        corr_rows = db.execute(
            text(
                "SELECT pain_point_category, "
                "       AVG(churn_risk_score) as avg_churn, "
                "       COUNT(*) as cnt "
                "FROM feedback_items "
                "WHERE organization_id = :org "
                "  AND created_at >= :start "
                "  AND churn_risk_score > 50 "
                "  AND pain_point_category IS NOT NULL "
                "GROUP BY pain_point_category "
                "ORDER BY avg_churn DESC"
            ),
            {"org": org_id, "start": start},
        ).fetchall()
        category_correlation = [
            {"category": row[0], "avg_churn_risk": round(row[1], 1) if row[1] else 0, "count": row[2]}
            for row in corr_rows
        ]

        return {
            "risk_overview": risk_overview,
            "high_risk_customers": high_risk_customers,
            "churn_trend": churn_trend,
            "category_correlation": category_correlation,
        }
