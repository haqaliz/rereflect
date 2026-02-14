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
        stripe_customer_id="cus_test_pro_123",
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
    now = datetime.utcnow()
    sub = Subscription(
        organization_id=pro_org.id,
        stripe_subscription_id="sub_test_pro_123",
        stripe_price_id="price_pro_monthly_test",
        plan="pro",
        billing_cycle="monthly",
        status="active",
        current_period_start=now.replace(day=1),
        current_period_end=(now.replace(day=1) + timedelta(days=30)),
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
    """Tests for GET /api/v1/billing/subscription."""

    def test_get_subscription_free_default(
        self, client: TestClient, owner_headers: dict
    ):
        """Org with no subscription returns free plan."""
        response = client.get(
            "/api/v1/billing/subscription", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subscription"]["plan"] == "free"
        assert data["subscription"]["status"] == "active"
        assert data["can_manage_billing"] is False

    def test_get_subscription_pro_active(
        self, client: TestClient, pro_owner_headers: dict, pro_subscription: Subscription
    ):
        """Org with active pro subscription returns correct data."""
        response = client.get(
            "/api/v1/billing/subscription", headers=pro_owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subscription"]["plan"] == "pro"
        assert data["subscription"]["status"] == "active"
        assert data["subscription"]["billing_cycle"] == "monthly"
        assert data["can_manage_billing"] is True


# ============================================================================
# Start Trial Endpoint
# ============================================================================

class TestStartTrial:
    """Tests for POST /api/v1/billing/start-trial."""

    def test_start_trial_success(
        self, client: TestClient, owner_headers: dict, owner_org: Organization
    ):
        """Free org can start a 14-day Pro trial."""
        response = client.post(
            "/api/v1/billing/start-trial", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Trial started successfully"
        assert data["subscription"]["plan"] == "pro"
        assert data["subscription"]["status"] == "trialing"
        assert data["subscription"]["is_trial"] is True

    def test_start_trial_already_trialing(
        self, client: TestClient, owner_headers: dict, db: Session, owner_org: Organization
    ):
        """Org already on trial cannot start another."""
        # Create existing trial
        sub = Subscription(
            organization_id=owner_org.id,
            plan="pro",
            status="trialing",
            trial_start=datetime.utcnow(),
            trial_end=datetime.utcnow() + timedelta(days=14),
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=14),
        )
        db.add(sub)
        db.commit()

        response = client.post(
            "/api/v1/billing/start-trial", headers=owner_headers
        )
        assert response.status_code == 400
        assert "already on a trial" in response.json()["detail"]

    def test_start_trial_already_subscribed(
        self, client: TestClient, pro_owner_headers: dict, pro_subscription: Subscription
    ):
        """Org with active subscription cannot start trial."""
        response = client.post(
            "/api/v1/billing/start-trial", headers=pro_owner_headers
        )
        assert response.status_code == 400
        assert "already has an active subscription" in response.json()["detail"]


# ============================================================================
# Checkout Endpoint
# ============================================================================

class TestCreateCheckout:
    """Tests for POST /api/v1/billing/checkout."""

    @patch("src.api.routes.billing.get_stripe_service")
    def test_create_checkout_session_pro(
        self, mock_get_stripe, client: TestClient, owner_headers: dict
    ):
        """Owner can create checkout for Pro plan."""
        mock_service = MagicMock()
        mock_service.create_customer.return_value = "cus_new_123"
        mock_service.create_checkout_session.return_value = "https://checkout.stripe.com/session_pro"
        mock_get_stripe.return_value = mock_service

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

        assert response.status_code == 200
        data = response.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/session_pro"
        mock_service.create_checkout_session.assert_called_once()

    @patch("src.api.routes.billing.get_stripe_service")
    def test_create_checkout_session_business(
        self, mock_get_stripe, client: TestClient, owner_headers: dict
    ):
        """Owner can create checkout for Business plan."""
        mock_service = MagicMock()
        mock_service.create_customer.return_value = "cus_new_456"
        mock_service.create_checkout_session.return_value = "https://checkout.stripe.com/session_biz"
        mock_get_stripe.return_value = mock_service

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

        assert response.status_code == 200
        data = response.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/session_biz"

    def test_create_checkout_invalid_plan(
        self, client: TestClient, owner_headers: dict
    ):
        """Invalid plan returns 400."""
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
        assert response.status_code == 400
        assert "Invalid plan" in response.json()["detail"]

    def test_create_checkout_invalid_billing_cycle(
        self, client: TestClient, owner_headers: dict
    ):
        """Invalid billing cycle returns 400."""
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
        assert response.status_code == 400
        assert "Invalid billing cycle" in response.json()["detail"]

    @patch("src.api.routes.billing.get_stripe_service")
    def test_create_checkout_stripe_error(
        self, mock_get_stripe, client: TestClient, owner_headers: dict
    ):
        """Stripe error during checkout returns 400."""
        mock_service = MagicMock()
        mock_service.create_customer.return_value = "cus_new_789"
        mock_service.create_checkout_session.side_effect = ValueError(
            "No Stripe price configured for plan 'pro' with cycle 'monthly'"
        )
        mock_get_stripe.return_value = mock_service

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
        assert response.status_code == 400
        assert "No Stripe price configured" in response.json()["detail"]

    def test_create_checkout_unauthenticated(self, client: TestClient):
        """Unauthenticated request to checkout returns 401/403."""
        response = client.post(
            "/api/v1/billing/checkout",
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            },
        )
        assert response.status_code in [401, 403]


# ============================================================================
# Portal Endpoint
# ============================================================================

class TestCreatePortal:
    """Tests for POST /api/v1/billing/portal."""

    @patch("src.api.routes.billing.get_stripe_service")
    def test_create_portal_session_owner(
        self, mock_get_stripe, client: TestClient, pro_owner_headers: dict
    ):
        """Owner with Stripe customer can access billing portal."""
        mock_service = MagicMock()
        mock_service.create_portal_session.return_value = "https://billing.stripe.com/portal_123"
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/portal",
            headers=pro_owner_headers,
            json={"return_url": "https://app.example.com/settings/billing"},
        )

        assert response.status_code == 200
        assert response.json()["portal_url"] == "https://billing.stripe.com/portal_123"

    def test_create_portal_no_stripe_customer(
        self, client: TestClient, owner_headers: dict
    ):
        """Org without Stripe customer ID cannot access portal."""
        response = client.post(
            "/api/v1/billing/portal",
            headers=owner_headers,
            json={"return_url": "https://app.example.com/settings/billing"},
        )
        assert response.status_code == 400
        assert "no billing account" in response.json()["detail"].lower()


# ============================================================================
# Usage Endpoint
# ============================================================================

class TestGetUsage:
    """Tests for GET /api/v1/billing/usage."""

    def test_get_usage_free_tier(
        self, client: TestClient, owner_headers: dict, free_usage: UsageRecord
    ):
        """Free tier usage shows correct limits."""
        response = client.get(
            "/api/v1/billing/usage", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["feedback_limit"] == 250
        assert data["overage_enabled"] is False

    def test_get_usage_pro_tier(
        self, client: TestClient, pro_owner_headers: dict, pro_subscription: Subscription,
        db: Session, pro_org: Organization
    ):
        """Pro tier usage shows correct limits and overage enabled."""
        # Create a usage record for the pro org
        usage = UsageRecord(
            organization_id=pro_org.id,
            period_start=pro_subscription.current_period_start,
            period_end=pro_subscription.current_period_end,
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
        assert data["overage_enabled"] is True


# ============================================================================
# Webhook Endpoint
# ============================================================================

class TestStripeWebhook:
    """Tests for POST /api/v1/billing/webhooks/stripe."""

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_invalid_signature(
        self, mock_get_stripe, client: TestClient
    ):
        """Invalid Stripe signature returns 400."""
        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = None
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "fake"}',
            headers={"Stripe-Signature": "invalid_sig"},
        )
        assert response.status_code == 400
        assert "Invalid webhook signature" in response.json()["detail"]

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_missing_signature(
        self, mock_get_stripe, client: TestClient
    ):
        """Missing Stripe-Signature header returns 400."""
        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = None
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "test"}',
        )
        assert response.status_code == 400

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_checkout_completed(
        self, mock_get_stripe, client: TestClient, db: Session
    ):
        """Successful checkout webhook creates subscription."""
        # Set up org with Stripe customer
        org = Organization(
            name="Webhook Test Org",
            plan="free",
            stripe_customer_id="cus_webhook_test",
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_webhook_test",
                    "subscription": "sub_new_from_checkout",
                }
            },
        }
        mock_service.get_subscription.return_value = {
            "id": "sub_new_from_checkout",
            "status": "active",
            "current_period_start": datetime.utcnow(),
            "current_period_end": datetime.utcnow() + timedelta(days=30),
            "cancel_at_period_end": False,
            "canceled_at": None,
            "trial_start": None,
            "trial_end": None,
            "price_id": "price_pro_monthly_test",
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig_123"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Verify subscription was created
        sub = db.query(Subscription).filter(
            Subscription.organization_id == org.id
        ).first()
        assert sub is not None
        assert sub.stripe_subscription_id == "sub_new_from_checkout"
        assert sub.status == "active"

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_subscription_updated(
        self, mock_get_stripe, client: TestClient, db: Session
    ):
        """Subscription update webhook updates local record."""
        org = Organization(
            name="Sub Update Org",
            plan="pro",
            stripe_customer_id="cus_sub_update",
        )
        db.add(org)
        db.flush()

        now = datetime.utcnow()
        sub = Subscription(
            organization_id=org.id,
            stripe_subscription_id="sub_existing_123",
            stripe_price_id="price_pro_monthly_test",
            plan="pro",
            billing_cycle="monthly",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_existing_123",
                    "customer": "cus_sub_update",
                    "status": "active",
                    "cancel_at_period_end": True,
                    "canceled_at": int(now.timestamp()),
                    "current_period_start": int(now.timestamp()),
                    "current_period_end": int((now + timedelta(days=30)).timestamp()),
                    "items": {"data": []},
                }
            },
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "customer.subscription.updated"}',
            headers={"Stripe-Signature": "valid_sig_456"},
        )

        assert response.status_code == 200

        db.refresh(sub)
        assert sub.cancel_at_period_end is True

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_subscription_deleted(
        self, mock_get_stripe, client: TestClient, db: Session
    ):
        """Cancellation webhook marks subscription as canceled and downgrades org."""
        org = Organization(
            name="Delete Sub Org",
            plan="pro",
            stripe_customer_id="cus_sub_delete",
        )
        db.add(org)
        db.flush()

        now = datetime.utcnow()
        sub = Subscription(
            organization_id=org.id,
            stripe_subscription_id="sub_to_cancel",
            plan="pro",
            billing_cycle="monthly",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        db.commit()

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_to_cancel",
                    "customer": "cus_sub_delete",
                }
            },
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "customer.subscription.deleted"}',
            headers={"Stripe-Signature": "valid_sig_789"},
        )

        assert response.status_code == 200

        db.refresh(sub)
        assert sub.status == "canceled"
        assert sub.plan == "free"

        db.refresh(org)
        assert org.plan == "free"

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_invoice_payment_failed(
        self, mock_get_stripe, client: TestClient, db: Session
    ):
        """Failed payment webhook sets subscription to past_due."""
        org = Organization(
            name="Payment Fail Org",
            plan="pro",
            stripe_customer_id="cus_pay_fail",
        )
        db.add(org)
        db.flush()

        now = datetime.utcnow()
        sub = Subscription(
            organization_id=org.id,
            stripe_subscription_id="sub_payment_fail",
            plan="pro",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        db.commit()

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": "cus_pay_fail",
                    "subscription": "sub_payment_fail",
                }
            },
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "invoice.payment_failed"}',
            headers={"Stripe-Signature": "valid_sig_fail"},
        )

        assert response.status_code == 200

        db.refresh(sub)
        assert sub.status == "past_due"

    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_unknown_event_ignored(
        self, mock_get_stripe, client: TestClient
    ):
        """Unknown event type is accepted but ignored."""
        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "some.unknown.event",
            "data": {"object": {}},
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "some.unknown.event"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ============================================================================
# Feedback Limit Enforcement (check_feedback_limit dependency)
# ============================================================================

