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
    """Create a free-plan org that already has a Stripe customer ID."""
    org = Organization(
        name="Promo Stripe Org",
        plan="free",
        stripe_customer_id="cus_promo_test_123",
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
        stripe_customer_id="cus_promo_activated",
        promo_code_used="EARLYPRO3",
    )
    db.add(org)
    db.flush()

    now = datetime.utcnow()
    sub = Subscription(
        organization_id=org.id,
        stripe_subscription_id="sub_promo_activated",
        stripe_price_id="price_pro_monthly_test",
        plan="pro",
        billing_cycle="monthly",
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
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
    """Tests for POST /api/v1/billing/checkout with promo_code."""

    @patch("src.api.routes.billing.get_stripe_service")
    def test_checkout_passes_promo_code_to_stripe_service(
        self, mock_get_stripe, client: TestClient, owner_headers: dict
    ):
        """Promo code from request is forwarded to create_checkout_session."""
        mock_service = MagicMock()
        mock_service.create_customer.return_value = "cus_new_promo"
        mock_service.create_checkout_session.return_value = "https://checkout.stripe.com/promo_session"
        mock_get_stripe.return_value = mock_service

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

        assert response.status_code == 200
        assert response.json()["checkout_url"] == "https://checkout.stripe.com/promo_session"

        # Verify promo_code was passed to stripe service
        call_kwargs = mock_service.create_checkout_session.call_args
        assert call_kwargs.kwargs.get("promo_code") == "EARLYPRO3" or \
               (len(call_kwargs.args) > 6 and call_kwargs.args[6] == "EARLYPRO3") or \
               call_kwargs[1].get("promo_code") == "EARLYPRO3"

    @patch("src.api.routes.billing.get_stripe_service")
    def test_checkout_without_promo_passes_none(
        self, mock_get_stripe, client: TestClient, owner_headers: dict
    ):
        """Checkout without promo_code passes None to stripe service."""
        mock_service = MagicMock()
        mock_service.create_customer.return_value = "cus_no_promo"
        mock_service.create_checkout_session.return_value = "https://checkout.stripe.com/no_promo"
        mock_get_stripe.return_value = mock_service

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

        assert response.status_code == 200

        # Verify promo_code is None
        call_kwargs = mock_service.create_checkout_session.call_args
        assert call_kwargs.kwargs.get("promo_code") is None or \
               call_kwargs[1].get("promo_code") is None

    @patch("src.api.routes.billing.get_stripe_service")
    def test_checkout_with_promo_creates_stripe_customer_if_missing(
        self, mock_get_stripe, client: TestClient, owner_headers: dict, db: Session, free_org: Organization
    ):
        """Org without Stripe customer ID gets one created during promo checkout."""
        assert free_org.stripe_customer_id is None

        mock_service = MagicMock()
        mock_service.create_customer.return_value = "cus_brand_new"
        mock_service.create_checkout_session.return_value = "https://checkout.stripe.com/new_cus"
        mock_get_stripe.return_value = mock_service

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

        assert response.status_code == 200
        mock_service.create_customer.assert_called_once()

        db.refresh(free_org)
        assert free_org.stripe_customer_id == "cus_brand_new"


# ============================================================================
# Webhook: Checkout Completed with Promo
# ============================================================================

class TestWebhookCheckoutWithPromo:
    """Tests for checkout.session.completed webhook handling promo codes."""

    @patch("stripe.PromotionCode.retrieve")
    @patch("stripe.checkout.Session.retrieve")
    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_stores_promo_code_on_org(
        self, mock_get_stripe, mock_session_retrieve, mock_promo_retrieve,
        client: TestClient, db: Session, free_org_with_stripe: Organization
    ):
        """Webhook extracts promo code from Stripe session and stores it on org."""
        org = free_org_with_stripe
        now = datetime.utcnow()

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_promo_session_123",
                    "customer": org.stripe_customer_id,
                    "subscription": "sub_promo_123",
                }
            },
        }
        mock_service.get_subscription.return_value = {
            "id": "sub_promo_123",
            "status": "active",
            "current_period_start": now,
            "current_period_end": now + timedelta(days=90),
            "cancel_at_period_end": False,
            "canceled_at": None,
            "trial_start": None,
            "trial_end": None,
            "price_id": "price_pro_monthly_test",
        }
        mock_service.api_key = "sk_test_fake"
        mock_get_stripe.return_value = mock_service

        # Mock Session.retrieve to return discount data
        mock_session_obj = MagicMock()
        mock_session_obj.get.side_effect = lambda key, default=None: {
            "total_details": {
                "breakdown": {
                    "discounts": [
                        {
                            "discount": {
                                "promotion_code": "promo_abc123",
                            }
                        }
                    ]
                }
            }
        }.get(key, default)
        mock_session_retrieve.return_value = mock_session_obj

        # Mock PromotionCode.retrieve to return the code string
        mock_promo_obj = MagicMock()
        mock_promo_obj.code = "EARLYPRO3"
        mock_promo_retrieve.return_value = mock_promo_obj

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )

        assert response.status_code == 200

        db.refresh(org)
        assert org.promo_code_used == "EARLYPRO3"

    @patch("stripe.checkout.Session.retrieve")
    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_upgrades_plan_to_pro(
        self, mock_get_stripe, mock_session_retrieve,
        client: TestClient, db: Session, free_org_with_stripe: Organization
    ):
        """Webhook upgrades org.plan from free to pro after promo checkout."""
        org = free_org_with_stripe
        assert org.plan == "free"

        now = datetime.utcnow()

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_upgrade_123",
                    "customer": org.stripe_customer_id,
                    "subscription": "sub_upgrade_123",
                }
            },
        }
        mock_service.get_subscription.return_value = {
            "id": "sub_upgrade_123",
            "status": "active",
            "current_period_start": now,
            "current_period_end": now + timedelta(days=30),
            "cancel_at_period_end": False,
            "canceled_at": None,
            "trial_start": None,
            "trial_end": None,
            "price_id": "price_pro_monthly_test",
        }
        mock_service.api_key = "sk_test_fake"
        mock_get_stripe.return_value = mock_service

        # Mock Session.retrieve (no discounts)
        mock_session_obj = MagicMock()
        mock_session_obj.get.side_effect = lambda key, default=None: {
            "total_details": {"breakdown": {"discounts": []}}
        }.get(key, default)
        mock_session_retrieve.return_value = mock_session_obj

        # Set env var so _get_plan_from_price_id returns "pro"
        with patch.dict(os.environ, {"STRIPE_PRICE_PRO_MONTHLY": "price_pro_monthly_test"}):
            response = client.post(
                "/api/v1/billing/webhooks/stripe",
                content=b'{"type": "checkout.session.completed"}',
                headers={"Stripe-Signature": "valid_sig"},
            )

        assert response.status_code == 200

        db.refresh(org)
        assert org.plan == "pro"

        # Verify subscription record was created
        sub = db.query(Subscription).filter(
            Subscription.organization_id == org.id
        ).first()
        assert sub is not None
        assert sub.plan == "pro"
        assert sub.status == "active"
        assert sub.stripe_subscription_id == "sub_upgrade_123"

    @patch("stripe.checkout.Session.retrieve")
    @patch("src.api.routes.billing.get_stripe_service")
    def test_webhook_without_promo_leaves_promo_code_null(
        self, mock_get_stripe, mock_session_retrieve,
        client: TestClient, db: Session, free_org_with_stripe: Organization
    ):
        """Checkout without promo code leaves org.promo_code_used as None."""
        org = free_org_with_stripe
        assert org.promo_code_used is None

        now = datetime.utcnow()

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_no_promo_123",
                    "customer": org.stripe_customer_id,
                    "subscription": "sub_no_promo_123",
                }
            },
        }
        mock_service.get_subscription.return_value = {
            "id": "sub_no_promo_123",
            "status": "active",
            "current_period_start": now,
            "current_period_end": now + timedelta(days=30),
            "cancel_at_period_end": False,
            "canceled_at": None,
            "trial_start": None,
            "trial_end": None,
            "price_id": "price_pro_monthly_test",
        }
        mock_service.api_key = "sk_test_fake"
        mock_get_stripe.return_value = mock_service

        # No discounts in session
        mock_session_obj = MagicMock()
        mock_session_obj.get.side_effect = lambda key, default=None: {
            "total_details": {"breakdown": {"discounts": []}}
        }.get(key, default)
        mock_session_retrieve.return_value = mock_session_obj

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )

        assert response.status_code == 200

        db.refresh(org)
        assert org.promo_code_used is None


