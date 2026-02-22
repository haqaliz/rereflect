"""
Tests for M2.1 Multi-Model Support API endpoints.

Covers:
- Encryption utility (encrypt/decrypt round-trip, key hint)
- Updated GET/PATCH /api/v1/settings/ai (expanded schema)
- API Key management (GET/POST/DELETE /api/v1/settings/ai/keys)
- Key validation (POST /api/v1/settings/ai/keys/validate)
- Model testing (POST /api/v1/settings/ai/test-model)
- Available models (GET /api/v1/settings/ai/models)
- Usage endpoints (GET /api/v1/settings/ai/usage, /daily)
- Budget endpoint (GET /api/v1/settings/ai/budget)
- Admin model management (GET/PATCH /api/v1/admin/ai-models)
"""

import os
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

from src.api.auth import hash_password, create_access_token
from src.models.organization import Organization
from src.models.user import User

# ─── Set test encryption key before any imports ───────────────────────────────
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


# ─── Encryption Utility Tests ─────────────────────────────────────────────────

class TestEncryptionUtility:
    def test_encrypt_decrypt_round_trip(self):
        """Encrypt then decrypt should return original key."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            from src.utils.encryption import encrypt_api_key, decrypt_api_key
            plain = "sk-test-abc123"
            encrypted = encrypt_api_key(plain)
            assert encrypted != plain
            assert decrypt_api_key(encrypted) == plain

    def test_different_calls_produce_different_ciphertext(self):
        """Fernet uses a random IV, so each encryption is unique."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            from src.utils.encryption import encrypt_api_key
            plain = "sk-test-abc123"
            enc1 = encrypt_api_key(plain)
            enc2 = encrypt_api_key(plain)
            assert enc1 != enc2

    def test_missing_env_var_raises(self):
        """Missing LLM_ENCRYPTION_KEY should raise ValueError."""
        env = {k: v for k, v in os.environ.items() if k != "LLM_ENCRYPTION_KEY"}
        with patch.dict(os.environ, env, clear=True):
            # Re-import to bypass module-level caching
            import importlib
            import src.utils.encryption as enc_mod
            importlib.reload(enc_mod)
            with pytest.raises(ValueError, match="LLM_ENCRYPTION_KEY"):
                enc_mod.encrypt_api_key("sk-test")
        # Restore
        import importlib
        import src.utils.encryption as enc_mod
        importlib.reload(enc_mod)

    def test_get_key_hint_returns_last_4(self):
        """Key hint should be '...XXXX' with last 4 chars."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            from src.utils.encryption import get_key_hint
            assert get_key_hint("sk-abc1234abcd") == "...abcd"
            assert get_key_hint("ABCD") == "...ABCD"

    def test_get_key_hint_short_key(self):
        """Short key returns as-is."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            from src.utils.encryption import get_key_hint
            assert get_key_hint("AB") == "AB"


