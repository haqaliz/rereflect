"""
Public-API key management (JWT-authenticated, admin/owner only).

Endpoints
---------
  POST   /api/v1/api-keys           Create a new key (returns full key ONCE)
  GET    /api/v1/api-keys           List org keys (prefix/scopes/last_used only)
  POST   /api/v1/api-keys/{id}/revoke   Soft-revoke a key (sets revoked_at)
  DELETE /api/v1/api-keys/{id}      Alias for revoke (convenience)
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_admin_or_owner
from src.database.session import get_db
from src.models.api_key import ApiKey
from src.models.organization import Organization
from src.models.user import User

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])

_VALID_SCOPES = frozenset({"read", "ingest", "write"})


# ─── Schemas ──────────────────────────────────────────────────────────────────


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: List[str] = Field(default=["read"])

    def validated_scopes_str(self) -> str:
        bad = [s for s in self.scopes if s not in _VALID_SCOPES]
        if bad:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown scopes: {bad}. Valid values: {sorted(_VALID_SCOPES)}",
            )
        if not self.scopes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one scope is required",
            )
        return ",".join(sorted(set(self.scopes)))


class ApiKeyCreateResponse(BaseModel):
    """Returned exactly once on key creation — includes the raw key."""

    id: int
    name: str
    key: str  # full key — shown ONCE, never stored
    key_prefix: str
    scopes: str
    organization_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyListItem(BaseModel):
    """Safe list view — never exposes the raw key or its hash."""

    id: int
    name: str
    key_prefix: str
    scopes: str
    organization_id: int
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RevokeResponse(BaseModel):
    id: int
    revoked_at: datetime


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _generate_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, sha256_hash)."""
    token = secrets.token_urlsafe(32)
    full_key = f"rrf_{token}"
    prefix = full_key[:10]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_owner)],
    summary="Create a public API key",
    description=(
        "Generates a new API key for the caller's organization. "
        "The full key (``rrf_...``) is returned **once** — store it securely. "
        "Only the hash and a short prefix are persisted."
    ),
)
def create_api_key(
    data: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ApiKeyCreateResponse:
    scopes_str = data.validated_scopes_str()
    full_key, prefix, key_hash = _generate_key()

    row = ApiKey(
        organization_id=current_org.id,
        name=data.name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes_str,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return ApiKeyCreateResponse(
        id=row.id,
        name=row.name,
        key=full_key,
        key_prefix=row.key_prefix,
        scopes=row.scopes,
        organization_id=row.organization_id,
        created_at=row.created_at,
    )


@router.get(
    "",
    response_model=List[ApiKeyListItem],
    summary="List API keys for the current organization",
    description="Returns all (non-deleted) API keys for the org. Never exposes the raw key or hash.",
)
def list_api_keys(
    current_org: Organization = Depends(get_current_org),
    _: bool = Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
) -> List[ApiKeyListItem]:
    rows = (
        db.query(ApiKey)
        .filter(ApiKey.organization_id == current_org.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [ApiKeyListItem.model_validate(r) for r in rows]


@router.post(
    "/{key_id}/revoke",
    response_model=RevokeResponse,
    dependencies=[Depends(require_admin_or_owner)],
    summary="Revoke an API key",
    description="Soft-revokes the key by setting ``revoked_at``. The key will immediately stop working.",
)
def revoke_api_key(
    key_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> RevokeResponse:
    row = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.organization_id == current_org.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    now = datetime.utcnow()
    row.revoked_at = now
    db.commit()
    return RevokeResponse(id=row.id, revoked_at=now)


@router.delete(
    "/{key_id}",
    response_model=RevokeResponse,
    dependencies=[Depends(require_admin_or_owner)],
    summary="Revoke an API key (DELETE alias)",
)
def delete_api_key(
    key_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> RevokeResponse:
    """Alias for POST /{id}/revoke — soft-deletes by setting revoked_at."""
    return revoke_api_key(key_id, current_org, db)
