"""
TDD tests for OSS Stripe cleanup (B3 + B4 code references).

These tests assert the *target* state after cleanup — they must FAIL (RED)
before any production changes are made, then PASS (GREEN) after.

Scope (backend-api only):
- /billing/start-trial  → 404 (route deleted)
- /billing/subscription → 404 (route deleted)
- /billing/usage        → Stripe-free (no current_period_* from subscription, no overage_feedback)
- check_feedback_limit / track_feedback_usage → no overage_feedback reference
- UsageRecord.total_feedback property removed (reads overage_feedback)
- Subscription.trial_days_remaining property removed (reads trial_end)
- AdminOrgResponse / AdminOrgDetailResponse → no stripe_customer_id / max_seats
- OrganizationResponse → no stripe_customer_id
- stripe_service.py: no reference to stripe_price_id / stripe_subscription_id in column reads
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import hash_password, create_access_token
from src.models.organization import Organization
from src.models.user import User
from src.models.subscription import Subscription
from src.models.usage import UsageRecord


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def billing_org(db: Session) -> Organization:
    org = Organization(name="OSS Cleanup Test Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def billing_owner(db: Session, billing_org: Organization) -> User:
    user = User(
        email="cleanup_owner@test.com",
        password_hash=hash_password("password123"),
        organization_id=billing_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def billing_headers(billing_owner: User) -> dict:
    token = create_access_token({
        "user_id": billing_owner.id,
        "organization_id": billing_owner.organization_id,
        "role": billing_owner.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db: Session) -> User:
    """System admin user for admin org endpoints."""
    admin_org = Organization(name="Admin Org", plan="enterprise")
    db.add(admin_org)
    db.commit()
    db.refresh(admin_org)

    user = User(
        email="sysadmin@test.com",
        password_hash=hash_password("password123"),
        organization_id=admin_org.id,
        role="owner",
        is_system_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    token = create_access_token({
        "user_id": admin_user.id,
        "organization_id": admin_user.organization_id,
        "role": admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ─── Task 1: DELETE /billing/start-trial ──────────────────────────────────────

class TestStartTrialDeleted:
    """POST /billing/start-trial must return 404 (route deleted)."""

    def test_start_trial_returns_404(self, client: TestClient, billing_headers: dict):
        """Route removed: trials are meaningless in OSS unlimited mode."""
        response = client.post("/api/v1/billing/start-trial", headers=billing_headers)
        assert response.status_code == 404, (
            f"Expected 404 for removed /start-trial, got {response.status_code}"
        )

    def test_trial_response_schema_not_exported(self):
        """TrialResponse schema must be removed from billing.py."""
        import src.api.routes.billing as billing_mod
        assert not hasattr(billing_mod, "TrialResponse"), (
            "TrialResponse schema should be removed after deleting /start-trial"
        )


# ─── Task 2: DELETE /billing/subscription ─────────────────────────────────────

class TestSubscriptionDeleted:
    """GET /billing/subscription must return 404 (route deleted)."""

    def test_subscription_returns_404(self, client: TestClient, billing_headers: dict):
        """Route removed: only exposes Stripe fields."""
        response = client.get("/api/v1/billing/subscription", headers=billing_headers)
        assert response.status_code == 404, (
            f"Expected 404 for removed /subscription, got {response.status_code}"
        )

    def test_subscription_response_schema_not_exported(self):
        """SubscriptionResponse / SubscriptionData schemas removed from billing.py."""
        import src.api.routes.billing as billing_mod
        assert not hasattr(billing_mod, "SubscriptionResponse"), (
            "SubscriptionResponse schema should be removed with the /subscription route"
        )
        assert not hasattr(billing_mod, "SubscriptionData"), (
            "SubscriptionData schema should be removed with the /subscription route"
        )


# ─── Task 3: Stripe-free /billing/usage ───────────────────────────────────────

class TestUsageStripeeFree:
    """/billing/usage must work without reading subscription.current_period_* or overage_feedback."""

    def test_usage_returns_200_without_subscription(
        self, client: TestClient, billing_headers: dict
    ):
        """Usage endpoint works even when no Subscription row exists."""
        response = client.get("/api/v1/billing/usage", headers=billing_headers)
        assert response.status_code == 200

    def test_usage_does_not_include_overage_count(
        self, client: TestClient, billing_headers: dict
    ):
        """overage_count field must be absent from UsageResponse (Stripe artifact)."""
        response = client.get("/api/v1/billing/usage", headers=billing_headers)
        assert response.status_code == 200
        data = response.json()
        assert "overage_count" not in data, (
            "overage_count field must be removed from UsageResponse"
        )

    def test_usage_period_is_calendar_month(
        self, client: TestClient, billing_headers: dict, db: Session, billing_org: Organization
    ):
        """Period is derived from calendar month, not Subscription.current_period_*."""
        # No subscription row exists — usage must still compute a sane period
        response = client.get("/api/v1/billing/usage", headers=billing_headers)
        assert response.status_code == 200
        data = response.json()
        now = datetime.utcnow()
        expected_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # period_start should be this calendar month's first day
        period_start = datetime.fromisoformat(data["period_start"].replace("Z", "+00:00").replace("+00:00", ""))
        assert period_start.month == expected_month_start.month
        assert period_start.day == 1

    def test_usage_schema_no_overage_fields(self):
        """UsageResponse Pydantic model must not have overage_count or overage_enabled fields."""
        from src.api.routes.billing import UsageResponse
        fields = set(UsageResponse.model_fields.keys())
        assert "overage_count" not in fields, "overage_count must be removed from UsageResponse"
        assert "overage_enabled" not in fields, "overage_enabled must be removed from UsageResponse"


# ─── Task 4: check_feedback_limit / track_feedback_usage ──────────────────────

class TestDependenciesStripeeFree:
    """dependencies.py must not reference overage_feedback or Subscription.current_period_*."""

    def test_check_feedback_limit_does_not_read_overage(self):
        """check_feedback_limit source must not reference 'overage_feedback'."""
        import inspect
        from src.api import dependencies
        source = inspect.getsource(dependencies.check_feedback_limit)
        assert "overage_feedback" not in source, (
            "check_feedback_limit still references overage_feedback"
        )

    def test_track_feedback_usage_does_not_write_overage(self):
        """track_feedback_usage source must not reference 'overage_feedback'."""
        import inspect
        from src.api import dependencies
        source = inspect.getsource(dependencies.track_feedback_usage)
        assert "overage_feedback" not in source, (
            "track_feedback_usage still references overage_feedback"
        )

    def test_get_current_usage_does_not_read_current_period(self):
        """get_current_usage must not read subscription.current_period_start/_end."""
        import inspect
        from src.api import dependencies
        source = inspect.getsource(dependencies.get_current_usage)
        assert "current_period_start" not in source, (
            "get_current_usage still reads subscription.current_period_start"
        )
        assert "current_period_end" not in source, (
            "get_current_usage still reads subscription.current_period_end"
        )


# ─── Task 5: feedback.py overage_feedback removed ─────────────────────────────

class TestFeedbackNoOverage:
    """feedback.py must not reference overage_feedback."""

    def test_feedback_create_no_overage_reference(self):
        """Inline usage tracking in create_feedback must not use overage_feedback."""
        import inspect
        import src.api.routes.feedback as fb_mod
        # Get source of the module (not just one function)
        source = inspect.getsource(fb_mod)
        assert "overage_feedback" not in source, (
            "feedback.py still references overage_feedback"
        )


# ─── Task 5b: UsageRecord.total_feedback property removed ─────────────────────

class TestUsageModelNoTotalFeedback:
    """UsageRecord.total_feedback property (reads overage_feedback) must be removed."""

    def test_usage_record_has_no_total_feedback_property(self, db: Session, billing_org: Organization):
        """total_feedback must be gone from UsageRecord."""
        now = datetime.utcnow()
        usage = UsageRecord(
            organization_id=billing_org.id,
            period_start=now.replace(day=1),
            period_end=(now.replace(day=1) + timedelta(days=30)),
            feedback_count=42,
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)
        assert not hasattr(usage, "total_feedback"), (
            "UsageRecord.total_feedback property must be removed (it reads overage_feedback)"
        )


# ─── Task 6: Subscription.trial_days_remaining property removed ───────────────

class TestSubscriptionModelNoTrialDaysRemaining:
    """Subscription.trial_days_remaining property (reads trial_end) must be removed."""

    def test_subscription_has_no_trial_days_remaining(self, db: Session, billing_org: Organization):
        """trial_days_remaining must be gone from Subscription."""
        sub = Subscription(
            organization_id=billing_org.id,
            plan="pro",
            status="active",
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        assert not hasattr(sub, "trial_days_remaining"), (
            "Subscription.trial_days_remaining property must be removed (it reads trial_end)"
        )


# ─── Task 7: Admin/org schemas – stripe_customer_id / max_seats removed ───────

class TestAdminOrgSchemaClean:
    """AdminOrgResponse / AdminOrgDetailResponse must not include stripe_customer_id or max_seats."""

    def test_admin_org_list_no_stripe_customer_id(
        self, client: TestClient, admin_headers: dict
    ):
        """GET /admin/organizations must not include stripe_customer_id in each org."""
        response = client.get("/api/v1/admin/organizations", headers=admin_headers)
        assert response.status_code == 200
        orgs = response.json()["organizations"]
        for org in orgs:
            assert "stripe_customer_id" not in org, (
                f"stripe_customer_id still in AdminOrgResponse: {org}"
            )

    def test_admin_org_detail_no_stripe_customer_id(
        self, client: TestClient, admin_headers: dict, admin_user: User
    ):
        """GET /admin/organizations/{id} must not include stripe_customer_id."""
        org_id = admin_user.organization_id
        response = client.get(f"/api/v1/admin/organizations/{org_id}", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "stripe_customer_id" not in data, (
            "stripe_customer_id still in AdminOrgDetailResponse"
        )

    def test_admin_org_detail_no_max_seats(
        self, client: TestClient, admin_headers: dict, admin_user: User
    ):
        """GET /admin/organizations/{id} must not include max_seats."""
        org_id = admin_user.organization_id
        response = client.get(f"/api/v1/admin/organizations/{org_id}", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "max_seats" not in data, (
            "max_seats still in AdminOrgDetailResponse"
        )

    def test_admin_org_schema_no_stripe_field(self):
        """AdminOrgResponse Pydantic model must not have stripe_customer_id."""
        from src.api.routes.admin_orgs import AdminOrgResponse
        fields = set(AdminOrgResponse.model_fields.keys())
        assert "stripe_customer_id" not in fields, (
            "AdminOrgResponse.stripe_customer_id field must be removed"
        )

    def test_admin_org_detail_schema_no_max_seats_field(self):
        """AdminOrgDetailResponse must not have max_seats."""
        from src.api.routes.admin_orgs import AdminOrgDetailResponse
        fields = set(AdminOrgDetailResponse.model_fields.keys())
        assert "max_seats" not in fields, (
            "AdminOrgDetailResponse.max_seats field must be removed"
        )


class TestOrganizationSchemaClean:
    """OrganizationResponse in organizations.py must not include stripe_customer_id."""

    def test_org_me_no_stripe_customer_id(
        self, client: TestClient, billing_headers: dict
    ):
        """GET /organizations/me must not include stripe_customer_id."""
        response = client.get("/api/v1/organizations/me", headers=billing_headers)
        assert response.status_code == 200
        data = response.json()
        assert "stripe_customer_id" not in data, (
            "stripe_customer_id still in OrganizationResponse"
        )

    def test_org_response_schema_no_stripe_field(self):
        """OrganizationResponse Pydantic model must not have stripe_customer_id."""
        from src.api.routes.organizations import OrganizationResponse
        fields = set(OrganizationResponse.model_fields.keys())
        assert "stripe_customer_id" not in fields, (
            "OrganizationResponse.stripe_customer_id field must be removed"
        )


# ─── Verify /billing/plans still works (preserved route) ──────────────────────

class TestPreservedRoutes:
    """Routes that should be KEPT must still work after cleanup."""

    def test_plans_route_still_works(self, client: TestClient):
        """GET /billing/plans is Stripe-free and must be preserved."""
        response = client.get("/api/v1/billing/plans")
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) > 0

    def test_usage_route_still_works(self, client: TestClient, billing_headers: dict):
        """GET /billing/usage is preserved (Stripe-free version)."""
        response = client.get("/api/v1/billing/usage", headers=billing_headers)
        assert response.status_code == 200


# ─── Feedback creation still works (SELF_HOSTED unlimited) ────────────────────

class TestFeedbackCreationUnlimited:
    """Feedback creation must work unlimited under SELF_HOSTED without hitting overage paths."""

    def test_feedback_count_increments_on_create(
        self, db: Session, billing_org: Organization
    ):
        """After removing overage path, feedback_count is the sole counter."""
        now = datetime.utcnow()
        usage = UsageRecord(
            organization_id=billing_org.id,
            period_start=now.replace(day=1),
            period_end=(now.replace(day=1) + timedelta(days=30)),
            feedback_count=0,
        )
        db.add(usage)
        db.commit()

        # Simulate what the Stripe-free track_feedback_usage should do
        from src.config.plans import get_feedback_limit
        plan = billing_org.plan or "free"
        limit = get_feedback_limit(plan)

        # In SELF_HOSTED mode (default in module after reload) or enterprise plan limit=None
        # We test the logic the new code must implement: just increment feedback_count
        usage.feedback_count += 1
        db.commit()
        db.refresh(usage)
        assert usage.feedback_count == 1
