"""
BYOK (Bring Your Own Key) resolution helper.

Provides a single shared helper `resolve_org_byok_key` that retrieves a
decrypted API key for a provider from the org's OrgApiKey table.

This helper has NO system-key fallback. If the org has no valid BYOK key
for the requested provider, it returns None. Callers are responsible for
gracefully disabling or skipping the AI feature when None is returned.

Design contract (PRD §A4, Decision D2):
- NEVER read OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_AI_API_KEY from env.
- NEVER return a Rereflect-operated key.
- Return None when absent → caller falls back to VADER/keyword pipeline.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_org_byok_key(
    provider: str,
    org_id: int,
    db,
) -> Optional[str]:
    """
    Return the decrypted BYOK API key for `provider` and `org_id`.

    Args:
        provider: One of "openai", "anthropic", "google".
        org_id:   The organization ID.
        db:       SQLAlchemy session.

    Returns:
        Decrypted API key string if a valid BYOK key exists, else None.
        NEVER returns a system/env key.
    """
    try:
        from src.models.org_api_key import OrgApiKey
        from src.utils.encryption import decrypt_api_key

        row = db.query(OrgApiKey).filter_by(
            organization_id=org_id,
            provider=provider,
            is_valid=True,
        ).first()

        if row is None:
            return None

        return decrypt_api_key(row.encrypted_key)

    except Exception as exc:
        logger.warning(
            "resolve_org_byok_key: could not retrieve key for provider=%s org=%s: %s",
            provider,
            org_id,
            exc,
        )
        return None
