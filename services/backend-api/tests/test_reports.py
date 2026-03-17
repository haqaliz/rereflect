"""
TDD tests for On-Demand AI Reports — Phase 1 (M2.4).

Covers:
- Report model creation and persistence
- Report CRUD API endpoints (GET list, GET by id, DELETE)
- Plan gating: ai_reports feature requires Business+
- Admin-only delete enforcement
- Organization isolation (reports are org-scoped)
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def business_org(db: Session) -> Organization:
    org = Organization(name="Business Corp", plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def enterprise_org(db: Session) -> Organization:
    org = Organization(name="Enterprise Corp", plan="enterprise")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Pro Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def business_admin(db: Session, business_org: Organization) -> User:
    user = User(
        email="admin@business.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def business_member(db: Session, business_org: Organization) -> User:
    user = User(
        email="member@business.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def enterprise_admin(db: Session, enterprise_org: Organization) -> User:
    user = User(
        email="admin@enterprise.com",
        password_hash=hash_password("password123"),
        organization_id=enterprise_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_admin(db: Session, free_org: Organization) -> User:
    user = User(
        email="admin@free.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_admin(db: Session, pro_org: Organization) -> User:
    user = User(
        email="admin@pro.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_headers(user: User) -> dict:
    token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def business_admin_headers(business_admin: User) -> dict:
    return _make_headers(business_admin)


@pytest.fixture
def business_member_headers(business_member: User) -> dict:
    return _make_headers(business_member)


@pytest.fixture
def enterprise_admin_headers(enterprise_admin: User) -> dict:
    return _make_headers(enterprise_admin)


@pytest.fixture
def free_admin_headers(free_admin: User) -> dict:
    return _make_headers(free_admin)


@pytest.fixture
def pro_admin_headers(pro_admin: User) -> dict:
    return _make_headers(pro_admin)


@pytest.fixture
def sample_report(db: Session, business_org: Organization, business_admin: User):
    """Create a sample Report record directly in the DB."""
    from src.models.report import Report
    report = Report(
        organization_id=business_org.id,
        created_by_user_id=business_admin.id,
        report_type="executive_summary",
        date_range_days=30,
        title="Executive Summary — Feb 16 to Mar 17, 2026",
        sections=[
            {
                "heading": "Overview",
                "narrative": "This is the overview section.",
                "data": {"type": "table", "columns": ["Metric", "Value"], "rows": [["Total Feedback", 100]]},
                "chart": None,
            }
        ],
        report_metadata={
            "total_feedback": 100,
            "date_start": "2026-02-16",
            "date_end": "2026-03-17",
            "generated_at": "2026-03-17T12:00:00",
            "model_used": "gpt-4o-mini",
            "tokens_used": 500,
        },
        pdf_generated=False,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# ── Model tests ────────────────────────────────────────────────────────────────


class TestReportModel:
    """Verify the SQLAlchemy Report model fields and defaults."""

    def test_report_model_importable(self):
        from src.models.report import Report
        assert Report is not None

    def test_report_model_has_required_columns(self):
        from src.models.report import Report
        mapper = Report.__table__.columns
        col_names = {c.name for c in mapper}
        required = {
            "id", "organization_id", "created_by_user_id", "conversation_id",
            "report_type", "date_range_days", "title",
            "sections", "metadata", "pdf_generated", "created_at",
        }
        # 'metadata' is the actual DB column name (mapped as report_metadata on the ORM)
        assert required.issubset(col_names), f"Missing columns: {required - col_names}"

    def test_report_model_tablename(self):
        from src.models.report import Report
        assert Report.__tablename__ == "reports"

    def test_report_pdf_generated_defaults_false(self, db: Session, business_org: Organization, business_admin: User):
        from src.models.report import Report
        report = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            date_range_days=30,
            title="Test Report",
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        assert report.pdf_generated is False

    def test_report_created_at_auto_set(self, db: Session, business_org: Organization, business_admin: User):
        from src.models.report import Report
        report = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="churn_risk",
            date_range_days=7,
            title="Churn Risk — 7 Days",
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        assert report.created_at is not None
        assert isinstance(report.created_at, datetime)

    def test_report_conversation_id_nullable(self, db: Session, business_org: Organization, business_admin: User):
        from src.models.report import Report
        report = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="customer_health",
            date_range_days=90,
            title="Customer Health Report",
            conversation_id=None,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        assert report.conversation_id is None

    def test_report_sections_stores_json(self, db: Session, business_org: Organization, business_admin: User):
        from src.models.report import Report
        sections = [{"heading": "Overview", "narrative": "Test narrative", "data": {}, "chart": None}]
        report = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            date_range_days=30,
            title="Test",
            sections=sections,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        assert report.sections == sections

    def test_report_metadata_stores_json(self, db: Session, business_org: Organization, business_admin: User):
        from src.models.report import Report
        meta = {"total_feedback": 42, "model_used": "gpt-4o-mini"}
        report = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="feature_prioritization",
            date_range_days=30,
            title="Feature Report",
            report_metadata=meta,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        assert report.report_metadata["total_feedback"] == 42

    def test_report_in_models_init(self):
        """Report must be exported from src/models/__init__.py."""
        from src.models import Report
        assert Report is not None


# ── Plan config tests ──────────────────────────────────────────────────────────


class TestPlanConfig:
    """ai_reports feature must be gated at Business+."""

    def test_ai_reports_not_in_free_features(self):
        from src.config.plans import PLANS
        assert "ai_reports" not in PLANS["free"]["features"]

    def test_ai_reports_not_in_pro_features(self):
        from src.config.plans import PLANS
        assert "ai_reports" not in PLANS["pro"]["features"]

    def test_ai_reports_in_business_features(self):
        from src.config.plans import PLANS
        assert "ai_reports" in PLANS["business"]["features"]

    def test_ai_reports_in_enterprise_features(self):
        from src.config.plans import PLANS
        assert "ai_reports" in PLANS["enterprise"]["features"]

    def test_ai_reports_feature_plan_is_business(self):
        from src.config.plans import FEATURE_PLANS
        assert FEATURE_PLANS.get("ai_reports") == "business"

    def test_has_feature_business_ai_reports(self):
        from src.config.plans import has_feature
        assert has_feature("business", "ai_reports") is True

    def test_has_feature_enterprise_ai_reports(self):
        from src.config.plans import has_feature
        assert has_feature("enterprise", "ai_reports") is True

    def test_has_feature_free_ai_reports_false(self):
        from src.config.plans import has_feature
        assert has_feature("free", "ai_reports") is False

    def test_has_feature_pro_ai_reports_false(self):
        from src.config.plans import has_feature
        assert has_feature("pro", "ai_reports") is False


# ── API: List Reports ──────────────────────────────────────────────────────────


class TestListReports:
    """GET /api/v1/reports"""

    def test_list_reports_returns_200_for_business(self, client: TestClient, business_admin_headers: dict):
        resp = client.get("/api/v1/reports", headers=business_admin_headers)
        assert resp.status_code == 200

    def test_list_reports_returns_empty_list_when_none(self, client: TestClient, business_admin_headers: dict):
        resp = client.get("/api/v1/reports", headers=business_admin_headers)
        assert resp.json() == []

    def test_list_reports_returns_saved_report(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get("/api/v1/reports", headers=business_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["report_type"] == "executive_summary"

    def test_list_reports_403_for_free_plan(self, client: TestClient, free_admin_headers: dict):
        resp = client.get("/api/v1/reports", headers=free_admin_headers)
        assert resp.status_code == 403

    def test_list_reports_403_for_pro_plan(self, client: TestClient, pro_admin_headers: dict):
        resp = client.get("/api/v1/reports", headers=pro_admin_headers)
        assert resp.status_code == 403

    def test_list_reports_200_for_enterprise(self, client: TestClient, enterprise_admin_headers: dict):
        resp = client.get("/api/v1/reports", headers=enterprise_admin_headers)
        assert resp.status_code == 200

    def test_list_reports_401_without_auth(self, client: TestClient):
        resp = client.get("/api/v1/reports")
        assert resp.status_code == 403

    def test_list_reports_org_isolation(
        self,
        client: TestClient,
        db: Session,
        enterprise_org: Organization,
        enterprise_admin: User,
        enterprise_admin_headers: dict,
        sample_report,  # belongs to business_org
    ):
        """Reports from a different org must not appear."""
        resp = client.get("/api/v1/reports", headers=enterprise_admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_reports_response_shape(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get("/api/v1/reports", headers=business_admin_headers)
        item = resp.json()[0]
        for key in ("id", "report_type", "date_range_days", "title", "pdf_generated", "created_at"):
            assert key in item, f"Missing key: {key}"

    def test_list_reports_default_order_newest_first(
        self, client: TestClient, db: Session, business_org: Organization,
        business_admin: User, business_admin_headers: dict
    ):
        """Reports should be ordered by created_at DESC."""
        from src.models.report import Report
        from datetime import timedelta

        older = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            date_range_days=7,
            title="Older Report",
            created_at=datetime(2026, 3, 1),
        )
        newer = Report(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="churn_risk",
            date_range_days=30,
            title="Newer Report",
            created_at=datetime(2026, 3, 15),
        )
        db.add_all([older, newer])
        db.commit()

        resp = client.get("/api/v1/reports", headers=business_admin_headers)
        titles = [r["title"] for r in resp.json()]
        assert titles[0] == "Newer Report"
        assert titles[1] == "Older Report"


# ── API: Get Report by ID ──────────────────────────────────────────────────────


class TestGetReport:
    """GET /api/v1/reports/{id}"""

    def test_get_report_returns_200(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        assert resp.status_code == 200

    def test_get_report_returns_full_sections(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        data = resp.json()
        assert "sections" in data
        assert len(data["sections"]) == 1
        assert data["sections"][0]["heading"] == "Overview"

    def test_get_report_returns_metadata(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        data = resp.json()
        assert "metadata" in data
        assert data["metadata"]["total_feedback"] == 100

    def test_get_report_404_for_nonexistent(
        self, client: TestClient, business_admin_headers: dict
    ):
        resp = client.get("/api/v1/reports/99999", headers=business_admin_headers)
        assert resp.status_code == 404

    def test_get_report_404_for_other_org(
        self,
        client: TestClient,
        enterprise_admin_headers: dict,
        sample_report,  # belongs to business_org
    ):
        """Cross-org access must return 404, not 403 (don't leak existence)."""
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=enterprise_admin_headers)
        assert resp.status_code == 404

    def test_get_report_403_for_free_plan(
        self, client: TestClient, free_admin_headers: dict, sample_report
    ):
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=free_admin_headers)
        assert resp.status_code == 403

    def test_get_report_response_has_title(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        assert resp.json()["title"] == sample_report.title

    def test_get_report_response_has_report_type(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        assert resp.json()["report_type"] == "executive_summary"


# ── API: Delete Report ─────────────────────────────────────────────────────────


class TestDeleteReport:
    """DELETE /api/v1/reports/{id}"""

    def test_delete_report_204_for_admin(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        resp = client.delete(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        assert resp.status_code == 204

    def test_delete_report_actually_removes_it(
        self, client: TestClient, business_admin_headers: dict, sample_report
    ):
        client.delete(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        resp = client.get(f"/api/v1/reports/{sample_report.id}", headers=business_admin_headers)
        assert resp.status_code == 404

    def test_delete_report_403_for_member(
        self, client: TestClient, business_member_headers: dict, sample_report
    ):
        resp = client.delete(f"/api/v1/reports/{sample_report.id}", headers=business_member_headers)
        assert resp.status_code == 403

    def test_delete_report_404_for_nonexistent(
        self, client: TestClient, business_admin_headers: dict
    ):
        resp = client.delete("/api/v1/reports/99999", headers=business_admin_headers)
        assert resp.status_code == 404

    def test_delete_report_404_cross_org(
        self,
        client: TestClient,
        enterprise_admin_headers: dict,
        sample_report,
    ):
        resp = client.delete(f"/api/v1/reports/{sample_report.id}", headers=enterprise_admin_headers)
        assert resp.status_code == 404

    def test_delete_report_403_for_free_plan(
        self, client: TestClient, free_admin_headers: dict, sample_report
    ):
        resp = client.delete(f"/api/v1/reports/{sample_report.id}", headers=free_admin_headers)
        assert resp.status_code == 403

    def test_delete_report_401_without_auth(self, client: TestClient, sample_report):
        resp = client.delete(f"/api/v1/reports/{sample_report.id}")
        assert resp.status_code == 403
