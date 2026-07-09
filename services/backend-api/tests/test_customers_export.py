"""
TDD tests — bulk-actions-api aspect (segment-actions feature), Phase 3.

Coverage:
  - GET /api/v1/customers/export -> 200, text/csv, attachment header.
  - Filename reflects segment param ("customers-<segment>.csv" / "-all.csv").
  - Rows honor the same filters as list_customers (segment, org scope).
  - Columns per spec, tags joined with "|", cs_owner_email from the owner
    relationship. sentiment_trend is OMITTED and never computed per-row.
  - require_feature("customer_health_scores") gate is unchanged (403 on Free).
  - Route registered before /{email} (export is not swallowed as an email).

See docs/planning/segment-actions/bulk-actions-api/{plan_20260709.md,spec.md}.
"""
import csv
import io
import pytest
from datetime import datetime
from unittest.mock import patch
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.customer_usage import CustomerUsage
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Export Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def free_org(db: Session) -> Organization:
    o = Organization(name="Free Export Co", plan="free")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def other_org(db: Session) -> Organization:
    o = Organization(name="Other Export Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _make_user_headers(db, org, email="owner@export.com", role="owner"):
    u = User(email=email, password_hash=hash_password("password123"), organization_id=org.id, role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id, "organization_id": u.organization_id, "role": u.role})
    return u, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_and_headers(db: Session, org: Organization):
    return _make_user_headers(db, org)


def make_ch(db, org, email, **kwargs) -> CustomerHealth:
    defaults = dict(
        health_score=60,
        risk_level="moderate",
        feedback_count=5,
        confidence_level="medium",
        last_feedback_at=datetime(2026, 1, 1),
        is_archived=False,
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
    )
    defaults.update(kwargs)
    record = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _parse_csv(content: str):
    return list(csv.DictReader(io.StringIO(content)))


class TestExportBasics:
    def test_export_returns_csv_content_type_and_attachment_header(
        self, client, org, user_and_headers, db
    ):
        _, headers = user_and_headers
        make_ch(db, org, "a@example.com")
        r = client.get("/api/v1/customers/export", headers=headers)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert r.headers["content-disposition"] == 'attachment; filename="customers-all.csv"'

    def test_export_filename_reflects_segment(self, client, org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, org, "a@example.com", segment="at_risk")
        r = client.get("/api/v1/customers/export?segment=at_risk", headers=headers)
        assert r.status_code == 200
        assert r.headers["content-disposition"] == 'attachment; filename="customers-at_risk.csv"'

    def test_requires_customer_health_scores_feature(self, client, free_org, db):
        _, headers = _make_user_headers(db, free_org, email="free@export.com")
        r = client.get("/api/v1/customers/export", headers=headers)
        assert r.status_code == 403

    def test_route_not_swallowed_by_email_route(self, client, org, user_and_headers):
        """/export must resolve to the export endpoint, not GET /{email}."""
        _, headers = user_and_headers
        r = client.get("/api/v1/customers/export", headers=headers)
        # A 404 here would mean /{email} matched "export" as a literal email.
        assert r.status_code != 404


