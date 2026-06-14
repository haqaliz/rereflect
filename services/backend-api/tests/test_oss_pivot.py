"""
Tests for OSS Self-Hosted Pivot (Workstreams A4, A6, A7, B1, B2, B3).

TDD Red → Green for every new behavior:
- B1: SELF_HOSTED flag short-circuits all plan gates (all features unlocked,
      all limits = None/unlimited).
- B2: /auth/me emits plan="enterprise" when SELF_HOSTED=true.
- A4: resolve_org_byok_key helper exists and returns BYOK only — no system key
      fallback; ai_settings._get_api_key_for_provider raises 503 when no BYOK.
- A6: AISettingsResponse no longer has a 'budget' field.
- A7: POST /settings/ai/keys no longer requires byok_keys feature gate.
- B3: Stripe-only routes are gone (404 or stripped); app boots with stripe absent;
      notifications /retention no longer calls stripe.
"""

import importlib
import os
import sys
import types
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

from src.api.auth import hash_password, create_access_token
from src.models.organization import Organization
from src.models.user import User

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="oss_owner@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
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
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_owner(db: Session, free_org: Organization) -> User:
    user = User(
        email="free_owner@test.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_owner_headers(free_owner: User) -> dict:
    token = create_access_token({
        "user_id": free_owner.id,
        "organization_id": free_owner.organization_id,
        "role": free_owner.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ─── B1: SELF_HOSTED flag in plans.py ─────────────────────────────────────────

class TestSelfHostedFlag:
    """B1: With SELF_HOSTED=true, every gate returns True/None (unlimited)."""

    def test_has_feature_returns_true_for_any_feature_when_self_hosted(self):
        """has_feature() must short-circuit to True on any feature for any plan."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            # free plan, enterprise-only feature
            assert plans_mod.has_feature("free", "sso_saml") is True
            assert plans_mod.has_feature("free", "byok_keys") is True
            assert plans_mod.has_feature("free", "custom_probability_bands") is True

    def test_plan_includes_returns_true_for_any_combo_when_self_hosted(self):
        """plan_includes() must short-circuit to True."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.plan_includes("free", "enterprise") is True
            assert plans_mod.plan_includes("free", "business") is True
            assert plans_mod.plan_includes("pro", "enterprise") is True

    def test_get_feedback_limit_returns_none_when_self_hosted(self):
        """get_feedback_limit() returns None (unlimited) for all plans."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_feedback_limit("free") is None
            assert plans_mod.get_feedback_limit("pro") is None
            assert plans_mod.get_feedback_limit("business") is None

    def test_get_seat_limit_returns_none_when_self_hosted(self):
        """get_seat_limit() returns None (unlimited) for all plans."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_seat_limit("free") is None
            assert plans_mod.get_seat_limit("pro") is None

    def test_get_saved_views_limit_returns_none_when_self_hosted(self):
        """get_saved_views_limit() returns None."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_saved_views_limit("free") is None

    def test_get_webhook_limit_returns_none_when_self_hosted(self):
        """get_webhook_limit() returns None."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_webhook_limit("free") is None

    def test_get_automation_rule_limit_returns_none_when_self_hosted(self):
        """get_automation_rule_limit() returns None."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.get_automation_rule_limit("free") is None

    def test_get_webhook_header_limit_returns_high_constant_when_self_hosted(self):
        """get_webhook_header_limit() returns a high constant (>=5) for all plans."""
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            # free plan previously returned 2, must now return high value
            assert plans_mod.get_webhook_header_limit("free") >= 5

    def test_original_tiered_behavior_when_not_self_hosted(self):
        """With SELF_HOSTED=false, tiered limits still apply (for future hosted mode)."""
        with patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            assert plans_mod.has_feature("free", "sso_saml") is False
            assert plans_mod.get_feedback_limit("free") == 250
            assert plans_mod.get_seat_limit("free") == 2
            assert plans_mod.get_webhook_header_limit("free") == 2
            assert plans_mod.plan_includes("free", "enterprise") is False


# ─── B2: /auth/me emits plan="enterprise" when SELF_HOSTED ───────────────────

class TestAuthMeSelfHosted:
    """B2: /auth/me must return plan='enterprise' when SELF_HOSTED=true."""

    def test_auth_me_returns_enterprise_plan_when_self_hosted(
        self, client: TestClient, auth_headers: dict, test_organization: Organization, db: Session
    ):
        """Even a 'free' org must see plan='enterprise' in self-hosted mode."""
        # Force org to free so we can prove the override
        test_organization.plan = "free"
        db.commit()

        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            import src.api.routes.auth as auth_mod
            importlib.reload(auth_mod)
            response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["plan"] == "enterprise"

    def test_auth_me_returns_actual_plan_when_not_self_hosted(
        self, client: TestClient, auth_headers: dict, test_organization: Organization, db: Session
    ):
        """With SELF_HOSTED=false, the real org.plan is returned."""
        test_organization.plan = "free"
        db.commit()

        with patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            import src.config.plans as plans_mod
            importlib.reload(plans_mod)
            import src.api.routes.auth as auth_mod
            importlib.reload(auth_mod)
            response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["plan"] == "free"


# ─── A4: resolve_org_byok_key helper ─────────────────────────────────────────

class TestResolveOrgByokKey:
    """A4: Helper returns BYOK key or None; NEVER falls back to env key."""

    def test_returns_decrypted_byok_key_when_present(
        self, db: Session, test_organization: Organization
    ):
        """When org has a valid BYOK key, the helper returns it."""
        from src.models.org_api_key import OrgApiKey
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            from src.utils.encryption import encrypt_api_key
            stored = OrgApiKey(
                organization_id=test_organization.id,
                provider="openai",
                encrypted_key=encrypt_api_key("sk-byok-key-test"),
                key_hint="...test",
                is_valid=True,
            )
            db.add(stored)
            db.commit()

            from src.utils.byok import resolve_org_byok_key
            result = resolve_org_byok_key("openai", test_organization.id, db)
            assert result == "sk-byok-key-test"

    def test_returns_none_when_no_byok_key(
        self, db: Session, test_organization: Organization
    ):
        """When org has no BYOK key, returns None — never uses env key."""
        with patch.dict(os.environ, {
            "LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY,
            "OPENAI_API_KEY": "sk-system-key-should-never-be-used",
        }):
            from src.utils.byok import resolve_org_byok_key
            result = resolve_org_byok_key("openai", test_organization.id, db)
            assert result is None

    def test_never_returns_env_key(
        self, db: Session, test_organization: Organization
    ):
        """Critically: the env OPENAI_API_KEY must NEVER be returned."""
        system_key = "sk-system-key-must-not-leak"
        with patch.dict(os.environ, {
            "LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY,
            "OPENAI_API_KEY": system_key,
            "ANTHROPIC_API_KEY": system_key,
            "GOOGLE_AI_API_KEY": system_key,
        }):
            from src.utils.byok import resolve_org_byok_key
            for provider in ("openai", "anthropic", "google"):
                result = resolve_org_byok_key(provider, test_organization.id, db)
                assert result != system_key, (
                    f"resolve_org_byok_key leaked system key for {provider}"
                )


# ─── A4: _get_api_key_for_provider raises 503 when no BYOK key ───────────────

class TestGetApiKeyForProviderByokOnly:
    """A4: _get_api_key_for_provider must raise 503 (not use env key) when no BYOK."""

    def test_raises_503_when_no_byok_key_and_no_env_fallback(
        self, db: Session, test_organization: Organization
    ):
        """With env key present but no BYOK, must raise HTTP 503."""
        from fastapi import HTTPException
        with patch.dict(os.environ, {
            "LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY,
            "OPENAI_API_KEY": "sk-env-key-present",
        }):
            from src.api.routes.ai_settings import _get_api_key_for_provider
            with pytest.raises(HTTPException) as exc_info:
                _get_api_key_for_provider("openai", test_organization.id, db)
            assert exc_info.value.status_code == 503

    def test_returns_byok_key_when_present(
        self, db: Session, test_organization: Organization
    ):
        """When BYOK key exists, returns it (not the env key)."""
        from src.models.org_api_key import OrgApiKey
        with patch.dict(os.environ, {
            "LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY,
            "OPENAI_API_KEY": "sk-env-key-must-not-be-used",
        }):
            from src.utils.encryption import encrypt_api_key
            stored = OrgApiKey(
                organization_id=test_organization.id,
                provider="openai",
                encrypted_key=encrypt_api_key("sk-byok-key"),
                key_hint="...byok",
                is_valid=True,
            )
            db.add(stored)
            db.commit()

            from src.api.routes.ai_settings import _get_api_key_for_provider
            result = _get_api_key_for_provider("openai", test_organization.id, db)
            assert result == "sk-byok-key"


# ─── A6: Budget removed from AISettingsResponse ───────────────────────────────

class TestAISettingsNoBudget:
    """A6: AISettingsResponse no longer contains a 'budget' field."""

    def test_get_ai_settings_has_no_budget_field(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /settings/ai must NOT return a 'budget' key."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "budget" not in data, "budget field must be removed from AISettingsResponse"

    def test_ai_settings_schema_has_no_budget_model(self):
        """AISettingsResponse Pydantic model must not have a 'budget' field."""
        from src.api.routes.ai_settings import AISettingsResponse
        assert not hasattr(AISettingsResponse, "budget") or (
            "budget" not in AISettingsResponse.model_fields
        ), "AISettingsResponse.budget field must be removed"


# ─── A7: BYOK key endpoint no longer requires byok_keys feature gate ─────────

class TestByokKeyNoFeatureGate:
    """A7: POST /settings/ai/keys no longer requires byok_keys feature gate."""

    def test_free_plan_owner_can_add_byok_key(
        self,
        client: TestClient,
        free_owner_headers: dict,
        db: Session,
        free_org: Organization,
    ):
        """A free-plan owner must be able to add a BYOK key (gate removed)."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=free_owner_headers,
                json={"provider": "openai", "api_key": "sk-free-user-key"},
            )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.json()}"
        )
        assert response.json()["provider"] == "openai"