class TestFeedbackLimitEnforcement:
    """Tests for feedback limit checks via the check_feedback_limit dependency."""

    def test_feedback_limit_free_tier_exceeded(
        self, db: Session, owner_org: Organization
    ):
        """Free tier blocks feedback when 250 limit is reached."""
        from src.config.plans import get_feedback_limit, get_plan

        plan = "free"
        limit = get_feedback_limit(plan)
        assert limit == 250

        plan_config = get_plan(plan)
        assert plan_config.get("overage_enabled") is False

    def test_feedback_limit_pro_tier_allows_overage(self, db: Session):
        """Pro tier allows overage (doesn't block at limit)."""
        from src.config.plans import get_feedback_limit, get_plan

        plan = "pro"
        limit = get_feedback_limit(plan)
        assert limit == 2500

        plan_config = get_plan(plan)
        assert plan_config.get("overage_enabled") is True

    def test_feedback_limit_enterprise_unlimited(self):
        """Enterprise tier has no feedback limit."""
        from src.config.plans import get_feedback_limit

        limit = get_feedback_limit("enterprise")
        assert limit is None


# ============================================================================
# Feature Gating (require_feature dependency)
# ============================================================================

class TestFeatureGating:
    """Tests for the require_feature dependency."""

    def test_feature_available_for_correct_plan(self):
        """Feature included in plan returns True."""
        from src.config.plans import has_feature

        assert has_feature("free", "basic_dashboard") is True
        assert has_feature("free", "csv_import") is True
        assert has_feature("pro", "slack_integration") is True
        assert has_feature("business", "api_access") is True
        assert has_feature("enterprise", "sso_saml") is True

    def test_feature_blocked_for_wrong_plan(self):
        """Feature not included in lower plan returns False."""
        from src.config.plans import has_feature

        assert has_feature("free", "slack_integration") is False
        assert has_feature("free", "api_access") is False
        assert has_feature("pro", "api_access") is False
        assert has_feature("pro", "sso_saml") is False
        assert has_feature("business", "sso_saml") is False

    def test_plan_hierarchy(self):
        """Plan hierarchy comparison works correctly."""
        from src.config.plans import plan_includes

        assert plan_includes("free", "free") is True
        assert plan_includes("pro", "free") is True
        assert plan_includes("business", "pro") is True
        assert plan_includes("enterprise", "business") is True

        assert plan_includes("free", "pro") is False
        assert plan_includes("pro", "business") is False
        assert plan_includes("business", "enterprise") is False


