"""
Tests for billing endpoints: checkout, portal, subscription, usage, webhooks, and feature gating.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.subscription import Subscription
from src.models.usage import UsageRecord
from src.api.auth import hash_password, create_access_token
from src.config.plans import PLANS


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def owner_org(db: Session) -> Organization:
    """Create a free-plan org for billing tests."""
    org = Organization(name="Billing Test Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def owner_user(db: Session, owner_org: Organization) -> User:
    """Create an owner user."""
    user = User(
        email="owner@billing.com",
        password_hash=hash_password("password123"),
        organization_id=owner_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    """Auth headers for the owner."""
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db: Session, owner_org: Organization) -> User:
    """Create an admin user in the same org."""
    user = User(
        email="admin@billing.com",
        password_hash=hash_password("password123"),
        organization_id=owner_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    """Auth headers for the admin."""
    token = create_access_token({
        "user_id": admin_user.id,
        "organization_id": admin_user.organization_id,
        "role": admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user(db: Session, owner_org: Organization) -> User:
    """Create a member user in the same org."""
    user = User(
        email="member@billing.com",
        password_hash=hash_password("password123"),
        organization_id=owner_org.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    """Auth headers for the member."""
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pro_org(db: Session) -> Organization:
    """Create a pro-plan org with Stripe customer."""
    org = Organization(
        name="Pro Billing Org",
        plan="pro",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_owner(db: Session, pro_org: Organization) -> User:
    """Create an owner in the pro org."""
    user = User(
        email="pro-owner@billing.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_owner_headers(pro_owner: User) -> dict:
    """Auth headers for the pro owner."""
    token = create_access_token({
        "user_id": pro_owner.id,
        "organization_id": pro_owner.organization_id,
        "role": pro_owner.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pro_subscription(db: Session, pro_org: Organization) -> Subscription:
    """Create an active pro subscription."""
    sub = Subscription(
        organization_id=pro_org.id,
        plan="pro",
        status="active",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@pytest.fixture
def free_usage(db: Session, owner_org: Organization) -> UsageRecord:
    """Create a usage record for the free org."""
    now = datetime.utcnow()
    usage = UsageRecord(
        organization_id=owner_org.id,
        period_start=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        period_end=(now.replace(day=1) + timedelta(days=30)),
        feedback_count=0,
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


# ============================================================================
# Plans Endpoint
# ============================================================================

class TestGetPlans:
    """Tests for GET /api/v1/billing/plans."""

    def test_get_plans_returns_all_tiers(self, client: TestClient):
        """Plans endpoint returns all 4 plan tiers without auth."""
        response = client.get("/api/v1/billing/plans")
        assert response.status_code == 200
        data = response.json()
        plan_ids = [p["id"] for p in data["plans"]]
        assert "free" in plan_ids
        assert "pro" in plan_ids
        assert "business" in plan_ids
        assert "enterprise" in plan_ids

    def test_get_plans_pro_is_popular(self, client: TestClient):
        """Pro plan should be marked as popular."""
        response = client.get("/api/v1/billing/plans")
        data = response.json()
        pro = next(p for p in data["plans"] if p["id"] == "pro")
        assert pro["is_popular"] is True

    def test_get_plans_free_has_correct_limits(self, client: TestClient):
        """Free plan should have 250 feedback limit and 2 seats."""
        response = client.get("/api/v1/billing/plans")
        data = response.json()
        free = next(p for p in data["plans"] if p["id"] == "free")
        assert free["feedback_limit"] == 250
        assert free["seat_limit"] == 2
        assert free["price_monthly"] == 0


# ============================================================================
# Subscription Endpoint
# ============================================================================

class TestGetSubscription:
    """Tests for GET /api/v1/billing/subscription.

    OSS pivot (B3 + B4 cleanup): /subscription route deleted — returns 404.
    """

    def test_get_subscription_returns_404(
        self, client: TestClient, owner_headers: dict
    ):
        """B4 cleanup: /subscription route is removed — returns 404."""
        response = client.get(
            "/api/v1/billing/subscription", headers=owner_headers
        )
        assert response.status_code == 404, (
            f"Expected 404 for removed /subscription route, got {response.status_code}"
        )

    def test_get_subscription_pro_returns_404(
        self, client: TestClient, pro_owner_headers: dict, pro_subscription: Subscription
    ):
        """B4 cleanup: /subscription route removed even for pro orgs — returns 404."""
        response = client.get(
            "/api/v1/billing/subscription", headers=pro_owner_headers
        )
        assert response.status_code == 404, (
            f"Expected 404 for removed /subscription route, got {response.status_code}"
        )


# ============================================================================
# Start Trial Endpoint
# ============================================================================

class TestStartTrial:
    """Tests for POST /api/v1/billing/start-trial.

    OSS pivot (B4 cleanup): /start-trial route deleted — returns 404.
    Trials are meaningless when everything is unlimited in self-hosted mode.
    """

    def test_start_trial_returns_404(
        self, client: TestClient, owner_headers: dict
    ):
        """B4 cleanup: /start-trial route is removed — returns 404."""
        response = client.post(
            "/api/v1/billing/start-trial", headers=owner_headers
        )
        assert response.status_code == 404, (
            f"Expected 404 for removed /start-trial route, got {response.status_code}"
        )

    def test_start_trial_pro_returns_404(
        self, client: TestClient, pro_owner_headers: dict, pro_subscription: Subscription
    ):
        """B4 cleanup: /start-trial removed even for pro orgs."""
        response = client.post(
            "/api/v1/billing/start-trial", headers=pro_owner_headers
        )
        assert response.status_code == 404, (
            f"Expected 404 for removed /start-trial route, got {response.status_code}"
        )


# ============================================================================
# Checkout Endpoint
# ============================================================================

class TestCreateCheckout:
    """Tests for POST /api/v1/billing/checkout.

    OSS pivot (B3): /checkout route removed. All tests verify 404.
    """

    def test_create_checkout_session_pro(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /checkout route is removed in self-hosted OSS — returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_session_business(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /checkout route is removed — returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "business",
                "billing_cycle": "annual",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_invalid_plan(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /checkout route removed — even invalid plans return 404 (route gone)."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "ultra",
                "billing_cycle": "monthly",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_invalid_billing_cycle(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /checkout route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "pro",
                "billing_cycle": "weekly",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_stripe_error(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /checkout route removed — returns 404 (no Stripe in self-hosted)."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_unauthenticated(self, client: TestClient):
        """B3: /checkout route removed — unauthenticated request also returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code == 404


