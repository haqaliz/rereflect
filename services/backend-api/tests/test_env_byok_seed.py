"""
TDD tests for Q1 env-seed BYOK key convenience (A7 / OSS Self-Hosted Pivot).

On startup, if OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_AI_API_KEY is set in
the environment, the operator's key is seeded into the primary org's OrgApiKey
table using the existing Fernet encryption pipeline. This keeps the BYOK resolver
pure-DB — env is only a one-time populate, never a runtime fallback.

Five tests, strict TDD:
  T1 – Env key set + no existing row → encrypted OrgApiKey created, decrypts back.
  T2 – Env key set + existing row → seeding does NOT overwrite it.
  T3 – Env var unset → no OrgApiKey created.
  T4 – Idempotency → running seed twice creates exactly one row.
  T5 – Missing LLM_ENCRYPTION_KEY → no crash, skips gracefully.
"""

import os
import pytest
from unittest.mock import patch
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password

# A fresh Fernet key used only inside this test module.
TEST_ENC_KEY = Fernet.generate_key().decode()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_org(db: Session, name: str = "Primary Org") -> Organization:
    """Create and persist a bare-minimum organization."""
    org = Organization(name=name, plan="enterprise")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_owner(db: Session, org: Organization) -> User:
    """Create an owner user for the given org (mirrors what seed_admin_user does)."""
    user = User(
        email="admin@selfhost.example",
        password_hash=hash_password("changeme"),
        organization_id=org.id,
        role="owner",
        is_system_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ─── T1: creates encrypted OrgApiKey when env key present and no row exists ───

class TestEnvSeedCreatesKey:
    """T1 – env key set, no existing OrgApiKey → row is created and decrypts."""

    def test_creates_org_api_key_for_openai_env_var(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        env = {
            "LLM_ENCRYPTION_KEY": TEST_ENC_KEY,
            "OPENAI_API_KEY": "sk-operator-openai-key-123",
        }
        # Keep the patch active for both seeding AND decryption — Fernet needs
        # the same key for encrypt and decrypt.
        with patch.dict(os.environ, env, clear=False):
            from src.seed_byok import seed_byok_keys_from_env
            seed_byok_keys_from_env(db)

            from src.models.org_api_key import OrgApiKey
            from src.utils.encryption import decrypt_api_key

            row = db.query(OrgApiKey).filter_by(
                organization_id=org.id, provider="openai"
            ).first()

            assert row is not None, "OrgApiKey row must be created for openai"
            assert row.is_valid is True
            assert decrypt_api_key(row.encrypted_key) == "sk-operator-openai-key-123"

    def test_creates_org_api_key_for_anthropic_env_var(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        env = {
            "LLM_ENCRYPTION_KEY": TEST_ENC_KEY,
            "ANTHROPIC_API_KEY": "sk-ant-operator-key-456",
        }
        with patch.dict(os.environ, env, clear=False):
            from src.seed_byok import seed_byok_keys_from_env
            seed_byok_keys_from_env(db)

            from src.models.org_api_key import OrgApiKey
            from src.utils.encryption import decrypt_api_key

            row = db.query(OrgApiKey).filter_by(
                organization_id=org.id, provider="anthropic"
            ).first()
            assert row is not None, "OrgApiKey row must be created for anthropic"
            assert decrypt_api_key(row.encrypted_key) == "sk-ant-operator-key-456"

    def test_creates_org_api_key_for_google_env_var(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        env = {
            "LLM_ENCRYPTION_KEY": TEST_ENC_KEY,
            "GOOGLE_AI_API_KEY": "AIza-operator-google-key-789",
        }
        with patch.dict(os.environ, env, clear=False):
            from src.seed_byok import seed_byok_keys_from_env
            seed_byok_keys_from_env(db)

            from src.models.org_api_key import OrgApiKey
            from src.utils.encryption import decrypt_api_key

            row = db.query(OrgApiKey).filter_by(
                organization_id=org.id, provider="google"
            ).first()
            assert row is not None, "OrgApiKey row must be created for google"
            assert decrypt_api_key(row.encrypted_key) == "AIza-operator-google-key-789"


# ─── T2: does NOT overwrite an existing OrgApiKey ─────────────────────────────

class TestEnvSeedDoesNotOverwrite:
    """T2 – env key set + existing row → existing key wins (UI key is canonical)."""

    def test_does_not_overwrite_existing_org_api_key(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        # Simulate a key that was set via the UI
        from src.models.org_api_key import OrgApiKey
        from src.utils.encryption import encrypt_api_key, decrypt_api_key

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_ENC_KEY}, clear=False):
            ui_key_value = "sk-ui-set-key-must-survive"
            existing = OrgApiKey(
                organization_id=org.id,
                provider="openai",
                encrypted_key=encrypt_api_key(ui_key_value),
                key_hint="...vive",
                is_valid=True,
            )
            db.add(existing)
            db.commit()
            existing_id = existing.id

            # Now seed runs with a DIFFERENT env key
            env = {
                "LLM_ENCRYPTION_KEY": TEST_ENC_KEY,
                "OPENAI_API_KEY": "sk-env-key-must-not-overwrite",
            }
            with patch.dict(os.environ, env, clear=False):
                from src.seed_byok import seed_byok_keys_from_env
                seed_byok_keys_from_env(db)

            row = db.query(OrgApiKey).filter_by(
                organization_id=org.id, provider="openai"
            ).first()
            assert row is not None
            assert row.id == existing_id, "Row identity must not change (no overwrite)"
            assert decrypt_api_key(row.encrypted_key) == ui_key_value, (
                "Existing key must NOT be overwritten by env seed"
            )


# ─── T3: env var unset → no row created ──────────────────────────────────────

class TestEnvSeedSkipsWhenVarUnset:
    """T3 – provider env var absent → no OrgApiKey created for that provider."""

    def test_no_row_created_when_openai_env_var_absent(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        # Explicitly ensure OPENAI_API_KEY is NOT in environment
        env = {"LLM_ENCRYPTION_KEY": TEST_ENC_KEY}
        # Remove OPENAI_API_KEY if it happens to be set in the test runner
        cleaned = {k: v for k, v in os.environ.items() if k not in (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY"
        )}
        cleaned["LLM_ENCRYPTION_KEY"] = TEST_ENC_KEY

        with patch.dict(os.environ, cleaned, clear=True):
            from src.seed_byok import seed_byok_keys_from_env
            seed_byok_keys_from_env(db)

        from src.models.org_api_key import OrgApiKey
        count = db.query(OrgApiKey).filter_by(organization_id=org.id).count()
        assert count == 0, "No OrgApiKey rows should be created when env vars are unset"


# ─── T4: idempotency ──────────────────────────────────────────────────────────

class TestEnvSeedIdempotent:
    """T4 – running seed twice with the same env key creates exactly one row."""

    def test_two_seed_runs_create_exactly_one_row(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        env = {
            "LLM_ENCRYPTION_KEY": TEST_ENC_KEY,
            "OPENAI_API_KEY": "sk-idempotent-key",
        }
        with patch.dict(os.environ, env, clear=False):
            from src.seed_byok import seed_byok_keys_from_env
            seed_byok_keys_from_env(db)
            seed_byok_keys_from_env(db)  # second call must be a no-op

        from src.models.org_api_key import OrgApiKey
        count = db.query(OrgApiKey).filter_by(
            organization_id=org.id, provider="openai"
        ).count()
        assert count == 1, f"Expected exactly 1 row after two seed runs, got {count}"


# ─── T5: missing LLM_ENCRYPTION_KEY → no crash, skips gracefully ─────────────

class TestEnvSeedGracefulWithoutEncryptionKey:
    """T5 – LLM_ENCRYPTION_KEY absent → no crash, seeding is silently skipped."""

    def test_does_not_crash_when_llm_encryption_key_missing(self, db: Session):
        org = _make_org(db)
        _make_owner(db, org)

        # Remove both LLM_ENCRYPTION_KEY and set an OPENAI_API_KEY
        cleaned = {k: v for k, v in os.environ.items()
                   if k != "LLM_ENCRYPTION_KEY"}
        cleaned["OPENAI_API_KEY"] = "sk-would-fail-without-enc-key"

        with patch.dict(os.environ, cleaned, clear=True):
            from src.seed_byok import seed_byok_keys_from_env
            # Must not raise any exception
            seed_byok_keys_from_env(db)

        from src.models.org_api_key import OrgApiKey
        count = db.query(OrgApiKey).filter_by(organization_id=org.id).count()
        assert count == 0, "No row must be created when LLM_ENCRYPTION_KEY is absent"


# ─── Resolver purity guard (regression) ──────────────────────────────────────

class TestResolverRemainsDBOnly:
    """
    Regression: resolve_org_byok_key must NEVER return an env key, even after
    seed_byok_keys_from_env has been imported into the process.
    """

    def test_resolver_returns_none_not_env_key_when_no_db_row(self, db: Session):
        """
        With OPENAI_API_KEY set but no OrgApiKey row, resolver returns None.
        This proves the env-seed path is startup-only and does not pollute the
        runtime resolver.
        """
        org = _make_org(db)

        env = {
            "LLM_ENCRYPTION_KEY": TEST_ENC_KEY,
            "OPENAI_API_KEY": "sk-should-not-come-from-resolver",
        }
        with patch.dict(os.environ, env, clear=False):
            from src.utils.byok import resolve_org_byok_key
            result = resolve_org_byok_key("openai", org.id, db)

        assert result is None, (
            "resolve_org_byok_key must return None (not the env key) "
            "when no OrgApiKey row exists — env-seed only populates the DB at startup"
        )