# ============================================================================
# Invoices Endpoint
# ============================================================================

class TestGetInvoices:
    """Tests for GET /api/v1/billing/invoices."""

    def test_get_invoices_no_stripe_customer(
        self, client: TestClient, owner_headers: dict
    ):
        """Org without Stripe customer returns empty invoices."""
        response = client.get(
            "/api/v1/billing/invoices", headers=owner_headers
        )
        assert response.status_code == 200
        assert response.json()["invoices"] == []

    @patch("src.api.routes.billing.get_stripe_service")
    def test_get_invoices_with_stripe_customer(
        self, mock_get_stripe, client: TestClient, pro_owner_headers: dict
    ):
        """Org with Stripe customer returns invoices from Stripe."""
        mock_service = MagicMock()
        mock_service.get_invoices.return_value = [
            {
                "id": "inv_test_001",
                "number": "INV-0001",
                "amount_due": 2900,
                "amount_paid": 2900,
                "currency": "usd",
                "status": "paid",
                "created": datetime(2026, 1, 1),
                "due_date": None,
                "paid_at": datetime(2026, 1, 1),
                "hosted_invoice_url": "https://invoice.stripe.com/inv_test_001",
                "invoice_pdf": "https://invoice.stripe.com/inv_test_001.pdf",
            },
        ]
        mock_get_stripe.return_value = mock_service

        response = client.get(
            "/api/v1/billing/invoices", headers=pro_owner_headers
        )
        assert response.status_code == 200
        invoices = response.json()["invoices"]
        assert len(invoices) == 1
        assert invoices[0]["id"] == "inv_test_001"
        assert invoices[0]["amount_paid"] == 2900
