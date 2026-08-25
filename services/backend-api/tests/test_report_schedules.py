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
from unittest.mock import patch
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
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Corp", plan="free")
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


@pytest.fixture
def free_admin_headers(free_admin: User) -> dict:
    return _make_headers(free_admin)


def _schedule_payload(**overrides) -> dict:
    payload = {
        "report_type": "executive_summary",
        "date_range_days": 30,
        "cadence": "daily",
        "hour_utc": 9,
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


# ── API: Create Schedule ───────────────────────────────────────────────────────


class TestCreateSchedule:
    """POST /api/v1/report-schedules"""

    def test_create_schedule_returns_201(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(),
            headers=admin_headers,
        )
        assert resp.status_code == 201

    def test_create_schedule_response_shape(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(),
            headers=admin_headers,
        )
        data = resp.json()
        for key in (
            "id", "report_type", "date_range_days", "cadence", "hour_utc",
            "day_of_week", "day_of_month", "recipients", "enabled",
            "last_run_at", "created_by_user_id", "created_at", "updated_at",
        ):
            assert key in data, f"Missing key: {key}"

    def test_create_schedule_minimal_defaults_recipients_to_creator(
        self, client: TestClient, admin_headers: dict, business_admin: User
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["recipients"] == [business_admin.email]
        assert data["date_range_days"] == 30
        assert data["enabled"] is True
        assert data["created_by_user_id"] == business_admin.id
        assert data["last_run_at"] is None

    def test_create_schedule_weekly_requires_day_of_week(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(cadence="weekly", day_of_week=0),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["day_of_week"] == 0

    def test_create_schedule_monthly_requires_day_of_month(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(cadence="monthly", day_of_month=15),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["day_of_month"] == 15

    def test_create_schedule_stores_explicit_date_range(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(date_range_days=7),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["date_range_days"] == 7

    def test_create_schedule_recipients_trimmed_lowercased_deduped(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(recipients=[
                "  Ops@Business.COM ",
                "ops@business.com",
                "CEO@business.com",
            ]),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["recipients"] == [
            "ops@business.com", "ceo@business.com",
        ]

    def test_create_schedule_explicit_empty_recipients_allowed(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(recipients=[]),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["recipients"] == []

    def test_create_schedule_20_recipients_allowed(
        self, client: TestClient, admin_headers: dict
    ):
        recipients = [f"user{i}@business.com" for i in range(20)]
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(recipients=recipients),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert len(resp.json()["recipients"]) == 20

    def test_create_schedule_21_recipients_422(
        self, client: TestClient, admin_headers: dict
    ):
        recipients = [f"user{i}@business.com" for i in range(21)]
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(recipients=recipients),
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_create_schedule_403_for_member(
        self, client: TestClient, member_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(),
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_create_schedule_403_for_free_plan(
        self, client: TestClient, free_admin_headers: dict
    ):
        resp = client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(),
            headers=free_admin_headers,
        )
        assert resp.status_code == 403


# ── API: List Schedules ────────────────────────────────────────────────────────


class TestListSchedules:
    """GET /api/v1/report-schedules"""

    def test_list_schedules_returns_200(self, client: TestClient, admin_headers: dict):
        resp = client.get("/api/v1/report-schedules", headers=admin_headers)
        assert resp.status_code == 200

    def test_list_schedules_returns_empty_list_when_none(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.get("/api/v1/report-schedules", headers=admin_headers)
        assert resp.json() == []

    def test_list_schedules_returns_saved_schedule(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.get("/api/v1/report-schedules", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["report_type"] == "executive_summary"

    def test_list_schedules_allowed_for_member(
        self, client: TestClient, member_headers: dict, sample_schedule
    ):
        resp = client.get("/api/v1/report-schedules", headers=member_headers)
        assert resp.status_code == 200

    def test_list_schedules_403_for_free_plan(
        self, client: TestClient, free_admin_headers: dict
    ):
        resp = client.get("/api/v1/report-schedules", headers=free_admin_headers)
        assert resp.status_code == 403

    def test_list_schedules_org_isolation(
        self,
        client: TestClient,
        other_admin_headers: dict,
        sample_schedule,  # belongs to business_org
    ):
        resp = client.get("/api/v1/report-schedules", headers=other_admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_schedules_default_order_newest_first(
        self,
        client: TestClient,
        db: Session,
        business_org: Organization,
        business_admin: User,
        admin_headers: dict,
    ):
        from src.models.report_schedule import ReportSchedule
        older = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="executive_summary",
            cadence="daily",
            hour_utc=9,
            recipients=["ops@business.com"],
            created_at=datetime(2026, 3, 1),
            updated_at=datetime(2026, 3, 1),
        )
        newer = ReportSchedule(
            organization_id=business_org.id,
            created_by_user_id=business_admin.id,
            report_type="churn_risk",
            cadence="daily",
            hour_utc=8,
            recipients=["ops@business.com"],
            created_at=datetime(2026, 3, 15),
            updated_at=datetime(2026, 3, 15),
        )
        db.add_all([older, newer])
        db.commit()

        resp = client.get("/api/v1/report-schedules", headers=admin_headers)
        types = [s["report_type"] for s in resp.json()]
        assert types[0] == "churn_risk"
        assert types[1] == "executive_summary"


# ── API: Get Schedule by ID ────────────────────────────────────────────────────


class TestGetSchedule:
    """GET /api/v1/report-schedules/{id}"""

    def test_get_schedule_returns_200(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.get(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=admin_headers
        )
        assert resp.status_code == 200

    def test_get_schedule_response_shape(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.get(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=admin_headers
        )
        data = resp.json()
        for key in (
            "id", "report_type", "date_range_days", "cadence", "hour_utc",
            "day_of_week", "day_of_month", "recipients", "enabled",
            "last_run_at", "created_by_user_id", "created_at", "updated_at",
        ):
            assert key in data, f"Missing key: {key}"
        assert data["cadence"] == "weekly"
        assert data["day_of_week"] == 0
        assert data["created_by_user_id"] == sample_schedule.created_by_user_id

    def test_get_schedule_404_for_nonexistent(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.get("/api/v1/report-schedules/99999", headers=admin_headers)
        assert resp.status_code == 404

    def test_get_schedule_404_for_other_org(
        self,
        client: TestClient,
        other_admin_headers: dict,
        sample_schedule,  # belongs to business_org
    ):
        resp = client.get(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            headers=other_admin_headers,
        )
        assert resp.status_code == 404

    def test_get_schedule_allowed_for_member(
        self, client: TestClient, member_headers: dict, sample_schedule
    ):
        resp = client.get(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=member_headers
        )
        assert resp.status_code == 200


# ── API: Patch Schedule ────────────────────────────────────────────────────────


class TestPatchSchedule:
    """PATCH /api/v1/report-schedules/{id}"""

    def test_patch_schedule_partial_update(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"hour_utc": 17},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hour_utc"] == 17
        assert data["cadence"] == "weekly"
        assert data["report_type"] == "executive_summary"

    def test_patch_schedule_change_cadence_to_weekly_with_day(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"cadence": "monthly", "day_of_month": 10},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cadence"] == "monthly"
        assert data["day_of_month"] == 10

    def test_patch_schedule_replace_recipients(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"recipients": ["new@business.com", "NEW@business.com"]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["recipients"] == ["new@business.com"]

    def test_patch_schedule_removing_day_of_week_from_weekly_422(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"day_of_week": None},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_patch_schedule_cadence_weekly_without_day_422(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"cadence": "weekly", "day_of_week": None},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_patch_schedule_cadence_monthly_without_day_422(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"cadence": "monthly"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_patch_schedule_404_for_other_org(
        self,
        client: TestClient,
        other_admin_headers: dict,
        sample_schedule,  # belongs to business_org
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"hour_utc": 10},
            headers=other_admin_headers,
        )
        assert resp.status_code == 404

    def test_patch_schedule_404_for_nonexistent(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.patch(
            "/api/v1/report-schedules/99999",
            json={"hour_utc": 10},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_patch_schedule_403_for_member(
        self, client: TestClient, member_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"hour_utc": 10},
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_patch_schedule_created_by_user_id_not_updatable(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"created_by_user_id": 1},
            headers=admin_headers,
        )
        assert resp.status_code == 422


# ── API: Delete Schedule ───────────────────────────────────────────────────────


class TestDeleteSchedule:
    """DELETE /api/v1/report-schedules/{id}"""

    def test_delete_schedule_204_for_admin(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.delete(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=admin_headers
        )
        assert resp.status_code == 204

    def test_delete_schedule_actually_removes_it(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        client.delete(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=admin_headers
        )
        resp = client.get(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_delete_schedule_403_for_member(
        self, client: TestClient, member_headers: dict, sample_schedule
    ):
        resp = client.delete(
            f"/api/v1/report-schedules/{sample_schedule.id}", headers=member_headers
        )
        assert resp.status_code == 403

    def test_delete_schedule_404_for_other_org(
        self,
        client: TestClient,
        other_admin_headers: dict,
        sample_schedule,  # belongs to business_org
    ):
        resp = client.delete(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            headers=other_admin_headers,
        )
        assert resp.status_code == 404

    def test_delete_schedule_404_for_nonexistent(
        self, client: TestClient, admin_headers: dict
    ):
        resp = client.delete("/api/v1/report-schedules/99999", headers=admin_headers)
        assert resp.status_code == 404


# ── API: Toggle Schedule ───────────────────────────────────────────────────────


class TestToggleSchedule:
    """POST /api/v1/report-schedules/{id}/toggle"""

    def test_toggle_schedule_disables(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.post(
            f"/api/v1/report-schedules/{sample_schedule.id}/toggle",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_toggle_schedule_re_enables(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        client.post(
            f"/api/v1/report-schedules/{sample_schedule.id}/toggle",
            headers=admin_headers,
        )
        resp = client.post(
            f"/api/v1/report-schedules/{sample_schedule.id}/toggle",
            headers=admin_headers,
        )
        assert resp.json()["enabled"] is True

    def test_toggle_schedule_persists_enabled(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict,
        sample_schedule,
    ):
        client.post(
            f"/api/v1/report-schedules/{sample_schedule.id}/toggle",
            headers=admin_headers,
        )
        db.refresh(sample_schedule)
        assert sample_schedule.enabled is False

    def test_toggle_schedule_403_for_member(
        self, client: TestClient, member_headers: dict, sample_schedule
    ):
        resp = client.post(
            f"/api/v1/report-schedules/{sample_schedule.id}/toggle",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_toggle_schedule_404_for_other_org(
        self,
        client: TestClient,
        other_admin_headers: dict,
        sample_schedule,  # belongs to business_org
    ):
        resp = client.post(
            f"/api/v1/report-schedules/{sample_schedule.id}/toggle",
            headers=other_admin_headers,
        )
        assert resp.status_code == 404


# ── API: Validation ────────────────────────────────────────────────────────────


class TestScheduleValidation:
    """422 cases for create (and patch where noted)."""

    def _create(self, client: TestClient, headers: dict, **overrides):
        return client.post(
            "/api/v1/report-schedules",
            json=_schedule_payload(**overrides),
            headers=headers,
        )

    def test_create_invalid_report_type_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, report_type="quarterly_summary").status_code == 422

    def test_create_invalid_cadence_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, cadence="hourly").status_code == 422

    def test_create_hour_above_23_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, hour_utc=24).status_code == 422

    def test_create_hour_below_0_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, hour_utc=-1).status_code == 422

    def test_create_day_of_week_out_of_range_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, cadence="weekly", day_of_week=7).status_code == 422

    def test_create_day_of_month_zero_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, cadence="monthly", day_of_month=0).status_code == 422

    def test_create_day_of_month_above_31_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, cadence="monthly", day_of_month=32).status_code == 422

    def test_create_weekly_without_day_of_week_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, cadence="weekly").status_code == 422

    def test_create_monthly_without_day_of_month_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, cadence="monthly").status_code == 422

    def test_create_invalid_email_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, recipients=["not-an-email"]).status_code == 422

    def test_create_date_range_days_not_in_7_30_90_422(self, client: TestClient, admin_headers: dict):
        assert self._create(client, admin_headers, date_range_days=14).status_code == 422

    def test_create_unknown_field_422(self, client: TestClient, admin_headers: dict):
        payload = _schedule_payload()
        payload["bogus_field"] = "x"
        resp = client.post(
            "/api/v1/report-schedules", json=payload, headers=admin_headers
        )
        assert resp.status_code == 422

    def test_create_last_run_at_not_client_settable(self, client: TestClient, admin_headers: dict):
        payload = _schedule_payload(last_run_at="2026-03-17T12:00:00")
        resp = client.post(
            "/api/v1/report-schedules", json=payload, headers=admin_headers
        )
        assert resp.status_code == 422

    def test_patch_invalid_hour_422(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"hour_utc": 25},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_patch_unknown_field_422(
        self, client: TestClient, admin_headers: dict, sample_schedule
    ):
        resp = client.patch(
            f"/api/v1/report-schedules/{sample_schedule.id}",
            json={"bogus_field": "x"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

# ── API: Manual run ───────────────────────────────────────────────────────────


class TestRunSchedule:
    """POST /api/v1/report-schedules/{id}/run (manual "sync now")"""

    RUN_TASK = "src.tasks.scheduled_reports.generate_schedule_once"

    def test_run_schedule_dispatches_exact_task(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict,
        sample_schedule,
    ):
        with patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "task-x"
            resp = client.post(
                f"/api/v1/report-schedules/{sample_schedule.id}/run",
                headers=admin_headers,
            )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": "queued",
            "schedule_id": sample_schedule.id,
        }
        mock_get_app.return_value.send_task.assert_called_once_with(
            self.RUN_TASK, args=[sample_schedule.id]
        )

    def test_run_schedule_403_for_member(
        self, client: TestClient, member_headers: dict, sample_schedule
    ):
        with patch("src.background.celery_client.get_celery_app") as mock_get_app:
            resp = client.post(
                f"/api/v1/report-schedules/{sample_schedule.id}/run",
                headers=member_headers,
            )

        assert resp.status_code == 403
        mock_get_app.return_value.send_task.assert_not_called()

    def test_run_schedule_404_for_other_org(
        self,
        client: TestClient,
        other_admin_headers: dict,
        sample_schedule,  # belongs to business_org
    ):
        with patch("src.background.celery_client.get_celery_app") as mock_get_app:
            resp = client.post(
                f"/api/v1/report-schedules/{sample_schedule.id}/run",
                headers=other_admin_headers,
            )

        assert resp.status_code == 404
        mock_get_app.return_value.send_task.assert_not_called()
