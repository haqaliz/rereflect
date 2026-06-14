"""
Env-seed BYOK keys for single-tenant self-hosted convenience (OSS Pivot Q1).

On application startup, for each of the three provider env vars that is present,
ensure an OrgApiKey row exists for the *primary organization* (the first org in
the database, which is the one seeded for the admin user).

Design rules (PRD §9 Q1, Workstream A7):
- Encrypts the env key with `encrypt_api_key` (same Fernet pipeline as the UI).
- Does NOT overwrite an existing OrgApiKey for that provider+org — UI/manual key
  is canonical and wins.
- If the env var is unset → no-op for that provider.
- If `LLM_ENCRYPTION_KEY` is missing → logs a warning and skips entirely; never
  raises — startup must not crash.
- Idempotent: safe to call every startup.

IMPORTANT: This function ONLY populates the OrgApiKey table at startup.
It does NOT introduce any runtime env-key fallback in the resolver.
`resolve_org_byok_key` (src/utils/byok.py) remains pure-DB at all times.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Map from provider name (as stored in OrgApiKey.provider) to env var name.
_PROVIDER_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_AI_API_KEY",
}


def seed_byok_keys_from_env(db) -> None:
    """
    Seed env-supplied operator keys into the primary org's OrgApiKey store.

    Intended to be called once during application startup (lifespan hook).
    Safe to call multiple times — idempotent.

    Args:
        db: SQLAlchemy Session bound to the application database.
    """
    # Guard: LLM_ENCRYPTION_KEY must be present to encrypt keys.
    if not os.environ.get("LLM_ENCRYPTION_KEY"):
        logger.warning(
            "seed_byok_keys_from_env: LLM_ENCRYPTION_KEY is not set — "
            "skipping env-key seeding. Set this variable to enable BYOK key "
            "encryption for self-hosted deployments."
        )
        return

    # Find the primary organization (lowest id = first created = admin org).
    try:
        from src.models.organization import Organization
        primary_org: Optional[Organization] = (
            db.query(Organization).order_by(Organization.id.asc()).first()
        )
    except Exception as exc:
        logger.warning("seed_byok_keys_from_env: could not query Organization: %s", exc)
        return

    if primary_org is None:
        logger.info(
            "seed_byok_keys_from_env: no organizations found — "
            "skipping (will seed once org is created)."
        )
        return

    from src.models.org_api_key import OrgApiKey
    from src.utils.encryption import encrypt_api_key, get_key_hint

    seeded_count = 0

    for provider, env_var in _PROVIDER_ENV.items():
        raw_key: Optional[str] = os.environ.get(env_var)

        if not raw_key:
            # Env var unset → no-op for this provider.
            continue

        # Skip if a key already exists for this provider+org (UI key wins).
        existing = db.query(OrgApiKey).filter_by(
            organization_id=primary_org.id,
            provider=provider,
        ).first()

        if existing is not None:
            logger.info(
                "seed_byok_keys_from_env: org %d already has a key for provider=%s — "
                "skipping (existing key is canonical).",
                primary_org.id,
                provider,
            )
            continue

        # Encrypt and persist.
        try:
            encrypted = encrypt_api_key(raw_key)
            hint = get_key_hint(raw_key)
            key_row = OrgApiKey(
                organization_id=primary_org.id,
                provider=provider,
                encrypted_key=encrypted,
                key_hint=hint,
                is_valid=True,
            )
            db.add(key_row)
            db.commit()
            db.refresh(key_row)
            seeded_count += 1
            logger.info(
                "seed_byok_keys_from_env: seeded %s key (hint=%s) for org %d.",
                provider,
                hint,
                primary_org.id,
            )
        except Exception as exc:
            db.rollback()
            logger.warning(
                "seed_byok_keys_from_env: failed to seed %s key for org %d: %s",
                provider,
                primary_org.id,
                exc,
            )

    if seeded_count == 0:
        logger.debug("seed_byok_keys_from_env: nothing new to seed.")
    else:
        logger.info(
            "seed_byok_keys_from_env: seeded %d provider key(s) into org %d.",
            seeded_count,
            primary_org.id,
        )