# ─── B3: Stripe routes removed ────────────────────────────────────────────────

class TestStripeRoutesRemoved:
    """B3: Stripe-only billing routes must be gone (404)."""

    def test_checkout_route_is_gone(self, client: TestClient, auth_headers: dict):
        """POST /api/v1/billing/checkout must return 404 or 405 (route deleted)."""
        response = client.post(
            "/api/v1/billing/checkout",
            headers=auth_headers,
            json={"plan": "pro", "billing_cycle": "monthly",
                  "success_url": "http://x", "cancel_url": "http://y"},
        )
        assert response.status_code in (404, 405), (
            f"Expected 404/405 for removed checkout route, got {response.status_code}"
        )

    def test_portal_route_is_gone(self, client: TestClient, auth_headers: dict):
        """POST /api/v1/billing/portal must return 404 or 405."""
        response = client.post(
            "/api/v1/billing/portal",
            headers=auth_headers,
            json={"return_url": "http://x"},
        )
        assert response.status_code in (404, 405), (
            f"Expected 404/405 for removed portal route, got {response.status_code}"
        )

    def test_invoices_route_is_gone(self, client: TestClient, auth_headers: dict):
        """GET /api/v1/billing/invoices must return 404."""
        response = client.get("/api/v1/billing/invoices", headers=auth_headers)
        assert response.status_code in (404, 405), (
            f"Expected 404/405 for removed invoices route, got {response.status_code}"
        )

    def test_sync_subscription_route_is_gone(self, client: TestClient, auth_headers: dict):
        """POST /api/v1/billing/sync-subscription must return 404."""
        response = client.post(
            "/api/v1/billing/sync-subscription",
            headers=auth_headers,
        )
        assert response.status_code in (404, 405), (
            f"Expected 404/405 for removed sync-subscription route, got {response.status_code}"
        )

    def test_stripe_webhook_route_is_gone(self, client: TestClient):
        """POST /api/v1/billing/webhooks/stripe must return 404."""
        response = client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"type": "checkout.session.completed"},
        )
        assert response.status_code in (404, 405), (
            f"Expected 404/405 for removed stripe webhook route, got {response.status_code}"
        )

    def test_kept_billing_routes_still_work(self, client: TestClient, auth_headers: dict):
        """GET /billing/plans must still work (Stripe-free route)."""
        response = client.get("/api/v1/billing/plans", headers=auth_headers)
        assert response.status_code == 200

    def test_kept_billing_usage_still_works(self, client: TestClient, auth_headers: dict):
        """GET /billing/usage must still work."""
        response = client.get("/api/v1/billing/usage", headers=auth_headers)
        assert response.status_code == 200

    def test_billing_subscription_removed_in_b4_cleanup(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /billing/subscription was removed in B4 cleanup (exposed Stripe columns).
        It now returns 404."""
        response = client.get("/api/v1/billing/subscription", headers=auth_headers)
        assert response.status_code == 404, (
            f"Expected 404 for removed /subscription route, got {response.status_code}"
        )


class TestStripeServiceImportGuard:
    """B3: App must boot even if 'stripe' package is uninstalled."""

    def test_stripe_service_does_not_crash_without_stripe_package(self):
        """
        Importing stripe_service with stripe mocked away must not raise.
        This verifies the import guard.
        """
        # Save original
        original = sys.modules.get("stripe")
        sys.modules["stripe"] = None  # type: ignore[assignment]
        try:
            import src.services.stripe_service as ss_mod
            importlib.reload(ss_mod)
            # Must not raise; get_stripe_service() may raise but import must succeed
        except ImportError:
            pytest.fail("stripe_service module raised ImportError without stripe package")
        finally:
            if original is None:
                sys.modules.pop("stripe", None)
            else:
                sys.modules["stripe"] = original
            # Reload with real stripe back
            import src.services.stripe_service as ss_mod2
            importlib.reload(ss_mod2)


class TestAdminPromoRouteRemoved:
    """B3: admin_promo router must be removed from the app."""

    def test_admin_promo_route_is_gone(self, client: TestClient, auth_headers: dict):
        """GET /api/v1/admin/promo-codes must return 404."""
        response = client.get("/api/v1/admin/promo-codes", headers=auth_headers)
        assert response.status_code in (404, 405), (
            f"Expected 404/405 for removed admin promo route, got {response.status_code}"
        )


class TestRetentionNoStripeCall:
    """B3: PUT /notifications/retention must NOT call stripe_service."""

    def test_retention_update_does_not_call_stripe(
        self, client: TestClient, auth_headers: dict
    ):
        """Stripe manage_retention_addon must never be invoked from retention endpoint."""
        with patch(
            "src.services.stripe_service.StripeService.manage_retention_addon"
        ) as mock_stripe:
            response = client.put(
                "/api/v1/notifications/retention",
                headers=auth_headers,
                json={"retentions": [{"alert_type": "anomaly", "days": 60}]},
            )
            # Response may vary, but stripe must not be called
            assert not mock_stripe.called, (
                "stripe_service.manage_retention_addon was called from retention endpoint"
            )


# ─── No system key leakage (regression guard) ────────────────────────────────

class TestNoSystemKeyLeakage:
    """Regression: no module-level OPENAI_API_KEY read should escape to callers."""

    def test_response_generator_does_not_expose_env_key_at_module_level(self):
        """
        The module-level OPENAI_API_KEY constant in response_generator.py must be removed.
        The module should NOT cache the env key at import time.
        """
        # Set key in env before importing
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-system-leaked-key"}):
            import src.services.response_generator as rg_mod
            importlib.reload(rg_mod)
        # After reload, the module must not hold a module-level key attribute
        # that leaks the env value
        assert not hasattr(rg_mod, "OPENAI_API_KEY"), (
            "response_generator.py must not have a module-level OPENAI_API_KEY constant"
        )
