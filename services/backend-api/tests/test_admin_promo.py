"""
Tests for admin promo code management — Stripe service methods + API routes.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.services.stripe_service import StripeService
from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


class TestListPromotionCodes:
    """Tests for StripeService.list_promotion_codes."""

    @patch("stripe.PromotionCode.list")
    def test_list_returns_promo_codes(self, mock_list):
        """Should call stripe.PromotionCode.list and return data."""
        mock_promo = MagicMock()
        mock_promo.id = "promo_abc123"
        mock_promo.code = "EARLYPRO3"
        mock_promo.active = True
        mock_list.return_value = MagicMock(data=[mock_promo])

        service = StripeService()
        result = service.list_promotion_codes(limit=50)

        mock_list.assert_called_once_with(limit=50, expand=["data.coupon"])
        assert len(result) == 1
        assert result[0].id == "promo_abc123"

    @patch("stripe.PromotionCode.list")
    def test_list_with_active_filter(self, mock_list):
        """Should pass active filter to Stripe when provided."""
        mock_list.return_value = MagicMock(data=[])

        service = StripeService()
        result = service.list_promotion_codes(limit=25, active=True)

        mock_list.assert_called_once_with(limit=25, active=True, expand=["data.coupon"])
        assert result == []


class TestGetPromotionCode:
    """Tests for StripeService.get_promotion_code."""

    @patch("stripe.PromotionCode.retrieve")
    def test_get_returns_promo_code(self, mock_retrieve):
        """Should retrieve a promotion code by ID."""
        mock_promo = MagicMock()
        mock_promo.id = "promo_abc123"
        mock_promo.code = "EARLYPRO3"
        mock_retrieve.return_value = mock_promo

        service = StripeService()
        result = service.get_promotion_code("promo_abc123")

        mock_retrieve.assert_called_once_with("promo_abc123", expand=["coupon"])
        assert result.id == "promo_abc123"

    @patch("stripe.PromotionCode.retrieve")
    def test_get_returns_none_on_stripe_error(self, mock_retrieve):
        """Should return None when Stripe raises an error."""
        import stripe as stripe_module
        mock_retrieve.side_effect = stripe_module.error.InvalidRequestError(
            "No such promotion code", param="id"
        )

        service = StripeService()
        result = service.get_promotion_code("promo_nonexistent")
        assert result is None


class TestCreateCouponAndPromo:
    """Tests for StripeService.create_coupon_and_promo."""

    @patch("stripe.PromotionCode.create")
    @patch("stripe.Coupon.create")
    def test_create_coupon_and_promo_success(self, mock_coupon_create, mock_promo_create):
        """Should create coupon first, then promotion code with coupon ID."""
        mock_coupon = MagicMock()
        mock_coupon.id = "coupon_abc"
        mock_coupon_create.return_value = mock_coupon

        mock_promo = MagicMock()
        mock_promo.id = "promo_xyz"
        mock_promo.code = "EARLYPRO3"
        mock_promo_create.return_value = mock_promo

        service = StripeService()
        coupon_params = {"name": "3 Months Free", "percent_off": 100, "duration": "repeating", "duration_in_months": 3}
        promo_params = {"code": "EARLYPRO3", "max_redemptions": 50}
        result = service.create_coupon_and_promo(coupon_params, promo_params)

        mock_coupon_create.assert_called_once_with(**coupon_params)
        mock_promo_create.assert_called_once_with(coupon="coupon_abc", code="EARLYPRO3", max_redemptions=50)
        assert result.id == "promo_xyz"

    @patch("stripe.Coupon.create")
    def test_create_raises_on_coupon_error(self, mock_coupon_create):
        """Should propagate Stripe error if coupon creation fails."""
        import stripe as stripe_module
        mock_coupon_create.side_effect = stripe_module.error.InvalidRequestError(
            "Invalid params", param="percent_off"
        )

        service = StripeService()
        with pytest.raises(stripe_module.error.StripeError):
            service.create_coupon_and_promo(
                {"percent_off": 200},
                {"code": "BAD"}
            )


class TestDeactivatePromotionCode:
    """Tests for StripeService.deactivate_promotion_code."""

    @patch("stripe.PromotionCode.modify")
    def test_deactivate_success(self, mock_modify):
        """Should call stripe.PromotionCode.modify with active=False."""
        mock_modify.return_value = MagicMock(id="promo_abc", active=False)

        service = StripeService()
        result = service.deactivate_promotion_code("promo_abc")

        mock_modify.assert_called_once_with("promo_abc", active=False)
        assert result is True

    @patch("stripe.PromotionCode.modify")
    def test_deactivate_returns_false_on_error(self, mock_modify):
        """Should return False when Stripe raises an error."""
        import stripe as stripe_module
        mock_modify.side_effect = stripe_module.error.InvalidRequestError(
            "No such promotion code", param="id"
        )

        service = StripeService()
        result = service.deactivate_promotion_code("promo_nonexistent")
        assert result is False


class TestDeletePromotionCode:
    """Tests for StripeService.delete_promotion_code."""

    @patch("stripe.Coupon.delete")
    @patch("stripe.PromotionCode.modify")
    def test_delete_deactivates_and_deletes_coupon(self, mock_modify, mock_coupon_delete):
        """Should deactivate promo code and delete the coupon."""
        mock_modify.return_value = MagicMock(active=False)
        mock_coupon_delete.return_value = MagicMock(deleted=True)

        service = StripeService()
        result = service.delete_promotion_code("promo_abc", "coupon_xyz")

        mock_modify.assert_called_once_with("promo_abc", active=False)
        mock_coupon_delete.assert_called_once_with("coupon_xyz")
        assert result is True

    @patch("stripe.Coupon.delete")
    @patch("stripe.PromotionCode.modify")
    def test_delete_returns_true_even_if_coupon_delete_fails(self, mock_modify, mock_coupon_delete):
        """Should return True even if coupon deletion fails (promo was deactivated)."""
        import stripe as stripe_module
        mock_modify.return_value = MagicMock(active=False)
        mock_coupon_delete.side_effect = stripe_module.error.InvalidRequestError(
            "Coupon in use", param="id"
        )

        service = StripeService()
        result = service.delete_promotion_code("promo_abc", "coupon_xyz")
        assert result is True

    @patch("stripe.PromotionCode.modify")
    def test_delete_returns_false_if_deactivate_fails(self, mock_modify):
        """Should return False if promo deactivation itself fails."""
        import stripe as stripe_module
        mock_modify.side_effect = stripe_module.error.InvalidRequestError(
            "No such promotion code", param="id"
        )

        service = StripeService()
        result = service.delete_promotion_code("promo_nonexistent", "coupon_xyz")
        assert result is False


# ──────────────────────────────────────────────────────────────
# Route Tests — Admin Promo API
# ──────────────────────────────────────────────────────────────


def _make_stripe_promo_mock(
    promo_id="promo_abc123",
    code="EARLYPRO3",
    active=True,
    times_redeemed=2,
    max_redemptions=50,
):
    """Helper to build a realistic Stripe PromotionCode-like dict."""
    coupon = {
        "id": "coupon_xyz",
        "name": "3 Months Free Pro",
        "percent_off": 100.0,
        "amount_off": None,
        "currency": None,
        "duration": "repeating",
        "duration_in_months": 3,
    }
    return {
        "id": promo_id,
        "code": code,
        "active": active,
        "coupon": coupon,
        "max_redemptions": max_redemptions,
        "times_redeemed": times_redeemed,
        "expires_at": None,
        "created": 1700000000,
        "metadata": {},
        "customer": None,
        "restrictions": {
            "first_time_transaction": True,
            "minimum_amount": None,
            "minimum_amount_currency": None,
        },
    }


@pytest.fixture
def system_admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="admin@promo.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
        is_system_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def system_admin_headers(system_admin_user: User) -> dict:
    token = create_access_token({
        "user_id": system_admin_user.id,
        "organization_id": system_admin_user.organization_id,
        "role": system_admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def regular_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="regular@promo.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def regular_headers(regular_user: User) -> dict:
    token = create_access_token({
        "user_id": regular_user.id,
        "organization_id": regular_user.organization_id,
        "role": regular_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestAdminPromoListRoute:
    """Tests for GET /api/v1/admin/promo-codes."""

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_list_promo_codes_success(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should return list of promo codes from Stripe."""
        mock_service = MagicMock()
        mock_service.list_promotion_codes.return_value = [
            MagicMock(**_make_stripe_promo_mock()),
        ]
        mock_get_service.return_value = mock_service

        response = client.get("/api/v1/admin/promo-codes", headers=system_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "promo_codes" in data
        assert len(data["promo_codes"]) == 1
        assert data["promo_codes"][0]["code"] == "EARLYPRO3"

    def test_list_requires_system_admin(
        self, client: TestClient, regular_headers: dict
    ):
        """Should return 403 for non-system-admin users."""
        response = client.get("/api/v1/admin/promo-codes", headers=regular_headers)
        assert response.status_code == 403


class TestAdminPromoDetailRoute:
    """Tests for GET /api/v1/admin/promo-codes/{id}."""

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_get_promo_code_detail(
        self, mock_get_service, client: TestClient, system_admin_headers: dict,
        db: Session, test_organization: Organization,
    ):
        """Should return promo code detail with local redemptions."""
        # Set promo_code_used on the org so it shows up in redemptions
        test_organization.promo_code_used = "EARLYPRO3"
        db.commit()

        mock_service = MagicMock()
        mock_promo = MagicMock(**_make_stripe_promo_mock())
        mock_service.get_promotion_code.return_value = mock_promo
        mock_get_service.return_value = mock_service

        response = client.get("/api/v1/admin/promo-codes/promo_abc123", headers=system_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "promo_abc123"
        assert data["code"] == "EARLYPRO3"
        assert "redeemed_by" in data
        assert len(data["redeemed_by"]) == 1
        assert data["redeemed_by"][0]["organization_name"] == "Test Company"

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_get_promo_code_not_found(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should return 404 when promo code not found in Stripe."""
        mock_service = MagicMock()
        mock_service.get_promotion_code.return_value = None
        mock_get_service.return_value = mock_service

        response = client.get("/api/v1/admin/promo-codes/promo_nonexistent", headers=system_admin_headers)
        assert response.status_code == 404

    def test_get_detail_requires_system_admin(
        self, client: TestClient, regular_headers: dict
    ):
        """Should return 403 for non-system-admin users."""
        response = client.get("/api/v1/admin/promo-codes/promo_abc", headers=regular_headers)
        assert response.status_code == 403


class TestAdminPromoCreateRoute:
    """Tests for POST /api/v1/admin/promo-codes."""

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_create_promo_code_success(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should create coupon + promo code and return 201."""
        mock_service = MagicMock()
        mock_promo = MagicMock(**_make_stripe_promo_mock())
        mock_service.create_coupon_and_promo.return_value = mock_promo
        mock_get_service.return_value = mock_service

        payload = {
            "code": "EARLYPRO3",
            "coupon_name": "Early Adopter — 3 Months Free Pro",
            "discount_type": "percent",
            "percent_off": 100,
            "duration": "repeating",
            "duration_in_months": 3,
            "max_redemptions": 50,
            "first_time_transaction": True,
        }

        response = client.post("/api/v1/admin/promo-codes", json=payload, headers=system_admin_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "EARLYPRO3"
        mock_service.create_coupon_and_promo.assert_called_once()

    def test_create_requires_system_admin(
        self, client: TestClient, regular_headers: dict
    ):
        """Should return 403 for non-system-admin users."""
        payload = {
            "code": "TEST",
            "coupon_name": "Test",
            "discount_type": "percent",
            "percent_off": 50,
            "duration": "once",
        }
        response = client.post("/api/v1/admin/promo-codes", json=payload, headers=regular_headers)
        assert response.status_code == 403

    def test_create_validates_required_fields(
        self, client: TestClient, system_admin_headers: dict
    ):
        """Should return 422 when required fields are missing."""
        response = client.post("/api/v1/admin/promo-codes", json={}, headers=system_admin_headers)
        assert response.status_code == 422


class TestAdminPromoDeactivateRoute:
    """Tests for POST /api/v1/admin/promo-codes/{id}/deactivate."""

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_deactivate_success(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should deactivate a promo code and return 200."""
        mock_service = MagicMock()
        mock_service.deactivate_promotion_code.return_value = True
        mock_get_service.return_value = mock_service

        response = client.post(
            "/api/v1/admin/promo-codes/promo_abc/deactivate",
            headers=system_admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deactivated"
        mock_service.deactivate_promotion_code.assert_called_once_with("promo_abc")

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_deactivate_not_found(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should return 404 when deactivation fails."""
        mock_service = MagicMock()
        mock_service.deactivate_promotion_code.return_value = False
        mock_get_service.return_value = mock_service

        response = client.post(
            "/api/v1/admin/promo-codes/promo_nonexistent/deactivate",
            headers=system_admin_headers,
        )
        assert response.status_code == 404

    def test_deactivate_requires_system_admin(
        self, client: TestClient, regular_headers: dict
    ):
        """Should return 403 for non-system-admin users."""
        response = client.post(
            "/api/v1/admin/promo-codes/promo_abc/deactivate",
            headers=regular_headers,
        )
        assert response.status_code == 403


class TestAdminPromoDeleteRoute:
    """Tests for DELETE /api/v1/admin/promo-codes/{id}."""

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_delete_success(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should deactivate promo and delete coupon, return 200."""
        mock_service = MagicMock()
        mock_service.delete_promotion_code.return_value = True
        mock_get_service.return_value = mock_service

        response = client.delete(
            "/api/v1/admin/promo-codes/promo_abc?coupon_id=coupon_xyz",
            headers=system_admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        mock_service.delete_promotion_code.assert_called_once_with("promo_abc", "coupon_xyz")

    @patch("src.api.routes.admin_promo.get_stripe_service")
    def test_delete_not_found(
        self, mock_get_service, client: TestClient, system_admin_headers: dict
    ):
        """Should return 404 when deletion fails."""
        mock_service = MagicMock()
        mock_service.delete_promotion_code.return_value = False
        mock_get_service.return_value = mock_service

        response = client.delete(
            "/api/v1/admin/promo-codes/promo_nonexistent?coupon_id=coupon_xyz",
            headers=system_admin_headers,
        )
        assert response.status_code == 404

    def test_delete_requires_system_admin(
        self, client: TestClient, regular_headers: dict
    ):
        """Should return 403 for non-system-admin users."""
        response = client.delete(
            "/api/v1/admin/promo-codes/promo_abc?coupon_id=coupon_xyz",
            headers=regular_headers,
        )
        assert response.status_code == 403

    def test_delete_requires_coupon_id(
        self, client: TestClient, system_admin_headers: dict
    ):
        """Should return 422 when coupon_id query param is missing."""
        response = client.delete(
            "/api/v1/admin/promo-codes/promo_abc",
            headers=system_admin_headers,
        )
        assert response.status_code == 422
