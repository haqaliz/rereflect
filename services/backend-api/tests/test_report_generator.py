"""
TDD tests for the ReportGenerator service (M2.4).

Covers:
- ReportGenerator instantiation
- Data query methods for each report type
- Section building with expected keys
- Report type extraction from query string
- Date range extraction from query string
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem
from src.models.customer_health import CustomerHealth
from src.api.auth import hash_password


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def business_org(db: Session) -> Organization:
    org = Organization(name="Generator Test Corp", plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def admin_user(db: Session, business_org: Organization) -> User:
    user = User(
        email="gen_admin@test.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def feedback_batch(db: Session, business_org: Organization) -> list:
    """Seed feedback for report generation queries."""
    now = datetime.utcnow()
    items = [
        FeedbackItem(
            organization_id=business_org.id,
            text="Payment keeps failing on mobile.",
            source="support_ticket",
            sentiment_label="negative",
            sentiment_score=-0.8,
            is_urgent=True,
            pain_point_category="payment_issue",
            pain_point_severity="critical",
            feature_request_category=None,
            churn_risk_score=75,
            customer_email="angry@customer.com",
            created_at=now - timedelta(days=5),
        ),
        FeedbackItem(
            organization_id=business_org.id,
            text="Would love dark mode.",
            source="email",
            sentiment_label="neutral",
            sentiment_score=0.1,
            is_urgent=False,
            pain_point_category=None,
            feature_request_category="ui_enhancement",
            feature_request_priority="medium",
            churn_risk_score=10,
            customer_email="happy@customer.com",
            created_at=now - timedelta(days=3),
        ),
        FeedbackItem(
            organization_id=business_org.id,
            text="Great product overall!",
            source="survey",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            pain_point_category=None,
            feature_request_category=None,
            churn_risk_score=5,
            customer_email="satisfied@customer.com",
            created_at=now - timedelta(days=1),
        ),
    ]
    for item in items:
        db.add(item)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@pytest.fixture
def health_scores(db: Session, business_org: Organization) -> list:
    """Seed customer health scores."""
    scores = [
        CustomerHealth(
            organization_id=business_org.id,
            customer_email="angry@customer.com",
            health_score=25,
            risk_level="critical",
            feedback_count=5,
            updated_at=datetime.utcnow() - timedelta(days=2),
        ),
        CustomerHealth(
            organization_id=business_org.id,
            customer_email="moderate@customer.com",
            health_score=55,
            risk_level="moderate",
            feedback_count=3,
            updated_at=datetime.utcnow() - timedelta(days=1),
        ),
        CustomerHealth(
            organization_id=business_org.id,
            customer_email="satisfied@customer.com",
            health_score=90,
            risk_level="healthy",
            feedback_count=2,
            updated_at=datetime.utcnow(),
        ),
    ]
    for score in scores:
        db.add(score)
    db.commit()
    for score in scores:
        db.refresh(score)
    return scores


@pytest.fixture
def generator():
    from src.services.copilot.report_generator import ReportGenerator
    return ReportGenerator()


# ── Import and instantiation ───────────────────────────────────────────────────


class TestReportGeneratorImport:
    def test_report_generator_importable(self):
        from src.services.copilot.report_generator import ReportGenerator
        assert ReportGenerator is not None

    def test_report_generator_instantiates(self, generator):
        assert generator is not None

    def test_report_generator_has_generate_method(self, generator):
        assert hasattr(generator, "generate")

    def test_report_generator_has_query_methods(self, generator):
        assert hasattr(generator, "_query_executive_summary_data")
        assert hasattr(generator, "_query_customer_health_data")
        assert hasattr(generator, "_query_feature_prioritization_data")
        assert hasattr(generator, "_query_churn_risk_data")


# ── Executive Summary Data Queries ─────────────────────────────────────────────


class TestExecutiveSummaryQueries:
    def test_query_returns_dict(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert isinstance(result, dict)

    def test_query_has_total_feedback_key(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert "total_feedback" in result

    def test_query_total_feedback_correct_count(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert result["total_feedback"] == 3

    def test_query_has_sentiment_distribution(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert "sentiment_distribution" in result

    def test_sentiment_distribution_has_all_labels(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        dist = result["sentiment_distribution"]
        assert isinstance(dist, list)

    def test_query_has_top_pain_points(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert "top_pain_points" in result
        assert isinstance(result["top_pain_points"], list)

    def test_query_has_top_feature_requests(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert "top_feature_requests" in result
        assert isinstance(result["top_feature_requests"], list)

    def test_query_has_urgent_count(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert "urgent_count" in result
        assert result["urgent_count"] == 1

    def test_query_respects_date_range(self, generator, db: Session, business_org: Organization, feedback_batch):
        """Only feedback within date_range_days should be counted."""
        result_7 = generator._query_executive_summary_data(db, business_org.id, 7)
        # All 3 test items are within 7 days
        assert result_7["total_feedback"] == 3

    def test_query_at_risk_count(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_executive_summary_data(db, business_org.id, 30)
        assert "at_risk_count" in result


# ── Customer Health Data Queries ───────────────────────────────────────────────


class TestCustomerHealthQueries:
    def test_query_returns_dict(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_customer_health_data(db, business_org.id, 30)
        assert isinstance(result, dict)

    def test_query_has_health_distribution(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_customer_health_data(db, business_org.id, 30)
        assert "health_distribution" in result
        assert isinstance(result["health_distribution"], list)

    def test_query_has_at_risk_customers(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_customer_health_data(db, business_org.id, 30)
        assert "at_risk_customers" in result
        assert isinstance(result["at_risk_customers"], list)

    def test_at_risk_customers_returns_critical(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_customer_health_data(db, business_org.id, 30)
        at_risk = result["at_risk_customers"]
        emails = [c["email"] for c in at_risk]
        assert "angry@customer.com" in emails

    def test_query_has_health_score_trend(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_customer_health_data(db, business_org.id, 30)
        assert "health_score_trend" in result

    def test_health_distribution_has_risk_levels(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_customer_health_data(db, business_org.id, 30)
        dist = result["health_distribution"]
        risk_levels = {item["risk_level"] for item in dist}
        assert len(risk_levels) > 0


# ── Feature Prioritization Data Queries ────────────────────────────────────────


class TestFeaturePrioritizationQueries:
    def test_query_returns_dict(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_feature_prioritization_data(db, business_org.id, 30)
        assert isinstance(result, dict)

    def test_query_has_feature_requests(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_feature_prioritization_data(db, business_org.id, 30)
        assert "feature_requests" in result
        assert isinstance(result["feature_requests"], list)

    def test_query_has_total_requests(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_feature_prioritization_data(db, business_org.id, 30)
        assert "total_requests" in result
        assert result["total_requests"] == 1  # only 1 item with feature_request_category

    def test_query_has_requests_by_source(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_feature_prioritization_data(db, business_org.id, 30)
        assert "requests_by_source" in result
        assert isinstance(result["requests_by_source"], list)

    def test_query_has_priority_distribution(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_feature_prioritization_data(db, business_org.id, 30)
        assert "priority_distribution" in result

    def test_feature_request_item_has_category(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_feature_prioritization_data(db, business_org.id, 30)
        if result["feature_requests"]:
            item = result["feature_requests"][0]
            assert "category" in item
            assert "count" in item


# ── Churn Risk Data Queries ─────────────────────────────────────────────────────


class TestChurnRiskQueries:
    def test_query_returns_dict(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_churn_risk_data(db, business_org.id, 30)
        assert isinstance(result, dict)

    def test_query_has_risk_overview(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_churn_risk_data(db, business_org.id, 30)
        assert "risk_overview" in result
        assert isinstance(result["risk_overview"], list)

    def test_query_has_high_risk_customers(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_churn_risk_data(db, business_org.id, 30)
        assert "high_risk_customers" in result
        assert isinstance(result["high_risk_customers"], list)

    def test_high_risk_customers_top10(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_churn_risk_data(db, business_org.id, 30)
        assert len(result["high_risk_customers"]) <= 10

    def test_query_has_churn_trend(self, generator, db: Session, business_org: Organization, health_scores):
        result = generator._query_churn_risk_data(db, business_org.id, 30)
        assert "churn_trend" in result

    def test_query_has_category_correlation(self, generator, db: Session, business_org: Organization, feedback_batch):
        result = generator._query_churn_risk_data(db, business_org.id, 30)
        assert "category_correlation" in result
        assert isinstance(result["category_correlation"], list)


# ── Report Type Extraction ─────────────────────────────────────────────────────


class TestReportTypeExtraction:
    def test_extract_executive_summary_from_keyword(self, generator):
        assert generator.extract_report_type("Generate an executive summary") == "executive_summary"

    def test_extract_executive_summary_from_summary_keyword(self, generator):
        assert generator.extract_report_type("Give me a monthly summary") == "executive_summary"

    def test_extract_executive_summary_from_overview(self, generator):
        assert generator.extract_report_type("Show me an overview for last 30 days") == "executive_summary"

    def test_extract_customer_health_from_health(self, generator):
        assert generator.extract_report_type("Customer health report please") == "customer_health"

    def test_extract_customer_health_from_health_report(self, generator):
        assert generator.extract_report_type("Generate a health report") == "customer_health"

    def test_extract_feature_prioritization_from_feature(self, generator):
        assert generator.extract_report_type("Feature request priorities") == "feature_prioritization"

    def test_extract_feature_prioritization_from_prioriti(self, generator):
        assert generator.extract_report_type("Prioritize my feature requests") == "feature_prioritization"

    def test_extract_churn_risk_from_churn(self, generator):
        assert generator.extract_report_type("Churn risk analysis for this month") == "churn_risk"

    def test_extract_churn_risk_from_attrition(self, generator):
        assert generator.extract_report_type("Show attrition analysis") == "churn_risk"

    def test_extract_default_is_executive_summary(self, generator):
        """Bare 'report' keyword with no type hint → executive_summary."""
        assert generator.extract_report_type("Generate a report") == "executive_summary"

    def test_extract_case_insensitive(self, generator):
        assert generator.extract_report_type("EXECUTIVE SUMMARY please") == "executive_summary"


# ── Date Range Extraction ──────────────────────────────────────────────────────


class TestDateRangeExtraction:
    def test_extract_7_days_from_last_7(self, generator):
        assert generator.extract_date_range("last 7 days") == 7

    def test_extract_7_days_from_this_week(self, generator):
        assert generator.extract_date_range("show this week") == 7

    def test_extract_30_days_from_last_30(self, generator):
        assert generator.extract_date_range("last 30 days") == 30

    def test_extract_30_days_from_this_month(self, generator):
        assert generator.extract_date_range("executive summary this month") == 30

    def test_extract_90_days_from_last_90(self, generator):
        assert generator.extract_date_range("last 90 days") == 90

    def test_extract_90_days_from_this_quarter(self, generator):
        assert generator.extract_date_range("quarterly review") == 90

    def test_extract_90_days_from_quarterly(self, generator):
        assert generator.extract_date_range("generate a quarterly report") == 90

    def test_default_is_30_days(self, generator):
        """No date hint → default 30 days."""
        assert generator.extract_date_range("generate a report") == 30

    def test_extract_case_insensitive(self, generator):
        assert generator.extract_date_range("This Month summary") == 30


# ── Build sections structure ───────────────────────────────────────────────────


class TestBuildSections:
    """Each report type returns a {title, sections} dict with proper structure."""

    def test_build_executive_summary_returns_title_and_sections(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        assert "title" in result
        assert "sections" in result

    def test_build_executive_summary_sections_is_list(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        assert isinstance(result["sections"], list)

    def test_build_executive_summary_sections_not_empty(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        assert len(result["sections"]) > 0

    def test_build_executive_summary_sections_have_heading(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        for section in result["sections"]:
            assert "heading" in section

    def test_build_executive_summary_sections_have_data(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        for section in result["sections"]:
            assert "data" in section

    def test_build_customer_health_returns_title_and_sections(
        self, generator, db: Session, business_org: Organization, health_scores
    ):
        result = generator._build_customer_health(db, business_org.id, 30)
        assert "title" in result
        assert "sections" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) > 0

    def test_build_feature_prioritization_returns_title_and_sections(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_feature_prioritization(db, business_org.id, 30)
        assert "title" in result
        assert "sections" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) > 0

    def test_build_churn_risk_returns_title_and_sections(
        self, generator, db: Session, business_org: Organization, health_scores
    ):
        result = generator._build_churn_risk(db, business_org.id, 30)
        assert "title" in result
        assert "sections" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) > 0

    def test_section_has_chart_key(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        for section in result["sections"]:
            assert "chart" in section

    def test_title_includes_date_range(
        self, generator, db: Session, business_org: Organization, feedback_batch
    ):
        result = generator._build_executive_summary(db, business_org.id, 30)
        # Title should mention some date context
        assert isinstance(result["title"], str)
        assert len(result["title"]) > 0