# ============================================================================
# Portal Endpoint
# ============================================================================

class TestCreatePortal:
    """Tests for POST /api/v1/billing/portal.

    OSS pivot (B3): /portal route removed. All tests verify 404.
    """

    def test_create_portal_session_owner(
        self, client: TestClient, pro_owner_headers: dict
    ):
        """B3: /portal route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/portal",
            headers=pro_owner_headers,
            json={"return_url": "https://app.example.com/settings/billing"},
        )
        assert response.status_code == 404

    def test_create_portal_no_stripe_customer(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /portal route removed — returns 404 regardless of customer."""
        response = client.post(
            "/api/v1/billing/portal",
            headers=owner_headers,
            json={"return_url": "https://app.example.com/settings/billing"},
        )
        assert response.status_code == 404


# ============================================================================
# Usage Endpoint
# ============================================================================

class TestGetUsage:
    """Tests for GET /api/v1/billing/usage."""

    def test_get_usage_free_tier(
        self, client: TestClient, owner_headers: dict, free_usage: UsageRecord
    ):
        """Free plan returns 250 feedback limit (SELF_HOSTED=false default)."""
        response = client.get(
            "/api/v1/billing/usage", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["feedback_limit"] == 250

    def test_get_usage_pro_tier(
        self, client: TestClient, pro_owner_headers: dict, pro_subscription: Subscription,
        db: Session, pro_org: Organization
    ):
        """Pro plan returns 2500 feedback limit (SELF_HOSTED=false default).

        B4 cleanup: usage period is now the current calendar month, not the
        Stripe subscription period.
        """
        # Create a usage record for the current calendar month (new Stripe-free window)
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            month_end = month_start.replace(year=now.year + 1, month=1)
        else:
            month_end = month_start.replace(month=now.month + 1)

        usage = UsageRecord(
            organization_id=pro_org.id,
            period_start=month_start,
            period_end=month_end,
            feedback_count=100,
        )
        db.add(usage)
        db.commit()

        response = client.get(
            "/api/v1/billing/usage", headers=pro_owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["feedback_limit"] == 2500
        assert data["feedback_used"] == 100


# ============================================================================
# Webhook Endpoint
# ============================================================================

class TestStripeWebhook:
    """Tests for POST /api/v1/billing/webhooks/stripe.

    OSS pivot (B3): /webhooks/stripe route removed. All tests verify 404.
    """

    def test_webhook_invalid_signature(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "fake"}',
            headers={"Stripe-Signature": "invalid_sig"},
        )
        assert response.status_code == 404

    def test_webhook_missing_signature(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "test"}',
        )
        assert response.status_code == 404

    def test_webhook_checkout_completed(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig_123"},
        )
        assert response.status_code == 404

    def test_webhook_subscription_updated(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "customer.subscription.updated"}',
            headers={"Stripe-Signature": "valid_sig_456"},
        )
        assert response.status_code == 404

    def test_webhook_subscription_deleted(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "customer.subscription.deleted"}',
            headers={"Stripe-Signature": "valid_sig_789"},
        )
        assert response.status_code == 404

    def test_webhook_invoice_payment_failed(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "invoice.payment_failed"}',
            headers={"Stripe-Signature": "valid_sig_fail"},
        )
        assert response.status_code == 404

    def test_webhook_unknown_event_ignored(self, client: TestClient):
        """B3: /webhooks/stripe removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "some.unknown.event"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 404


# ============================================================================
# Feedback Limit Enforcement (check_feedback_limit dependency)
# ============================================================================

class TestFeedbackLimitEnforcement:
    """Tests for feedback limit checks.

    OSS pivot (B1): SELF_HOSTED=true returns None for all limits (unlimited).
    """

    def test_feedback_limit_is_unlimited_in_self_hosted(
        self, db: Session, owner_org: Organization
    ):
        """B1: In self-hosted mode, get_feedback_limit always returns None."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_feedback_limit("free") is None
            assert plans_mod.get_feedback_limit("pro") is None
            assert plans_mod.get_feedback_limit("enterprise") is None

    def test_feedback_limit_tiered_when_not_self_hosted(self, db: Session):
        """Tiered limits are preserved when SELF_HOSTED=false."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_feedback_limit("free") == 250
            assert plans_mod.get_feedback_limit("pro") == 2500

    def test_feedback_limit_enterprise_unlimited(self):
        """Enterprise tier has no feedback limit regardless of SELF_HOSTED."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_feedback_limit("enterprise") is None


