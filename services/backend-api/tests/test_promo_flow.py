"""
Tests for the promo code signup → checkout → activation → downgrade flow.

Covers:
- Checkout endpoint passes promo_code to Stripe service
- Stripe service creates session with discount when promo code is valid
- Webhook stores promo_code_used on organization after successful checkout
- Plan upgrades from free → pro via webhook
- Subscription deletion downgrades promo org back to free
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.subscription import Subscription
from src.api.auth import hash_password, create_access_token


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def free_org(db: Session) -> Organization:
    """Create a free-plan org (simulating fresh signup)."""
    org = Organization(name="Promo Test Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_org_with_stripe(db: Session) -> Organization:
    """Create a free-plan org (Stripe customer ID dropped in B4 OSS pivot)."""
    org = Organization(
        name="Promo Stripe Org",
        plan="free",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def owner_user(db: Session, free_org: Organization) -> User:
    """Create an owner in the free org."""
    user = User(
        email="promo-owner@test.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def promo_org_with_sub(db: Session) -> tuple[Organization, Subscription]:
    """Create a pro org that was activated via promo (simulates post-checkout state)."""
    org = Organization(
        name="Promo Activated Org",
        plan="pro",
        promo_code_used="EARLYPRO3",
    )
    db.add(org)
    db.flush()

    sub = Subscription(
        organization_id=org.id,
        plan="pro",
        status="active",
    )
    db.add(sub)
    db.commit()
    db.refresh(org)
    db.refresh(sub)
    return org, sub


# ============================================================================
# Checkout with Promo Code
# ============================================================================

class TestCheckoutWithPromoCode:
    """Tests for POST /api/v1/billing/checkout with promo_code.

    OSS pivot (B3): /checkout route removed. All tests verify 404.
    """

    def test_checkout_passes_promo_code_to_stripe_service(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /billing/checkout route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.test.com/success",
                "cancel_url": "https://app.test.com/cancel",
                "promo_code": "EARLYPRO3",
            },
        )
        assert response.status_code == 404

    def test_checkout_without_promo_passes_none(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /billing/checkout route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.test.com/success",
                "cancel_url": "https://app.test.com/cancel",
            },
        )
        assert response.status_code == 404

    def test_checkout_with_promo_creates_stripe_customer_if_missing(
        self, client: TestClient, owner_headers: dict
    ):
        """B3: /billing/checkout route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=owner_headers,
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "success_url": "https://app.test.com/success",
                "cancel_url": "https://app.test.com/cancel",
                "promo_code": "EARLYPRO3",
            },
        )
        assert response.status_code == 404


# ============================================================================
# Webhook: Checkout Completed with Promo
# ============================================================================