class TestExportRowsAndColumns:
    EXPECTED_COLUMNS = [
        "email", "name", "health_score", "risk_level", "segment", "confidence_level",
        "feedback_count", "last_feedback_at", "last_active_at", "churn_probability",
        "tags", "cs_owner_email",
    ]

    def test_columns_and_values(self, client, org, user_and_headers, db):
        owner, headers = user_and_headers
        make_ch(
            db, org, "full@example.com",
            customer_name="Full Row",
            health_score=77,
            risk_level="at_risk",
            segment="silent_churner",
            confidence_level="high",
            feedback_count=12,
            churn_probability=0.4321,
            tags=["vip", "expansion"],
            cs_owner_user_id=owner.id,
        )
        db.add(CustomerUsage(
            organization_id=org.id,
            customer_email="full@example.com",
            usage_score=50,
            events_total=10,
            last_active_at=datetime(2026, 2, 2),
        ))
        db.commit()

        r = client.get("/api/v1/customers/export", headers=headers)
        assert r.status_code == 200
        rows = _parse_csv(r.text)
        assert len(rows) == 1
        row = rows[0]
        assert list(row.keys()) == self.EXPECTED_COLUMNS
        assert row["email"] == "full@example.com"
        assert row["name"] == "Full Row"
        assert row["health_score"] == "77"
        assert row["risk_level"] == "at_risk"
        assert row["segment"] == "silent_churner"
        assert row["confidence_level"] == "high"
        assert row["feedback_count"] == "12"
        assert row["tags"] == "vip|expansion"
        assert row["cs_owner_email"] == owner.email
        assert "0.4321" in row["churn_probability"]
        assert row["last_active_at"] != ""

    def test_no_sentiment_trend_column(self, client, org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, org, "a@example.com")
        r = client.get("/api/v1/customers/export", headers=headers)
        rows = _parse_csv(r.text)
        assert "sentiment_trend" not in rows[0]

    def test_no_per_row_sentiment_trend_computation(self, client, org, user_and_headers, db):
        """The export must NOT call the per-row sentiment-trend service (N+1 avoided)."""
        _, headers = user_and_headers
        make_ch(db, org, "a@example.com")
        make_ch(db, org, "b@example.com")

        with patch(
            "src.api.routes.customers._compute_sentiment_trend_for_customer"
        ) as mock_trend:
            r = client.get("/api/v1/customers/export", headers=headers)
            assert r.status_code == 200
            _parse_csv(r.text)  # force full body consumption
            mock_trend.assert_not_called()

    def test_filters_by_segment(self, client, org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, org, "risky@example.com", segment="at_risk")
        make_ch(db, org, "healthy@example.com", segment="happy_advocate")
        r = client.get("/api/v1/customers/export?segment=at_risk", headers=headers)
        rows = _parse_csv(r.text)
        assert [row["email"] for row in rows] == ["risky@example.com"]

    def test_org_scoped(self, client, org, other_org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, other_org, "theirs@example.com")
        r = client.get("/api/v1/customers/export", headers=headers)
        rows = _parse_csv(r.text)
        assert rows == []

    def test_excludes_archived_by_default(self, client, org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, org, "archived@example.com", is_archived=True)
        make_ch(db, org, "active@example.com", is_archived=False)
        r = client.get("/api/v1/customers/export", headers=headers)
        rows = _parse_csv(r.text)
        assert [row["email"] for row in rows] == ["active@example.com"]

    def test_include_archived_true(self, client, org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, org, "archived@example.com", is_archived=True)
        r = client.get("/api/v1/customers/export?include_archived=true", headers=headers)
        rows = _parse_csv(r.text)
        assert [row["email"] for row in rows] == ["archived@example.com"]

    def test_no_tags_or_owner_renders_empty(self, client, org, user_and_headers, db):
        _, headers = user_and_headers
        make_ch(db, org, "bare@example.com")
        r = client.get("/api/v1/customers/export", headers=headers)
        rows = _parse_csv(r.text)
        assert rows[0]["tags"] == ""
        assert rows[0]["cs_owner_email"] == ""

    def test_csv_formula_injection_is_neutralized(self, client, org, user_and_headers, db):
        """A customer name/tag starting with =, +, -, @ must not be written as a
        live spreadsheet formula, and embedded CR/LF must be stripped so a
        malicious cell can't fabricate an extra CSV "row"."""
        _, headers = user_and_headers
        make_ch(
            db, org, "attacker@example.com",
            customer_name="=cmd|'/C calc'!A1",
            tags=["@evil", "line\r\nbreak"],
        )
        r = client.get("/api/v1/customers/export", headers=headers)
        assert r.status_code == 200
        rows = _parse_csv(r.text)
        assert len(rows) == 1
        row = rows[0]
        # Leading apostrophe neutralizes formula execution in spreadsheet apps.
        assert row["name"].startswith("'=")
        assert row["name"] == "'=cmd|'/C calc'!A1"
        # tags: "@evil" gets a leading apostrophe; embedded CR/LF is stripped.
        tag_parts = row["tags"].split("|")
        assert tag_parts[0] == "'@evil"
        assert "\r" not in row["tags"]
        assert "\n" not in row["tags"]

    def test_export_paginates_across_many_rows(self, client, org, user_and_headers, db):
        """Correctness across a batch boundary (small dataset, but exercises the paging loop)."""
        _, headers = user_and_headers
        for i in range(10):
            make_ch(db, org, f"c{i}@example.com", health_score=i)
        r = client.get(
            "/api/v1/customers/export?sort_by=customer_email&sort_order=asc", headers=headers
        )
        rows = _parse_csv(r.text)
        assert [row["email"] for row in rows] == [f"c{i}@example.com" for i in range(10)]
