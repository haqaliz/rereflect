"""
TDD tests for Scheduled AI Reports — ReportSchedule model + CRUD API.

Covers:
- ReportSchedule model fields, defaults and registration
- CRUD API endpoints (GET list, GET by id, POST create, PATCH, DELETE, toggle)
- RBAC: member -> 403 on mutating routes
- Organization isolation (schedules are org-scoped; cross-org -> 404)
- Validation: enum membership, hour/day bounds, cadence-conditional day fields,
  recipients (EmailStr, trim/lowercase/dedupe, cap 20), unknown fields -> 422
"""

import pytest
from datetime import datetime, timedelta
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
def other_org(db: Session) -> Organization:
    org = Organization(name="Other Corp", plan="business")
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
def other_admin(db: Session, other_org: Organization) -> User:
    user = User(
        email="admin@other.com",
        password_hash=hash_password("password123"),
        organization_id=other_org.id,
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
def admin_headers(business_admin: User) -> dict:
    return _make_headers(business_admin)


@pytest.fixture
def member_headers(business_member: User) -> dict:
    return _make_headers(business_member)


@pytest.fixture
def other_admin_headers(other_admin: User) -> dict:
    return _make_headers(other_admin)


def _schedule_payload(**overrides) -> dict:
    payload = {
        "report_type": "executive_summary",
        "date_range_days": 30,
        "cadence": "daily",
        "hour_utc": 9,
        "recipients": ["ops@business.com"],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def sample_schedule(db: Session, business_org: Organization, business_admin: User):
    """Create a ReportSchedule row directly in the DB."""
    from src.models.report_schedule import ReportSchedule
    schedule = ReportSchedule(
        organization_id=business_org.id,
        created_by_user_id=business_admin.id,
        report_type="executive_summary",
        date_range_days=30,
        cadence="weekly",
        hour_utc=9,
        day_of_week=0,
        recipients=["ops@business.com"],
        enabled=True,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


# ── Model tests ────────────────────────────────────────────────────────────────


class TestReportScheduleModel:
    """Verify the SQLAlchemy ReportSchedule model fields and defaults."""

    def test_report_schedule_importable(self):
        from src.models.report_schedule import ReportSchedule
        assert ReportSchedule is not None

    def test_report_schedule_in_models_init(self):
        """ReportSchedule must be exported from src/models/__init__.py."""
        from src.models import ReportSchedule
        assert ReportSchedule is not None

    def test_report_schedule_tablename(self):
        from src.models.report_schedule import ReportSchedule
        assert ReportSchedule.__tablename__ == "report_schedules"

    def test_report_schedule_has_required_columns(self):
        from src.models.report_schedule import ReportSchedule
        mapper = ReportSchedule.__table__.columns
        col_names = {c.name for c in mapper}
        required = {
            "id", "organization_id", "created_by_user_id", "report_type",
            "date_range_days", "cadence", "hour_utc", "day_of_week",
            "day_of_month", "recipients", "enabled", "last_run_at",
            "created_at", "updated_at",
        }
        assert required.issubset(col_names), f"Missing columns: {required - col_names}"

    def test_report_schedule_enabled_defaults_true(
        self, db: Session, business_org: Organization, business_admin: User
    ):
        from src.models.report_schedule import ReportSchedule
        schedule = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            cadence="daily",
            hour_utc=9,
            recipients=["ops@business.com"],
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        assert schedule.enabled is True

    def test_report_schedule_date_range_days_defaults_30(
        self, db: Session, business_org: Organization, business_admin: User
    ):
        from src.models.report_schedule import ReportSchedule
        schedule = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            cadence="daily",
            hour_utc=9,
            recipients=["ops@business.com"],
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        assert schedule.date_range_days == 30

    def test_report_schedule_created_updated_auto_set(
        self, db: Session, business_org: Organization, business_admin: User
    ):
        from src.models.report_schedule import ReportSchedule
        schedule = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            cadence="daily",
            hour_utc=9,
            recipients=["ops@business.com"],
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        assert isinstance(schedule.created_at, datetime)
        assert isinstance(schedule.updated_at, datetime)

    def test_report_schedule_last_run_at_nullable(
        self, db: Session, business_org: Organization, business_admin: User
    ):
        from src.models.report_schedule import ReportSchedule
        schedule = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            cadence="daily",
            hour_utc=9,
            recipients=["ops@business.com"],
            last_run_at=None,
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        assert schedule.last_run_at is None

    def test_report_schedule_recipients_stores_json(
        self, db: Session, business_org: Organization, business_admin: User
    ):
        from src.models.report_schedule import ReportSchedule
        recipients = ["ops@business.com", "ceo@business.com"]
        schedule = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            cadence="daily",
            hour_utc=9,
            recipients=recipients,
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        assert schedule.recipients == recipients