class TestWebhookCheckoutWithPromo:
    """Tests for checkout.session.completed webhook handling promo codes.

    OSS pivot (B3): /webhooks/stripe route removed. All tests verify 404.
    """

    def test_webhook_stores_promo_code_on_org(
        self, client: TestClient
    ):
        """B3: /billing/webhooks/stripe route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 404

    def test_webhook_upgrades_plan_to_pro(
        self, client: TestClient
    ):
        """B3: /billing/webhooks/stripe route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 404

    def test_webhook_without_promo_leaves_promo_code_null(
        self, client: TestClient
    ):
        """B3: /billing/webhooks/stripe route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 404


# ============================================================================
# Auto-Downgrade After Promo Expires
# ============================================================================

class TestPromoAutoDowngrade:
    """Tests for subscription deletion downgrading a promo org back to free.

    OSS pivot (B3): /webhooks/stripe route removed. All tests verify 404.
    """

    def test_subscription_deleted_downgrades_promo_org_to_free(
        self, client: TestClient
    ):
        """B3: /billing/webhooks/stripe route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "customer.subscription.deleted"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 404

    def test_payment_failed_marks_promo_sub_past_due(
        self, client: TestClient
    ):
        """B3: /billing/webhooks/stripe route removed — returns 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "invoice.payment_failed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert response.status_code == 404


# ============================================================================
# Stripe Service: Promo Code Session Creation (unit tests)
# ============================================================================

class TestStripeServicePromoCode:
    """Unit tests for StripeService.create_checkout_session promo handling."""

    @patch("src.services.stripe_service._stripe_pkg")
    @patch("src.services.stripe_service.get_stripe_price_id")
    def test_session_with_valid_promo_applies_discount(
        self, mock_get_price, mock_stripe
    ):
        """When promo code exists in Stripe, session is created with discount."""
        mock_get_price.return_value = "price_pro_monthly"

        # Mock PromotionCode.list to return a valid promo
        mock_promo = MagicMock()
        mock_promo.id = "promo_abc123"
        mock_stripe.PromotionCode.list.return_value = MagicMock(data=[mock_promo])

        # Mock Session.create
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/with_discount"
        mock_stripe.checkout.Session.create.return_value = mock_session

        from src.services.stripe_service import StripeService
        service = StripeService.__new__(StripeService)
        service.api_key = "sk_test_fake"

        url = service.create_checkout_session(
            customer_id="cus_test",
            plan="pro",
            billing_cycle="monthly",
            success_url="https://app.test.com/success",
            cancel_url="https://app.test.com/cancel",
            promo_code="EARLYPRO3",
        )

        assert url == "https://checkout.stripe.com/with_discount"

        # Verify the session was created with discount params
        create_call = mock_stripe.checkout.Session.create.call_args
        session_params = create_call.kwargs if create_call.kwargs else create_call[1]

        assert session_params["discounts"] == [{"promotion_code": "promo_abc123"}]
        assert "allow_promotion_codes" not in session_params
        assert session_params["payment_method_collection"] == "if_required"

    @patch("src.services.stripe_service._stripe_pkg")
    @patch("src.services.stripe_service.get_stripe_price_id")
    def test_session_with_invalid_promo_falls_back_to_manual_entry(
        self, mock_get_price, mock_stripe
    ):
        """When promo code not found in Stripe, session allows manual promo entry."""
        mock_get_price.return_value = "price_pro_monthly"

        # Mock PromotionCode.list to return empty (promo not found)
        mock_stripe.PromotionCode.list.return_value = MagicMock(data=[])

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/no_discount"
        mock_stripe.checkout.Session.create.return_value = mock_session

        from src.services.stripe_service import StripeService
        service = StripeService.__new__(StripeService)
        service.api_key = "sk_test_fake"

        url = service.create_checkout_session(
            customer_id="cus_test",
            plan="pro",
            billing_cycle="monthly",
            success_url="https://app.test.com/success",
            cancel_url="https://app.test.com/cancel",
            promo_code="INVALIDCODE",
        )

        assert url == "https://checkout.stripe.com/no_discount"

        create_call = mock_stripe.checkout.Session.create.call_args
        session_params = create_call.kwargs if create_call.kwargs else create_call[1]

        # No discount applied, but allow_promotion_codes should still be True
        assert "discounts" not in session_params
        assert session_params["allow_promotion_codes"] is True

    @patch("src.services.stripe_service._stripe_pkg")
    @patch("src.services.stripe_service.get_stripe_price_id")
    def test_session_without_promo_enables_manual_promo_entry(
        self, mock_get_price, mock_stripe
    ):
        """When no promo code provided, session allows manual entry via allow_promotion_codes."""
        mock_get_price.return_value = "price_pro_monthly"

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/standard"
        mock_stripe.checkout.Session.create.return_value = mock_session

        from src.services.stripe_service import StripeService
        service = StripeService.__new__(StripeService)
        service.api_key = "sk_test_fake"

        url = service.create_checkout_session(
            customer_id="cus_test",
            plan="pro",
            billing_cycle="monthly",
            success_url="https://app.test.com/success",
            cancel_url="https://app.test.com/cancel",
        )

        assert url == "https://checkout.stripe.com/standard"

        create_call = mock_stripe.checkout.Session.create.call_args
        session_params = create_call.kwargs if create_call.kwargs else create_call[1]

        assert session_params["allow_promotion_codes"] is True
        assert "discounts" not in session_params
        assert "payment_method_collection" not in session_params