# ============================================================================
# Feature Gating (require_feature dependency)
# ============================================================================

class TestFeatureGating:
    """Tests for the require_feature dependency.

    OSS pivot (B1): In SELF_HOSTED mode, all features return True regardless of plan.
    Tiered behavior is preserved when SELF_HOSTED=false.
    """

    def test_all_features_available_in_self_hosted_mode(self):
        """B1: SELF_HOSTED=true makes has_feature always return True."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            # All plans and all features return True
            assert plans_mod.has_feature("free", "slack_integration") is True
            assert plans_mod.has_feature("free", "api_access") is True
            assert plans_mod.has_feature("free", "sso_saml") is True
            assert plans_mod.has_feature("pro", "sso_saml") is True

    def test_feature_available_for_correct_plan_when_not_self_hosted(self):
        """Tiered feature access when SELF_HOSTED=false."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.has_feature("free", "basic_dashboard") is True
            assert plans_mod.has_feature("free", "csv_import") is True
            assert plans_mod.has_feature("pro", "slack_integration") is True
            assert plans_mod.has_feature("business", "api_access") is True
            assert plans_mod.has_feature("enterprise", "sso_saml") is True

    def test_feature_blocked_for_wrong_plan_when_not_self_hosted(self):
        """Feature not included in lower plan returns False when SELF_HOSTED=false."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.has_feature("free", "slack_integration") is False
            assert plans_mod.has_feature("free", "api_access") is False
            assert plans_mod.has_feature("pro", "api_access") is False
            assert plans_mod.has_feature("pro", "sso_saml") is False
            assert plans_mod.has_feature("business", "sso_saml") is False

    def test_plan_hierarchy_when_not_self_hosted(self):
        """Plan hierarchy comparison works correctly when SELF_HOSTED=false."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.plan_includes("free", "free") is True
            assert plans_mod.plan_includes("pro", "free") is True
            assert plans_mod.plan_includes("business", "pro") is True
            assert plans_mod.plan_includes("enterprise", "business") is True
            assert plans_mod.plan_includes("free", "pro") is False
            assert plans_mod.plan_includes("pro", "business") is False
            assert plans_mod.plan_includes("business", "enterprise") is False

    def test_plan_hierarchy_all_true_in_self_hosted_mode(self):
        """B1: SELF_HOSTED=true makes plan_includes always return True."""
        import importlib
        import os
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.plan_includes("free", "pro") is True
            assert plans_mod.plan_includes("free", "enterprise") is True


# ============================================================================
# Invoices Endpoint
# ============================================================================

class TestGetInvoices:
    """Tests for GET /api/v1/billing/invoices.

    OSS pivot (B3): /invoices route removed. All tests verify 404.
    """

    def test_get_invoices_no_stripe_customer(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /invoices route removed — returns 404."""
        response = client.get(
            "/api/v1/billing/invoices", headers=owner_headers
        )
        assert response.status_code == 404

    def test_get_invoices_with_stripe_customer(
        self, client: TestClient, pro_owner_headers: dict
    ):
        """B3: /invoices route removed — returns 404 even with Stripe customer."""
        response = client.get(
            "/api/v1/billing/invoices", headers=pro_owner_headers
        )
        assert response.status_code == 404
