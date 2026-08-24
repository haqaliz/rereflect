"""
TDD tests for scheduled AI report generation (worker-scheduled-generation).

Phase 1: mirrored ReportGenerator characterization (pins against drift).
Later phases append: narrative writer, beat task dedup, Report row content,
email dispatch, per-schedule exception isolation, generate_schedule_once.
"""

from datetime import datetime, timedelta

import pytest

from src.models import CustomerHealth, FeedbackItem, Organization
from src.services.report_generator import ReportGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db, name: str = "Org") -> Organization:
    org = Organization(name=name, plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _seed_report_data(db, org_id: int) -> None:
    """Deterministic dataset for the generator characterization test."""
    now = datetime.utcnow()
    feedbacks = [
        FeedbackItem(
            organization_id=org_id,
            text="Great product!",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            created_at=now - timedelta(days=1),
        ),
        FeedbackItem(
            organization_id=org_id,
            text="App crashes on login",
            source="support",
            sentiment_label="negative",
            sentiment_score=-0.8,
            pain_point_category="bugs",
            pain_point_severity="critical",
            is_urgent=True,
            created_at=now - timedelta(days=2),
        ),
        FeedbackItem(
            organization_id=org_id,
            text="Would like dark mode",
            source="email",
            sentiment_label="neutral",
            sentiment_score=0.1,
            feature_request_category="ui",
            feature_request_priority="medium",
            is_urgent=False,
            created_at=now - timedelta(days=3),
        ),
        FeedbackItem(
            organization_id=org_id,
            text="Old feedback",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            created_at=now - timedelta(days=40),
        ),
    ]
    health = [
        CustomerHealth(
            organization_id=org_id,
            customer_email="at-risk@test.com",
            health_score=30,
            risk_level="at_risk",
        ),
        CustomerHealth(
            organization_id=org_id,
            customer_email="critical@test.com",
            health_score=15,
            risk_level="critical",
        ),
        CustomerHealth(
            organization_id=org_id,
            customer_email="healthy@test.com",
            health_score=85,
            risk_level="healthy",
        ),
    ]
    for f in feedbacks:
        db.add(f)
    for h in health:
        db.add(h)
    db.commit()


# ---------------------------------------------------------------------------
# Phase 1 — ReportGenerator mirror characterization
# ---------------------------------------------------------------------------


class TestReportGeneratorMirror:
    def test_generate_executive_summary_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(db, org.id, "executive_summary", 30)

        assert result["title"].startswith("Executive Summary")
        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Overview",
            "Sentiment Analysis",
            "Top Pain Points",
            "Feature Requests",
        ]
        overview_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert overview_rows["Total Feedback"] == 3  # 40-day-old row excluded
        assert overview_rows["Urgent Items"] == 1
        assert overview_rows["At-Risk Customers"] == 2

        sentiment_rows = {
            row[0]: row[1] for row in result["sections"][1]["data"]["rows"]
        }
        assert sentiment_rows == {"positive": 1, "negative": 1, "neutral": 1}

        pain_rows = result["sections"][2]["data"]["rows"]
        assert pain_rows == [["bugs", 1]]

        feature_rows = result["sections"][3]["data"]["rows"]
        assert feature_rows == [["ui", 1]]

    def test_generate_customer_health_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(db, org.id, "customer_health", 30)

        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Health Distribution",
            "At-Risk Customers",
            "Health Score Trends",
        ]
        dist_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert dist_rows["at_risk"] == 1
        assert dist_rows["critical"] == 1
        assert dist_rows["healthy"] == 1

        at_risk = result["sections"][1]["data"]["rows"]
        assert [r[0] for r in at_risk] == ["critical@test.com", "at-risk@test.com"]

    def test_generate_feature_prioritization_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(
            db, org.id, "feature_prioritization", 30
        )

        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Request Volume",
            "Top Requests by Frequency",
            "Requests by Source",
            "Priority Matrix",
        ]
        volume_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert volume_rows["Total Feature Requests"] == 1
        assert result["sections"][1]["data"]["rows"][0][:2] == ["ui", 1]

    def test_generate_churn_risk_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(db, org.id, "churn_risk", 30)

        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Risk Overview",
            "High-Risk Customer Details",
            "Churn Trends",
            "Category Correlation",
        ]
        risk_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert risk_rows["at_risk"] == 1
        assert risk_rows["critical"] == 1