# ─── Fixtures for API tests ───────────────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner@test.com",
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
def admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="admin@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="admin",
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


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def system_admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sysadmin@test.com",
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
def org_ai_config(db: Session, test_organization: Organization):
    """Create an OrgAIConfig record for the test organization."""
    from src.models.org_ai_config import OrgAIConfig
    config = OrgAIConfig(
        organization_id=test_organization.id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        monthly_budget_cents=1000,
        budget_used_cents=0,
        budget_reset_at=datetime(2026, 3, 1, 0, 0, 0),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def org_api_key(db: Session, test_organization: Organization):
    """Create an encrypted OrgApiKey for openai provider."""
    from src.models.org_api_key import OrgApiKey
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
        from src.utils.encryption import encrypt_api_key, get_key_hint
        plain_key = "sk-openai-test-key"
        key = OrgApiKey(
            organization_id=test_organization.id,
            provider="openai",
            encrypted_key=encrypt_api_key(plain_key),
            key_hint=get_key_hint(plain_key),
            is_valid=True,
        )
        db.add(key)
        db.commit()
        db.refresh(key)
        return key


@pytest.fixture
def llm_model_prices(db: Session):
    """Seed some model prices for tests."""
    from src.models.llm_model_price import LLMModelPrice
    models = [
        LLMModelPrice(
            provider="openai",
            model_id="gpt-4o-mini",
            display_name="GPT-4o Mini",
            input_price_per_1m_tokens=0.15,
            output_price_per_1m_tokens=0.60,
            context_window=128000,
            max_output_tokens=16384,
            supports_json_mode=True,
            tier="cheap",
            min_plan="free",
            is_available=True,
            is_deprecated=False,
        ),
        LLMModelPrice(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            input_price_per_1m_tokens=2.50,
            output_price_per_1m_tokens=10.00,
            context_window=128000,
            max_output_tokens=4096,
            supports_json_mode=True,
            tier="mid",
            min_plan="pro",
            is_available=True,
            is_deprecated=False,
        ),
        LLMModelPrice(
            provider="anthropic",
            model_id="claude-haiku-4-5",
            display_name="Claude Haiku 4.5",
            input_price_per_1m_tokens=0.80,
            output_price_per_1m_tokens=4.00,
            context_window=200000,
            max_output_tokens=8192,
            supports_json_mode=False,
            tier="cheap",
            min_plan="free",
            is_available=True,
            is_deprecated=False,
        ),
        LLMModelPrice(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            display_name="Claude Sonnet 4.6",
            input_price_per_1m_tokens=3.00,
            output_price_per_1m_tokens=15.00,
            context_window=200000,
            max_output_tokens=8192,
            supports_json_mode=False,
            tier="mid",
            min_plan="pro",
            is_available=True,
            is_deprecated=False,
        ),
        LLMModelPrice(
            provider="openai",
            model_id="gpt-4-turbo",
            display_name="GPT-4 Turbo",
            input_price_per_1m_tokens=10.00,
            output_price_per_1m_tokens=30.00,
            context_window=128000,
            max_output_tokens=4096,
            supports_json_mode=True,
            tier="premium",
            min_plan="business",
            is_available=True,
            is_deprecated=False,
        ),
        LLMModelPrice(
            provider="openai",
            model_id="deprecated-model",
            display_name="Old Deprecated Model",
            input_price_per_1m_tokens=1.00,
            output_price_per_1m_tokens=2.00,
            context_window=8192,
            max_output_tokens=4096,
            supports_json_mode=False,
            tier="cheap",
            min_plan="free",
            is_available=False,
            is_deprecated=True,
            replacement_model_id="gpt-4o-mini",
        ),
    ]
    for m in models:
        db.add(m)
    db.commit()
    return models


@pytest.fixture
def llm_usage_logs(db: Session, test_organization: Organization):
    """Create sample usage logs for current month."""
    from src.models.llm_usage_log import LLMUsageLog
    now = datetime.utcnow()
    logs = [
        LLMUsageLog(
            organization_id=test_organization.id,
            provider="openai",
            model="gpt-4o-mini",
            task_type="categorization",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_cents=0.5,
            latency_ms=300,
            was_fallback=False,
            is_byok=False,
            created_at=now - timedelta(days=2),
        ),
        LLMUsageLog(
            organization_id=test_organization.id,
            provider="anthropic",
            model="claude-haiku-4-5",
            task_type="analysis",
            prompt_tokens=200,
            completion_tokens=80,
            total_tokens=280,
            estimated_cost_cents=1.5,
            latency_ms=450,
            was_fallback=True,
            fallback_reason="rate_limit",
            is_byok=False,
            created_at=now - timedelta(days=1),
        ),
        LLMUsageLog(
            organization_id=test_organization.id,
            provider="openai",
            model="gpt-4o-mini",
            task_type="insights",
            prompt_tokens=500,
            completion_tokens=200,
            total_tokens=700,
            estimated_cost_cents=2.0,
            latency_ms=600,
            was_fallback=False,
            is_byok=True,
            created_at=now,
        ),
    ]
    for log in logs:
        db.add(log)
    db.commit()
    return logs


# ─── GET /api/v1/settings/ai (expanded schema) ───────────────────────────────

class TestGetAISettingsExpanded:
    def test_returns_expanded_schema_without_config(
        self, client: TestClient, auth_headers: dict
    ):
        """Should return expanded schema even if no OrgAIConfig exists yet."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "ai_analysis_enabled" in data
        assert "default_provider" in data
        assert "models" in data
        assert "budget" in data

    def test_returns_defaults_when_no_config(
        self, client: TestClient, auth_headers: dict
    ):
        """Defaults: provider=openai, all models=gpt-4o-mini, no budget set."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        data = response.json()
        assert data["default_provider"] == "openai"
        assert data["models"]["categorization"] == "gpt-4o-mini"
        assert data["models"]["analysis"] == "gpt-4o-mini"
        assert data["models"]["insights"] == "gpt-4o-mini"

    def test_returns_config_when_exists(
        self,
        client: TestClient,
        auth_headers: dict,
        org_ai_config,
    ):
        """Should return org's configured values."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["default_provider"] == "openai"
        assert data["budget"]["monthly_limit_cents"] == 1000
        assert data["budget"]["used_cents"] == 0
        assert data["budget"]["is_exceeded"] is False

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai")
        assert response.status_code == 403


# ─── PATCH /api/v1/settings/ai (expanded schema) ─────────────────────────────

class TestPatchAISettingsExpanded:
    def test_admin_can_update_provider_and_models(
        self,
        client: TestClient,
        admin_headers: dict,
        org_ai_config,
        db: Session,
        test_organization: Organization,
    ):
        """Admin can change default provider and models."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers,
            json={
                "default_provider": "anthropic",
                "model_categorization": "claude-haiku-4-5",
                "model_analysis": "claude-haiku-4-5",
                "model_insights": "claude-haiku-4-5",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["default_provider"] == "anthropic"
        assert data["models"]["categorization"] == "claude-haiku-4-5"

    def test_member_cannot_update(
        self, client: TestClient, member_headers: dict
    ):
        """Members cannot update AI settings."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=member_headers,
            json={"ai_analysis_enabled": False},
        )
        assert response.status_code == 403

    def test_settings_persist(
        self,
        client: TestClient,
        owner_headers: dict,
        org_ai_config,
    ):
        """Updated settings should be returned on subsequent GET."""
        client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"ai_analysis_enabled": False},
        )
        response = client.get("/api/v1/settings/ai", headers=owner_headers)
        assert response.json()["ai_analysis_enabled"] is False

    def test_creates_config_if_missing(
        self, client: TestClient, owner_headers: dict
    ):
        """Should create OrgAIConfig if one doesn't exist yet."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"default_provider": "google"},
        )
        assert response.status_code == 200
        assert response.json()["default_provider"] == "google"


# ─── GET /api/v1/settings/ai/keys ────────────────────────────────────────────

class TestListAPIKeys:
    def test_empty_list_when_no_keys(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.get("/api/v1/settings/ai/keys", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_key_info_not_full_key(
        self,
        client: TestClient,
        auth_headers: dict,
        org_api_key,
    ):
        """Should return key_hint, not the actual key."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.get("/api/v1/settings/ai/keys", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            key_data = data[0]
            assert "provider" in key_data
            assert "key_hint" in key_data
            assert "is_valid" in key_data
            assert "created_at" in key_data
            # Full key must NOT be present
            assert "encrypted_key" not in key_data
            assert "api_key" not in key_data

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/keys")
        assert response.status_code == 403


# ─── POST /api/v1/settings/ai/keys ───────────────────────────────────────────

class TestAddAPIKey:
    def test_owner_can_add_key(
        self,
        client: TestClient,
        owner_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Owner can add a new API key."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=owner_headers,
                json={"provider": "openai", "api_key": "sk-test-1234"},
            )
            assert response.status_code == 201
            data = response.json()
            assert data["provider"] == "openai"
            assert data["key_hint"] == "...1234"
            assert data["is_valid"] is True

    def test_admin_cannot_add_key(
        self, client: TestClient, admin_headers: dict
    ):
        """Only owners can add API keys."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=admin_headers,
                json={"provider": "openai", "api_key": "sk-test-1234"},
            )
            assert response.status_code == 403

    def test_member_cannot_add_key(
        self, client: TestClient, member_headers: dict
    ):
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=member_headers,
                json={"provider": "openai", "api_key": "sk-test-1234"},
            )
            assert response.status_code == 403

    def test_key_is_stored_encrypted(
        self,
        client: TestClient,
        owner_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """The stored key must be encrypted, not plaintext."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            plain_key = "sk-my-secret-key-xyz"
            client.post(
                "/api/v1/settings/ai/keys",
                headers=owner_headers,
                json={"provider": "anthropic", "api_key": plain_key},
            )
            from src.models.org_api_key import OrgApiKey
            stored = db.query(OrgApiKey).filter_by(
                organization_id=test_organization.id,
                provider="anthropic",
            ).first()
            assert stored is not None
            assert stored.encrypted_key != plain_key
            # But we should be able to decrypt it
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(stored.encrypted_key) == plain_key

    def test_upsert_existing_provider(
        self,
        client: TestClient,
        owner_headers: dict,
        org_api_key,
    ):
        """Adding a key for existing provider should upsert (replace)."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=owner_headers,
                json={"provider": "openai", "api_key": "sk-new-key-ABCD"},
            )
            assert response.status_code == 201
            assert response.json()["key_hint"] == "...ABCD"

    def test_invalid_provider_rejected(
        self, client: TestClient, owner_headers: dict
    ):
        """Unknown providers should be rejected."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=owner_headers,
                json={"provider": "notaprovider", "api_key": "sk-test"},
            )
            assert response.status_code == 422

    def test_requires_pro_plan(
        self,
        client: TestClient,
        owner_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """BYOK keys require Pro+ plan."""
        test_organization.plan = "free"
        db.commit()
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.post(
                "/api/v1/settings/ai/keys",
                headers=owner_headers,
                json={"provider": "openai", "api_key": "sk-test"},
            )
            assert response.status_code == 403


# ─── DELETE /api/v1/settings/ai/keys/{provider} ──────────────────────────────

class TestDeleteAPIKey:
    def test_owner_can_delete_key(
        self,
        client: TestClient,
        owner_headers: dict,
        org_api_key,
    ):
        """Owner can delete a key."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            response = client.delete(
                "/api/v1/settings/ai/keys/openai",
                headers=owner_headers,
            )
            assert response.status_code == 204

    def test_admin_cannot_delete_key(
        self,
        client: TestClient,
        admin_headers: dict,
        org_api_key,
    ):
        """Admins cannot delete API keys."""
        response = client.delete(
            "/api/v1/settings/ai/keys/openai",
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_delete_nonexistent_key_returns_404(
        self, client: TestClient, owner_headers: dict
    ):
        """Deleting a non-existent key returns 404."""
        response = client.delete(
            "/api/v1/settings/ai/keys/anthropic",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_key_is_removed_from_db(
        self,
        client: TestClient,
        owner_headers: dict,
        org_api_key,
        db: Session,
        test_organization: Organization,
    ):
        """After delete, key should not exist in DB."""
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            client.delete(
                "/api/v1/settings/ai/keys/openai",
                headers=owner_headers,
            )
            from src.models.org_api_key import OrgApiKey
            key = db.query(OrgApiKey).filter_by(
                organization_id=test_organization.id,
                provider="openai",
            ).first()
            assert key is None


# ─── POST /api/v1/settings/ai/keys/validate ──────────────────────────────────

class TestValidateAPIKey:
    def test_valid_key_returns_valid_true(
        self, client: TestClient, auth_headers: dict
    ):
        """Valid provider key should return {valid: true}."""
        with patch(
            "src.api.routes.ai_settings.validate_provider_key",
            return_value=(True, None),
        ):
            response = client.post(
                "/api/v1/settings/ai/keys/validate",
                headers=auth_headers,
                json={"provider": "openai", "api_key": "sk-valid-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data.get("error_message") is None

    def test_invalid_key_returns_valid_false_with_error(
        self, client: TestClient, auth_headers: dict
    ):
        """Invalid key returns {valid: false, error_message: '...'}."""
        with patch(
            "src.api.routes.ai_settings.validate_provider_key",
            return_value=(False, "Invalid API key"),
        ):
            response = client.post(
                "/api/v1/settings/ai/keys/validate",
                headers=auth_headers,
                json={"provider": "openai", "api_key": "sk-bad-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["error_message"] == "Invalid API key"

    def test_invalid_provider_rejected(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/settings/ai/keys/validate",
            headers=auth_headers,
            json={"provider": "unknown", "api_key": "sk-test"},
        )
        assert response.status_code == 422

    def test_requires_auth(self, client: TestClient):
        response = client.post(
            "/api/v1/settings/ai/keys/validate",
            json={"provider": "openai", "api_key": "sk-test"},
        )
        assert response.status_code == 403


# ─── POST /api/v1/settings/ai/test-model ─────────────────────────────────────

class TestModelTesting:
    def test_runs_sample_and_returns_result(
        self, client: TestClient, auth_headers: dict, llm_model_prices
    ):
        """Should run sample feedback and return analysis result."""
        mock_result = {
            "sentiment": "negative",
            "pain_points": ["payment system crashing"],
            "is_urgent": True,
        }
        with patch(
            "src.api.routes.ai_settings.run_model_test",
            return_value={
                "result": mock_result,
                "tokens": 150,
                "cost_cents": 0.5,
                "latency_ms": 320,
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        ), patch(
            "src.api.routes.ai_settings._get_api_key_for_provider",
            return_value="sk-system-key",
        ):
            response = client.post(
                "/api/v1/settings/ai/test-model",
                headers=auth_headers,
                json={"provider": "openai", "model": "gpt-4o-mini"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "result" in data
            assert "tokens" in data
            assert "cost_cents" in data
            assert "latency_ms" in data

    def test_invalid_provider_rejected(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/settings/ai/test-model",
            headers=auth_headers,
            json={"provider": "badprovider", "model": "gpt-4o-mini"},
        )
        assert response.status_code == 422

    def test_requires_auth(self, client: TestClient):
        response = client.post(
            "/api/v1/settings/ai/test-model",
            json={"provider": "openai", "model": "gpt-4o-mini"},
        )
        assert response.status_code == 403

    def test_free_plan_cannot_test_premium_model(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        llm_model_prices,
    ):
        """Free plan cannot test premium (business-tier) models."""
        test_organization.plan = "free"
        db.commit()
        response = client.post(
            "/api/v1/settings/ai/test-model",
            headers=auth_headers,
            json={"provider": "openai", "model": "gpt-4-turbo"},
        )
        assert response.status_code == 403

    def test_free_plan_can_test_cheap_model(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        llm_model_prices,
    ):
        """Free plan can test cheap-tier models."""
        test_organization.plan = "free"
        db.commit()
        mock_result = {"sentiment": "negative"}
        with patch(
            "src.api.routes.ai_settings.run_model_test",
            return_value={
                "result": mock_result,
                "tokens": 100,
                "cost_cents": 0.1,
                "latency_ms": 200,
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        ), patch(
            "src.api.routes.ai_settings._get_api_key_for_provider",
            return_value="sk-system-key",
        ):
            response = client.post(
                "/api/v1/settings/ai/test-model",
                headers=auth_headers,
                json={"provider": "openai", "model": "gpt-4o-mini"},
            )
            assert response.status_code == 200


# ─── GET /api/v1/settings/ai/models ──────────────────────────────────────────

class TestAvailableModels:
    def test_returns_models_for_plan(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_model_prices,
        db: Session,
        test_organization: Organization,
    ):
        """Should return models available for the org's plan."""
        test_organization.plan = "pro"
        db.commit()
        response = client.get("/api/v1/settings/ai/models", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should include cheap and mid tier (pro plan)
        model_ids = [m["model_id"] for m in data]
        assert "gpt-4o-mini" in model_ids
        assert "gpt-4o" in model_ids
        # Should not include premium (business only)
        assert "gpt-4-turbo" not in model_ids

    def test_free_plan_gets_only_cheap_models(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_model_prices,
        db: Session,
        test_organization: Organization,
    ):
        """Free plan should only see cheap-tier models."""
        test_organization.plan = "free"
        db.commit()
        response = client.get("/api/v1/settings/ai/models", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        model_ids = [m["model_id"] for m in data]
        assert "gpt-4o-mini" in model_ids
        assert "gpt-4o" not in model_ids  # mid tier, pro required
        assert "gpt-4-turbo" not in model_ids  # premium, business required

    def test_business_plan_gets_all_tiers(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_model_prices,
        db: Session,
        test_organization: Organization,
    ):
        """Business plan gets all tiers."""
        test_organization.plan = "business"
        db.commit()
        response = client.get("/api/v1/settings/ai/models", headers=auth_headers)
        data = response.json()
        model_ids = [m["model_id"] for m in data]
        assert "gpt-4o-mini" in model_ids
        assert "gpt-4o" in model_ids
        assert "gpt-4-turbo" in model_ids

    def test_deprecated_models_excluded(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_model_prices,
    ):
        """Deprecated / unavailable models should not appear."""
        response = client.get("/api/v1/settings/ai/models", headers=auth_headers)
        data = response.json()
        model_ids = [m["model_id"] for m in data]
        assert "deprecated-model" not in model_ids

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/models")
        assert response.status_code == 403


# ─── GET /api/v1/settings/ai/usage ───────────────────────────────────────────

class TestUsageSummary:
    def test_returns_monthly_summary(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_usage_logs,
    ):
        """Should return current month's usage summary."""
        response = client.get("/api/v1/settings/ai/usage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "month" in data
        assert "total_tokens" in data
        assert "total_requests" in data
        assert "estimated_cost_cents" in data
        assert "by_provider" in data
        assert "fallback_count" in data

    def test_aggregates_tokens_correctly(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_usage_logs,
    ):
        """Total tokens should be sum of all log entries."""
        response = client.get("/api/v1/settings/ai/usage", headers=auth_headers)
        data = response.json()
        # Fixtures: 150 + 280 + 700 = 1130 tokens
        assert data["total_tokens"] == 1130
        assert data["total_requests"] == 3

    def test_counts_fallbacks(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_usage_logs,
    ):
        """Fallback count should match was_fallback=True entries."""
        response = client.get("/api/v1/settings/ai/usage", headers=auth_headers)
        data = response.json()
        assert data["fallback_count"] == 1

    def test_by_provider_breakdown(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_usage_logs,
    ):
        """Should break down by provider."""
        response = client.get("/api/v1/settings/ai/usage", headers=auth_headers)
        data = response.json()
        providers = {p["provider"]: p for p in data["by_provider"]}
        assert "openai" in providers
        assert "anthropic" in providers
        assert providers["openai"]["requests"] == 2
        assert providers["anthropic"]["requests"] == 1

    def test_requires_pro_plan(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Usage dashboard requires Pro+ plan."""
        test_organization.plan = "free"
        db.commit()
        response = client.get("/api/v1/settings/ai/usage", headers=auth_headers)
        assert response.status_code == 403

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/usage")
        assert response.status_code == 403


# ─── GET /api/v1/settings/ai/usage/daily ─────────────────────────────────────

class TestUsageDaily:
    def test_returns_daily_breakdown(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_usage_logs,
    ):
        """Should return per-day breakdown."""
        response = client.get("/api/v1/settings/ai/usage/daily", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert isinstance(data["days"], list)

    def test_day_has_required_fields(
        self,
        client: TestClient,
        auth_headers: dict,
        llm_usage_logs,
    ):
        """Each day entry should have date, tokens, requests, cost_cents."""
        response = client.get("/api/v1/settings/ai/usage/daily", headers=auth_headers)
        data = response.json()
        if data["days"]:
            day = data["days"][0]
            assert "date" in day
            assert "tokens" in day
            assert "requests" in day
            assert "cost_cents" in day

    def test_requires_pro_plan(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        test_organization.plan = "free"
        db.commit()
        response = client.get("/api/v1/settings/ai/usage/daily", headers=auth_headers)
        assert response.status_code == 403

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/usage/daily")
        assert response.status_code == 403


# ─── GET /api/v1/settings/ai/budget ──────────────────────────────────────────

class TestBudgetEndpoint:
    def test_returns_budget_status(
        self,
        client: TestClient,
        auth_headers: dict,
        org_ai_config,
    ):
        """Should return budget status."""
        response = client.get("/api/v1/settings/ai/budget", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "monthly_limit_cents" in data
        assert "used_cents" in data
        assert "is_exceeded" in data
        assert "resets_at" in data

    def test_is_exceeded_false_when_under_budget(
        self,
        client: TestClient,
        auth_headers: dict,
        org_ai_config,
    ):
        response = client.get("/api/v1/settings/ai/budget", headers=auth_headers)
        data = response.json()
        assert data["is_exceeded"] is False

    def test_is_exceeded_true_when_over_budget(
        self,
        client: TestClient,
        auth_headers: dict,
        org_ai_config,
        db: Session,
    ):
        """Should flag is_exceeded when budget_used >= monthly_budget."""
        org_ai_config.budget_used_cents = 1000  # equals the limit
        db.commit()
        response = client.get("/api/v1/settings/ai/budget", headers=auth_headers)
        data = response.json()
        assert data["is_exceeded"] is True

    def test_no_budget_configured(
        self, client: TestClient, auth_headers: dict
    ):
        """When no config exists, returns nulls and is_exceeded=False."""
        response = client.get("/api/v1/settings/ai/budget", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["is_exceeded"] is False

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/budget")
        assert response.status_code == 403


# ─── Admin: GET /api/v1/admin/ai-models ──────────────────────────────────────

class TestAdminAIModels:
    def test_system_admin_can_list_all_models(
        self,
        client: TestClient,
        system_admin_headers: dict,
        llm_model_prices,
    ):
        """System admin should see all models including deprecated."""
        response = client.get(
            "/api/v1/admin/ai-models", headers=system_admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should include deprecated model
        model_ids = [m["model_id"] for m in data]
        assert "deprecated-model" in model_ids

    def test_non_system_admin_gets_403(
        self, client: TestClient, owner_headers: dict, llm_model_prices
    ):
        """Non-system-admin users get 403."""
        response = client.get("/api/v1/admin/ai-models", headers=owner_headers)
        assert response.status_code == 403

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/admin/ai-models")
        assert response.status_code == 403

    def test_response_includes_price_info(
        self,
        client: TestClient,
        system_admin_headers: dict,
        llm_model_prices,
    ):
        response = client.get("/api/v1/admin/ai-models", headers=system_admin_headers)
        data = response.json()
        model = next(m for m in data if m["model_id"] == "gpt-4o-mini")
        assert "input_price_per_1m_tokens" in model
        assert "output_price_per_1m_tokens" in model
        assert "tier" in model
        assert "min_plan" in model
        assert "is_available" in model
        assert "is_deprecated" in model


# ─── Admin: PATCH /api/v1/admin/ai-models/{id} ───────────────────────────────

class TestAdminUpdateAIModel:
    def test_system_admin_can_update_price(
        self,
        client: TestClient,
        system_admin_headers: dict,
        llm_model_prices,
        db: Session,
    ):
        """System admin can update model price."""
        from src.models.llm_model_price import LLMModelPrice
        model = db.query(LLMModelPrice).filter_by(model_id="gpt-4o-mini").first()
        response = client.patch(
            f"/api/v1/admin/ai-models/{model.id}",
            headers=system_admin_headers,
            json={"input_price_per_1m_tokens": 0.20},
        )
        assert response.status_code == 200
        assert response.json()["input_price_per_1m_tokens"] == 0.20

    def test_system_admin_can_toggle_availability(
        self,
        client: TestClient,
        system_admin_headers: dict,
        llm_model_prices,
        db: Session,
    ):
        from src.models.llm_model_price import LLMModelPrice
        model = db.query(LLMModelPrice).filter_by(model_id="gpt-4o-mini").first()
        response = client.patch(
            f"/api/v1/admin/ai-models/{model.id}",
            headers=system_admin_headers,
            json={"is_available": False},
        )
        assert response.status_code == 200
        assert response.json()["is_available"] is False

    def test_non_system_admin_gets_403(
        self,
        client: TestClient,
        owner_headers: dict,
        llm_model_prices,
        db: Session,
    ):
        from src.models.llm_model_price import LLMModelPrice
        model = db.query(LLMModelPrice).filter_by(model_id="gpt-4o-mini").first()
        response = client.patch(
            f"/api/v1/admin/ai-models/{model.id}",
            headers=owner_headers,
            json={"input_price_per_1m_tokens": 0.99},
        )
        assert response.status_code == 403

    def test_nonexistent_model_returns_404(
        self,
        client: TestClient,
        system_admin_headers: dict,
    ):
        response = client.patch(
            "/api/v1/admin/ai-models/99999",
            headers=system_admin_headers,
            json={"is_available": False},
        )
        assert response.status_code == 404


# ─── Admin: POST /api/v1/admin/ai-models/sync-prices ─────────────────────────

class TestAdminSyncPrices:
    def test_system_admin_can_trigger_sync(
        self,
        client: TestClient,
        system_admin_headers: dict,
    ):
        """System admin can trigger price sync (mocked)."""
        with patch(
            "src.api.routes.admin_ai_models.fetch_provider_prices",
            return_value={"synced": 5, "errors": []},
        ):
            response = client.post(
                "/api/v1/admin/ai-models/sync-prices",
                headers=system_admin_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert "synced" in data

    def test_non_system_admin_gets_403(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.post(
            "/api/v1/admin/ai-models/sync-prices",
            headers=owner_headers,
        )
        assert response.status_code == 403


# ─── Plan Gating ─────────────────────────────────────────────────────────────

class TestPlanGating:
    def test_multi_model_support_available_on_pro(self):
        """multi_model_support feature should be in Pro plan."""
        from src.config.plans import has_feature
        assert has_feature("pro", "multi_model_support") is True

    def test_multi_model_support_not_on_free(self):
        from src.config.plans import has_feature
        assert has_feature("free", "multi_model_support") is False

    def test_byok_keys_available_on_pro(self):
        from src.config.plans import has_feature
        assert has_feature("pro", "byok_keys") is True

    def test_byok_keys_not_on_free(self):
        from src.config.plans import has_feature
        assert has_feature("free", "byok_keys") is False

    def test_ai_usage_dashboard_available_on_pro(self):
        from src.config.plans import has_feature
        assert has_feature("pro", "ai_usage_dashboard") is True

    def test_ai_usage_dashboard_not_on_free(self):
        from src.config.plans import has_feature
        assert has_feature("free", "ai_usage_dashboard") is False

    def test_all_features_available_on_business(self):
        from src.config.plans import has_feature
        for feature in ["multi_model_support", "byok_keys", "ai_usage_dashboard"]:
            assert has_feature("business", feature) is True

    def test_all_features_available_on_enterprise(self):
        from src.config.plans import has_feature
        for feature in ["multi_model_support", "byok_keys", "ai_usage_dashboard"]:
            assert has_feature("enterprise", feature) is True
