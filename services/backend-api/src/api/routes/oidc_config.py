"""
OIDC SSO configuration routes (oidc-config aspect, Task 2).

Routes:
  GET    /api/v1/settings/oidc  — read the org's config (or configured:false)
  PUT    /api/v1/settings/oidc  — upsert (encrypt client_secret in the route)
  DELETE /api/v1/settings/oidc  — delete the org's config

Mirrors zendesk_integration.py's Fernet pattern: client_secret is encrypted
here (never in the model), and is NEVER returned in any response — only
secret_hint (last chars of plaintext). A missing LLM_ENCRYPTION_KEY raises
ValueError from encrypt_api_key, which is caught and surfaced as HTTP 422,
never a 500 (R6-style safeguard).

D5 guard: at most one OidcConfig may have enabled=true across the whole
deployment. This is enforced here at the route layer (not via a DB
constraint) because a Postgres partial unique index on `enabled` is not
enforced by the SQLite test DB — see spec.md R1. A write that would enable
a second org's config while a different org's is already enabled is
rejected with 422.

allowed_email_domains is normalized (lowercased + stripped) but an empty or
absent list is stored as-is and means deny-all — this aspect must never
coerce empty -> allow-all (the login-flow aspect enforces the deny).

All verbs require admin/owner role and are scoped by organization_id from
the authenticated context (get_current_org).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, require_admin_or_owner
from src.api.routes._sso_guard import assert_no_other_provider_enabled
from src.database.session import get_db
from src.models.oidc_config import OidcConfig
from src.models.organization import Organization
from src.utils.encryption import encrypt_api_key, get_key_hint

router = APIRouter(prefix="/api/v1/settings/oidc", tags=["oidc-config"])


# ──────────────────────── Pydantic schemas ────────────────────────────────────


class OidcConfigUpdateRequest(BaseModel):
    issuer_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: Optional[str] = Field(None, min_length=1)
    enabled: bool = False
    allowed_email_domains: List[str] = Field(default_factory=list)
    button_label: Optional[str] = None


class OidcConfigResponse(BaseModel):
    configured: bool
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    secret_hint: Optional[str] = None
    enabled: bool = False
    allowed_email_domains: List[str] = Field(default_factory=list)
    button_label: Optional[str] = None
    # client_secret is intentionally NEVER included


# ──────────────────────── Internal helpers ───────────────────────────────────


def _get_org_config(db: Session, org_id: int) -> Optional[OidcConfig]:
    """Return the OidcConfig row for an org, or None."""
    return db.query(OidcConfig).filter(OidcConfig.organization_id == org_id).first()


def _build_response(row: OidcConfig) -> OidcConfigResponse:
    return OidcConfigResponse(
        configured=True,
        issuer_url=row.issuer_url,
        client_id=row.client_id,
        secret_hint=row.secret_hint,
        enabled=bool(row.enabled),
        allowed_email_domains=row.allowed_email_domains or [],
        button_label=row.button_label,
    )


def _normalize_domains(raw: List[str]) -> List[str]:
    """Lowercase/strip each domain; reject any entry that is empty, whitespace,
    or has no dot. An empty input list is valid and preserved as-is
    (deny-all) — never coerced to allow-all."""
    normalized: List[str] = []
    for entry in raw:
        value = (entry or "").strip().lower()
        if not value or "." not in value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid allowed_email_domains entry: {entry!r}. Must be a non-empty domain (e.g. 'acme.com').",
            )
        normalized.append(value)
    return normalized


def _assert_no_other_enabled(db: Session, org_id: int) -> None:
    """D5 guard: reject enabling this org's config if a DIFFERENT org's
    config is already enabled=true. At most one enabled config may exist
    across the whole deployment."""
    other = (
        db.query(OidcConfig)
        .filter(
            OidcConfig.organization_id != org_id,
            OidcConfig.enabled.is_(True),
        )
        .first()
    )
    if other is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Another OIDC config is already enabled; only one may be active per deployment.",
        )


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.get(
    "",
    response_model=OidcConfigResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def get_oidc_config(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return the org's OIDC config, or configured:false if none exists."""
    row = _get_org_config(db, current_org.id)
    if not row:
        return OidcConfigResponse(configured=False)
    return _build_response(row)


@router.put(
    "",
    response_model=OidcConfigResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def upsert_oidc_config(
    payload: OidcConfigUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Upsert the org's OIDC config.

    - client_secret is optional on update: if omitted, the existing
      encrypted secret/hint are preserved. If provided, it is Fernet-
      encrypted here (never stored plaintext) and secret_hint is
      recomputed. A missing LLM_ENCRYPTION_KEY (ValueError from
      encrypt_api_key) is surfaced as 422, never a 500.
    - allowed_email_domains is normalized; an empty list is valid (deny-all).
    - D5: enabling this config while a different org's is already enabled
      is rejected with 422.
    """
    domains = _normalize_domains(payload.allowed_email_domains)

    if payload.enabled:
        _assert_no_other_enabled(db, current_org.id)
        assert_no_other_provider_enabled(db, enabling="oidc")

    existing = _get_org_config(db, current_org.id)

    if payload.client_secret:
        try:
            encrypted_secret = encrypt_api_key(payload.client_secret)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot store OIDC client secret: LLM_ENCRYPTION_KEY is not "
                    "set. Set this environment variable and restart the service "
                    "to configure OIDC SSO."
                ),
            ) from exc
        secret_hint = get_key_hint(payload.client_secret)
    elif existing:
        encrypted_secret = existing.client_secret
        secret_hint = existing.secret_hint
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="client_secret is required when creating a new OIDC config.",
        )

    button_label = payload.button_label or (existing.button_label if existing else None) or "Sign in with SSO"

    if existing:
        existing.issuer_url = payload.issuer_url
        existing.client_id = payload.client_id
        existing.client_secret = encrypted_secret
        existing.secret_hint = secret_hint
        existing.enabled = payload.enabled
        existing.allowed_email_domains = domains
        existing.button_label = button_label
        row = existing
    else:
        row = OidcConfig(
            organization_id=current_org.id,
            issuer_url=payload.issuer_url,
            client_id=payload.client_id,
            client_secret=encrypted_secret,
            secret_hint=secret_hint,
            enabled=payload.enabled,
            allowed_email_domains=domains,
            button_label=button_label,
        )
        db.add(row)

    db.commit()
    db.refresh(row)

    return _build_response(row)


@router.delete(
    "",
    dependencies=[Depends(require_admin_or_owner)],
)
def delete_oidc_config(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete the org's OIDC config. 404 if none exists."""
    row = _get_org_config(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OIDC config found.",
        )
    db.delete(row)
    db.commit()
    return {"success": True, "message": "OIDC config deleted."}