# ============================================================================
# Auto-Downgrade After Promo Expires
# ============================================================================

class TestPromoAutoDowngrade:
    """Tests for subscription deletion downgrading a promo org back to free."""

    @patch("src.api.routes.billing.get_stripe_service")
    def test_subscription_deleted_downgrades_promo_org_to_free(
        self, mock_get_stripe, client: TestClient, db: Session, promo_org_with_sub: tuple
    ):
        """When Stripe cancels subscription (promo expired), org downgrades to free."""
        org, sub = promo_org_with_sub
        assert org.plan == "pro"
        assert org.promo_code_used == "EARLYPRO3"

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": sub.stripe_subscription_id,
                    "customer": org.stripe_customer_id,
                }
            },
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "customer.subscription.deleted"}',
            headers={"Stripe-Signature": "valid_sig"},
        )

        assert response.status_code == 200

        db.refresh(org)
        assert org.plan == "free"
        # promo_code_used is preserved for historical tracking
        assert org.promo_code_used == "EARLYPRO3"

        db.refresh(sub)
        assert sub.status == "canceled"
        assert sub.plan == "free"

    @patch("src.api.routes.billing.get_stripe_service")
    def test_payment_failed_marks_promo_sub_past_due(
        self, mock_get_stripe, client: TestClient, db: Session, promo_org_with_sub: tuple
    ):
        """Failed payment after promo ends marks subscription as past_due."""
        org, sub = promo_org_with_sub

        mock_service = MagicMock()
        mock_service.verify_webhook_signature.return_value = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": org.stripe_customer_id,
                    "subscription": sub.stripe_subscription_id,
                }
            },
        }
        mock_get_stripe.return_value = mock_service

        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b'{"type": "invoice.payment_failed"}',
            headers={"Stripe-Signature": "valid_sig"},
        )

        assert response.status_code == 200

        db.refresh(sub)
        assert sub.status == "past_due"

        # Org still on pro until subscription is actually deleted
        db.refresh(org)
        assert org.plan == "pro"


# ============================================================================
# Stripe Service: Promo Code Session Creation (unit tests)
# ============================================================================

class TestStripeServicePromoCode:
    """Unit tests for StripeService.create_checkout_session promo handling."""

    @patch("src.services.stripe_service.stripe")
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

    @patch("src.services.stripe_service.stripe")
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

    @patch("src.services.stripe_service.stripe")
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
