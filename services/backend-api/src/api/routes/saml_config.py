"""
SAML SSO configuration routes (saml-sso: config-model-and-crud aspect).

Routes:
  GET    /api/v1/settings/saml  — read the org's config (or configured:false)
  PUT    /api/v1/settings/saml  — upsert (PEM-validate cert, SSRF-validate URL)
  DELETE /api/v1/settings/saml  — delete the org's config

Unlike oidc_config.py, idp_x509_cert is a PUBLIC signing certificate — it is
stored plaintext (never Fernet-encrypted) and there is no LLM_ENCRYPTION_KEY
dependency anywhere in this file. It IS validated as a parseable PEM X.509
certificate on save (422 on garbage), and the response returns a SHA-256
fingerprint rather than the raw PEM — tidier for an admin to cross-check
against their IdP console, and keeps the response small/stable.

idp_sso_url must be https and SSRF-gated on save (mirrors the OIDC
login-flow discipline, applied here at save time; the later login aspect
re-validates at use time).

D5 guard: at most one SamlConfig may have enabled=true across the whole
deployment (same-provider, same pattern as OIDC's _assert_no_other_enabled).
Additionally, this route calls the shared cross-provider guard
(_sso_guard.assert_no_other_provider_enabled) so enabling SAML fails if any
OIDC config is enabled — see src/api/routes/_sso_guard.py.

allowed_email_domains is normalized (lowercased + stripped) but an empty or
absent list is stored as-is and means deny-all — this aspect must never
coerce empty -> allow-all (the login-flow aspect enforces the deny).

All verbs require admin/owner role and are scoped by organization_id from
the authenticated context (get_current_org).
"""
from typing import List, Optional
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, require_admin_or_owner
from src.api.routes._sso_guard import assert_no_other_provider_enabled
from src.database.session import get_db
from src.models.organization import Organization
from src.models.saml_config import SamlConfig
from src.utils.ssrf import SsrfError, assert_host_not_ssrf

router = APIRouter(prefix="/api/v1/settings/saml", tags=["saml-config"])


# ──────────────────────── Pydantic schemas ────────────────────────────────────


class SamlConfigUpdateRequest(BaseModel):
    idp_entity_id: str = Field(..., min_length=1)
    idp_sso_url: str = Field(..., min_length=1)
    idp_x509_cert: Optional[str] = Field(None, min_length=1)
    email_attribute: Optional[str] = None
    enabled: bool = False
    allowed_email_domains: List[str] = Field(default_factory=list)
    button_label: Optional[str] = None


class SamlConfigResponse(BaseModel):
    configured: bool
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    cert_fingerprint: Optional[str] = None
    email_attribute: Optional[str] = None
    enabled: bool = False
    allowed_email_domains: List[str] = Field(default_factory=list)
    button_label: Optional[str] = None
    # idp_x509_cert is intentionally NEVER included — see module docstring


# ──────────────────────── Internal helpers ───────────────────────────────────


def _get_org_config(db: Session, org_id: int) -> Optional[SamlConfig]:
    """Return the SamlConfig row for an org, or None."""
    return db.query(SamlConfig).filter(SamlConfig.organization_id == org_id).first()


def _validate_pem_cert(pem: str) -> str:
    """Parse `pem` as an X.509 certificate; raise 422 on any failure.
    Returns the PEM unchanged (stored as-is, plaintext)."""
    try:
        x509.load_pem_x509_certificate(pem.encode())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="idp_x509_cert is not a valid PEM X.509 certificate.",
        ) from exc
    return pem


def _cert_fingerprint(pem: str) -> str:
    """SHA-256 fingerprint of the cert, uppercase colon-hex (e.g. AB:CD:...)."""
    cert = x509.load_pem_x509_certificate(pem.encode())
    digest = cert.fingerprint(hashes.SHA256())
    return ":".join(f"{b:02X}" for b in digest)


def _validate_idp_sso_url(url: str) -> None:
    """https-only + SSRF host gate. Raises 422 on failure."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="idp_sso_url must use https.",
        )
    try:
        assert_host_not_ssrf(parsed.hostname)
    except SsrfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"idp_sso_url is not allowed: {exc}",
        ) from exc


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
    """D5 guard (same-provider): reject enabling this org's config if a
    DIFFERENT org's SAML config is already enabled=true. At most one
    enabled SAML config may exist across the whole deployment."""
    other = (
        db.query(SamlConfig)
        .filter(
            SamlConfig.organization_id != org_id,
            SamlConfig.enabled.is_(True),
        )
        .first()
    )
    if other is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Another SAML config is already enabled; only one may be active per deployment.",
        )


def _build_response(row: SamlConfig) -> SamlConfigResponse:
    return SamlConfigResponse(
        configured=True,
        idp_entity_id=row.idp_entity_id,
        idp_sso_url=row.idp_sso_url,
        cert_fingerprint=_cert_fingerprint(row.idp_x509_cert),
        email_attribute=row.email_attribute,
        enabled=bool(row.enabled),
        allowed_email_domains=row.allowed_email_domains or [],
        button_label=row.button_label,
    )


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.get(
    "",
    response_model=SamlConfigResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def get_saml_config(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return the org's SAML config, or configured:false if none exists."""
    row = _get_org_config(db, current_org.id)
    if not row:
        return SamlConfigResponse(configured=False)
    return _build_response(row)


@router.put(
    "",
    response_model=SamlConfigResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def upsert_saml_config(
    payload: SamlConfigUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Upsert the org's SAML config.

    - idp_x509_cert is optional on update: if omitted, the existing PEM is
      preserved. If provided, it is PEM-validated here (422 on garbage).
    - idp_sso_url must be https and SSRF-gated (422 on failure) — validated
      even when enabled=false.
    - allowed_email_domains is normalized; an empty list is valid (deny-all).
    - D5 (same-provider): enabling this config while a different org's SAML
      config is already enabled is rejected with 422.
    - Cross-provider: enabling this config while any OIDC config is enabled
      is rejected with 422 (assert_no_other_provider_enabled).
    """
    domains = _normalize_domains(payload.allowed_email_domains)

    _validate_idp_sso_url(payload.idp_sso_url)

    if payload.enabled:
        _assert_no_other_enabled(db, current_org.id)
        assert_no_other_provider_enabled(db, enabling="saml")

    existing = _get_org_config(db, current_org.id)

    if payload.idp_x509_cert:
        cert_pem = _validate_pem_cert(payload.idp_x509_cert)
    elif existing:
        cert_pem = existing.idp_x509_cert
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="idp_x509_cert is required when creating a new SAML config.",
        )

    button_label = payload.button_label or (existing.button_label if existing else None) or "Sign in with SSO"

    if existing:
        existing.idp_entity_id = payload.idp_entity_id
        existing.idp_sso_url = payload.idp_sso_url
        existing.idp_x509_cert = cert_pem
        existing.email_attribute = payload.email_attribute
        existing.enabled = payload.enabled
        existing.allowed_email_domains = domains
        existing.button_label = button_label
        row = existing
    else:
        row = SamlConfig(
            organization_id=current_org.id,
            idp_entity_id=payload.idp_entity_id,
            idp_sso_url=payload.idp_sso_url,
            idp_x509_cert=cert_pem,
            email_attribute=payload.email_attribute,
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
def delete_saml_config(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete the org's SAML config. 404 if none exists."""
    row = _get_org_config(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SAML config found.",
        )
    db.delete(row)
    db.commit()
    return {"success": True, "message": "SAML config deleted."}
