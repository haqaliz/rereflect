"""
Public API authentication — API-key based auth dependency.

Keys are formatted ``rrf_<urlsafe-random>`` and stored as sha256(key) in
``api_keys.key_hash``.  The full key is shown exactly once at creation; only
the hash + a short prefix are persisted.

Usage
-----
    from src.api.public.auth import verify_api_key, require_scope

    @router.get("/feedback")
    def list_feedback(auth: ApiKeyAuth = Depends(verify_api_key)):
        ...

    @router.post("/feedback", dependencies=[Depends(require_scope("ingest"))])
    def ingest_feedback(auth: ApiKeyAuth = Depends(verify_api_key)):
        ...
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.api_key import ApiKey

logger = logging.getLogger(__name__)

# Accept the key via Authorization: Bearer OR the X-API-Key header.
_bearer_scheme = HTTPBearer(auto_error=False)
_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or revoked API key",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass
class ApiKeyAuth:
    """Auth context resolved from a public-API key."""

    organization_id: int
    scopes: list[str]
    key_row: ApiKey


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _resolve_raw_key(
    bearer: Optional[HTTPAuthorizationCredentials],
    header_key: Optional[str],
) -> str:
    """Extract the raw key string from whichever auth mechanism was used."""
    if bearer is not None and bearer.credentials:
        return bearer.credentials
    if header_key:
        return header_key
    raise _401


def verify_api_key(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
    header_key: Optional[str] = Security(_header_scheme),
    db: Session = Depends(get_db),
) -> ApiKeyAuth:
    """Dependency: validate the API key and return the resolved auth context.

    Accepts either ``Authorization: Bearer rrf_...`` or ``X-API-Key: rrf_...``.
    Updates ``last_used_at`` on each successful call.
    """
    raw = _resolve_raw_key(bearer, header_key)
    key_hash = _hash_key(raw)

    row = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        .first()
    )
    if row is None:
        raise _401

    # Update last_used_at (fire-and-forget style — failure doesn't break the request)
    try:
        row.last_used_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to update last_used_at for api key id=%s", row.id)

    scopes = [s.strip() for s in row.scopes.split(",") if s.strip()]
    return ApiKeyAuth(organization_id=row.organization_id, scopes=scopes, key_row=row)


def require_scope(scope: str):
    """Dependency factory: raises 403 if the resolved key lacks the given scope.

    Usage::

        @router.post("/feedback", dependencies=[Depends(require_scope("ingest"))])
        def ingest(auth: ApiKeyAuth = Depends(verify_api_key)):
            ...

    Because the scope check itself depends on the auth context, it re-resolves
    ``verify_api_key`` via the same ``Depends`` chain.  FastAPI caches dependency
    results within a request, so this is free.
    """

    def _check(auth: ApiKeyAuth = Depends(verify_api_key)) -> ApiKeyAuth:
        if scope not in auth.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This API key lacks the '{scope}' scope",
            )
        return auth

    return _check
