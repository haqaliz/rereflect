"""
Zendesk integration routes (backend-connection aspect, Phase 3).

Routes:
  POST   /api/v1/integrations/zendesk/connect     — validate + encrypt + store
  GET    /api/v1/integrations/zendesk/status      — connection status (no secrets)
  DELETE /api/v1/integrations/zendesk/disconnect  — deactivate (soft; does not
                                                      touch the auto-provisioned
                                                      FeedbackSource)
  POST   /api/v1/integrations/zendesk/test        — re-validate stored token

All endpoints require admin/owner role. Zendesk is NOT a CRM — disconnect
does NOT call crm_integration_common.another_crm_active / purge_crm_enrichment.

The api_token is Fernet-encrypted via encrypt_api_key and is NEVER returned
in any response body. The webhook_secret is likewise Fernet-encrypted at
rest, but — unlike api_token — its plaintext IS returned once, on a
successful POST /connect (initial connect or reconnect), so the operator can
paste it into a Zendesk trigger/webhook. It is never included in GET
/status. On reconnect, the existing webhook_secret is preserved (not
rotated) — only api_token/token_hint/account identity rotate.

R6 safeguard: POST /connect catches ValueError from encrypt_api_key (raised
when LLM_ENCRYPTION_KEY is unset) and returns HTTP 422 — never a 500. This
covers BOTH encrypt_api_key calls this route makes (api_token and, when a
new webhook_secret must be generated, webhook_secret).

SSRF gate: after normalizing subdomain, the host `{subdomain}.zendesk.com`
is resolved via socket.getaddrinfo and rejected if any resolved address is
loopback, RFC1918-private, or link-local. This is the primary SSRF gate on
untrusted operator input; ZendeskClient re-asserts the bare-subdomain
invariant as defense in depth (see
src/services/zendesk_client.py::_assert_safe_subdomain).

Source auto-provision: on a successful connect, if the org has no existing
`zendesk` FeedbackSource, one is auto-created (matched by subdomain) so
ingestion can flow without a separate wizard step (PRD 9a, option a).
GET /status exposes `has_feedback_source` via a read-only query so status
never has side effects.
"""
import ipaddress
import logging
import secrets
import socket
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_admin_or_owner
from src.database.session import get_db
from src.models.feedback_source import FeedbackSource
from src.models.organization import Organization
from src.models.user import User
from src.models.zendesk_integration import ZendeskIntegration
from src.services.zendesk_client import (
    ZendeskAuthError,
    ZendeskClient,
    ZendeskTransientError,
)
from src.utils.encryption import decrypt_api_key, encrypt_api_key, get_key_hint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/zendesk", tags=["zendesk"])


# ──────────────────────── Pydantic schemas ────────────────────────────────────


class ZendeskConnectRequest(BaseModel):
    subdomain: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    api_token: str = Field(..., min_length=1)


class ZendeskConnectResponse(BaseModel):
    connected: bool
    subdomain: Optional[str] = None
    email: Optional[str] = None
    token_hint: Optional[str] = None
    account_user_id: Optional[str] = None
    display_name: Optional[str] = None
    webhook_secret: Optional[str] = None
    has_feedback_source: Optional[bool] = None
    # api_token is intentionally NEVER included


class ZendeskStatusResponse(BaseModel):
    connected: bool
    subdomain: Optional[str] = None
    email: Optional[str] = None
    token_hint: Optional[str] = None
    account_user_id: Optional[str] = None
    display_name: Optional[str] = None
    is_active: Optional[bool] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    connected_at: Optional[datetime] = None
    has_feedback_source: Optional[bool] = None
    # api_token / webhook_secret are intentionally NEVER included


class ZendeskDisconnectResponse(BaseModel):
    success: bool
    message: str


class ZendeskTestResponse(BaseModel):
    success: bool
    message: Optional[str] = None


# ──────────────────────── Internal helpers ───────────────────────────────────


def _normalize_subdomain(raw: str) -> str:
    """
    Normalize a user-supplied Zendesk subdomain/host to the bare subdomain
    label (e.g. "acme", NOT a URL — contrast with Jira's `_normalize_site_url`,
    which returns a full https:// URL; the DB column here is `subdomain`).

    Accepts: `acme`, `acme.zendesk.com`, `https://acme.zendesk.com`,
    `https://acme.zendesk.com/` (trailing slash). Rejects any host that
    doesn't resolve to a `*.zendesk.com` host, and rejects suffix-trick
    hosts like `acme.zendesk.com.evil.com` (a leftover `.` after stripping
    exactly one trailing `.zendesk.com` label means reject).
    """
    value = (raw or "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="subdomain is required.",
        )

    if "://" in value:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
    else:
        host = value.rstrip("/").lower()

    if host.endswith(".zendesk.com"):
        # Strip exactly one trailing ".zendesk.com" label.
        subdomain = host[: -len(".zendesk.com")]
    elif "." not in host:
        # Bare subdomain, e.g. "acme".
        subdomain = host
    else:
        subdomain = ""

    if not subdomain or "." in subdomain:
        # Empty after stripping, or a leftover dot (suffix-trick host, e.g.
        # "acme.zendesk.com.evil.com" -> "acme.zendesk.com.evil" after a
        # naive single-suffix strip attempt would still contain a dot).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="subdomain must be a bare Zendesk subdomain or a *.zendesk.com host.",
        )

    return subdomain


def _assert_host_not_ssrf(host: str) -> None:
    """
    Resolve `host` and reject it if any resolved address is loopback,
    RFC1918-private, or link-local (SSRF gate).

    This is the primary gate: it runs on untrusted operator input (a
    `*.zendesk.com` host whose DNS could be pointed at
    169.254.169.254 / internal ranges).
    """
    try:
        infos = socket.getaddrinfo(host, 443)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not resolve subdomain host: {exc}",
        ) from exc

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_private or addr.is_link_local:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="subdomain resolves to a disallowed address.",
            )


def _get_active_integration(db: Session, org_id: int) -> Optional[ZendeskIntegration]:
    """Return the active Zendesk integration for an org, or None."""
    return (
        db.query(ZendeskIntegration)
        .filter(
            ZendeskIntegration.organization_id == org_id,
            ZendeskIntegration.is_active.is_(True),
        )
        .first()
    )


def _get_org_integration(db: Session, org_id: int) -> Optional[ZendeskIntegration]:
    """Return the Zendesk integration row for an org regardless of is_active (for upsert/disconnect)."""
    return db.query(ZendeskIntegration).filter(ZendeskIntegration.organization_id == org_id).first()


def get_decrypted_token(integration: ZendeskIntegration) -> str:
    """
    Decrypt and return the plaintext Zendesk API token stored in integration.

    Raises cryptography.fernet.InvalidToken on corruption — callers should
    handle this and treat it as a failed validation (never a 500).
    """
    return decrypt_api_key(integration.api_token)


def _close_client(zendesk_client: ZendeskClient) -> None:
    """Best-effort close — never let a close failure mask the real error."""
    try:
        zendesk_client.close()
    except Exception:  # noqa: BLE001 — best-effort cleanup only
        pass


def _generate_webhook_secret() -> str:
    """Generate a new webhook HMAC secret (display-once, on connect)."""
    return secrets.token_urlsafe(32)


def _has_zendesk_source(db: Session, org_id: int) -> bool:
    """Read-only check: does a `zendesk` FeedbackSource already exist for this org?

    Shared by `_ensure_default_feedback_source` (which calls this first, then
    creates if False) and `zendesk_status` (which only ever calls this
    read-only helper) — this split avoids a GET route ever having side
    effects, by construction.
    """
    return (
        db.query(FeedbackSource)
        .filter(
            FeedbackSource.organization_id == org_id,
            FeedbackSource.source_type == "zendesk",
        )
        .first()
        is not None
    )


def _ensure_default_feedback_source(db: Session, org_id: int, subdomain: str) -> bool:
    """
    Auto-provision a default `zendesk` FeedbackSource for this org if none
    exists yet (PRD 9a, option a). Idempotent — never creates a second row,
    and never overwrites an operator-customized existing one (only its
    existence is checked).

    Does NOT commit — caller commits once, alongside the integration upsert,
    so a mid-request failure can't persist one without the other.

    Returns True if a source now exists (found-or-created).
    """
    if _has_zendesk_source(db, org_id):
        return True

    source = FeedbackSource(
        organization_id=org_id,
        integration_id=None,  # zendesk is own-auth, like jira/linear
        source_type="zendesk",
        name="Zendesk",
        provider_config={"subdomain": subdomain},
        triggers={},
        field_mapping={},
        auto_import=True,
    )
    db.add(source)
    db.flush()
    return True


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.post(
    "/connect",
    response_model=ZendeskConnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def zendesk_connect(
    payload: ZendeskConnectRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect or reconnect a Zendesk account via email + API token (Basic auth,
    token-access scheme).

    1. Normalizes subdomain to a bare label (422 if not a *.zendesk.com host).
    2. Resolves the host and rejects loopback/private/link-local addresses
       (SSRF gate, 422).
    3. Validates the token against Zendesk's /users/me.json endpoint (422 on
       auth failure, 502 on transient upstream errors).
    4. Encrypts api_token with Fernet (422 if LLM_ENCRYPTION_KEY is unset —
       R6). Generates + encrypts a new webhook_secret only if this is the
       first connect (row is new, or its webhook_secret is still None) —
       reconnect preserves the existing webhook_secret.
    5. Upserts the row by organization_id (reconnect rotates api_token only).
    6. Auto-provisions a default `zendesk` FeedbackSource if none exists yet.
    7. Returns metadata + the current plaintext webhook_secret (display-once
       contract). api_token is NEVER included in the response.
    """
    subdomain = _normalize_subdomain(payload.subdomain)
    host = f"{subdomain}.zendesk.com"
    _assert_host_not_ssrf(host)

    zendesk_client = ZendeskClient(subdomain, payload.email, payload.api_token)
    try:
        try:
            info = zendesk_client.validate()
        except ZendeskAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Zendesk token is invalid or lacks required permissions.",
            ) from exc
        except ZendeskTransientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Zendesk API returned a transient error: {exc}",
            ) from exc
    finally:
        _close_client(zendesk_client)

    try:
        encrypted_token = encrypt_api_key(payload.api_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot store Zendesk token: LLM_ENCRYPTION_KEY is not set. "
                "Set this environment variable and restart the service to "
                "connect a Zendesk integration."
            ),
        ) from exc

    hint = get_key_hint(payload.api_token)
    account_user_id = info.get("account_user_id")
    display_name = info.get("display_name")

    existing = _get_org_integration(db, current_org.id)

    # Determine whether a NEW webhook_secret must be generated + encrypted
    # (first connect, or an existing row whose webhook_secret is still
    # None), before touching the row — so both encrypt_api_key calls are
    # inside this same try/except (R6: neither can raise past the route
    # boundary as an uncaught 500).
    needs_new_webhook_secret = existing is None or existing.webhook_secret is None
    encrypted_webhook_secret = existing.webhook_secret if existing else None
    plaintext_webhook_secret: Optional[str] = None

    if needs_new_webhook_secret:
        plaintext_webhook_secret = _generate_webhook_secret()
        try:
            encrypted_webhook_secret = encrypt_api_key(plaintext_webhook_secret)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot store Zendesk webhook secret: LLM_ENCRYPTION_KEY "
                    "is not set. Set this environment variable and restart "
                    "the service to connect a Zendesk integration."
                ),
            ) from exc
    else:
        plaintext_webhook_secret = decrypt_api_key(existing.webhook_secret)

    if existing:
        existing.subdomain = subdomain
        existing.email = payload.email
        existing.api_token = encrypted_token
        existing.token_hint = hint
        existing.webhook_secret = encrypted_webhook_secret
        existing.account_user_id = account_user_id
        existing.display_name = display_name
        existing.is_active = True
        existing.connected_by_user_id = current_user.id
        existing.connected_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        integration = existing
    else:
        integration = ZendeskIntegration(
            organization_id=current_org.id,
            subdomain=subdomain,
            email=payload.email,
            api_token=encrypted_token,
            token_hint=hint,
            webhook_secret=encrypted_webhook_secret,
            account_user_id=account_user_id,
            display_name=display_name,
            is_active=True,
            connected_by_user_id=current_user.id,
            connected_at=datetime.utcnow(),
        )
        db.add(integration)

    has_feedback_source = _ensure_default_feedback_source(db, current_org.id, subdomain)

    db.commit()
    db.refresh(integration)

    logger.info(
        "Zendesk connected for org %s (subdomain %s)", current_org.id, integration.subdomain
    )
    return ZendeskConnectResponse(
        connected=True,
        subdomain=integration.subdomain,
        email=integration.email,
        token_hint=integration.token_hint,
        account_user_id=integration.account_user_id,
        display_name=integration.display_name,
        webhook_secret=plaintext_webhook_secret,
        has_feedback_source=has_feedback_source,
    )


@router.get(
    "/status",
    response_model=ZendeskStatusResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def zendesk_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return connection status. Never returns api_token or webhook_secret.

    `has_feedback_source` uses the read-only existence check
    (`_has_zendesk_source`) — this GET route never creates a FeedbackSource.
    """
    row = _get_active_integration(db, current_org.id)
    if not row:
        return ZendeskStatusResponse(connected=False)
    return ZendeskStatusResponse(
        connected=True,
        subdomain=row.subdomain,
        email=row.email,
        token_hint=row.token_hint,
        account_user_id=row.account_user_id,
        display_name=row.display_name,
        is_active=row.is_active,
        last_synced_at=row.last_synced_at,
        last_sync_status=row.last_sync_status,
        last_error=row.last_error,
        connected_at=row.connected_at,
        has_feedback_source=_has_zendesk_source(db, current_org.id),
    )


@router.delete(
    "/disconnect",
    response_model=ZendeskDisconnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def zendesk_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Deactivate (soft-delete) the Zendesk integration for this org.

    Connection and source lifecycle are intentionally decoupled (PRD 9a) —
    this does NOT touch the auto-provisioned FeedbackSource. Zendesk is not
    a CRM — this must NOT call crm_integration_common.purge_crm_enrichment
    or any CRM purge path.
    """
    row = _get_org_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Zendesk integration found.",
        )
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()

    return ZendeskDisconnectResponse(
        success=True,
        message="Zendesk integration disconnected.",
    )


@router.post(
    "/test",
    response_model=ZendeskTestResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def zendesk_test(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Re-validate the stored Zendesk token.

    Returns {"success": true/false, "message": "..."}.
    Never raises a 500 — all errors (decrypt failure, auth failure,
    transient upstream errors, network errors) are surfaced as
    {"success": false}.
    """
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Zendesk integration.",
        )
    try:
        plain_token = get_decrypted_token(row)
        zendesk_client = ZendeskClient(row.subdomain, row.email, plain_token)
        try:
            zendesk_client.validate()
        finally:
            _close_client(zendesk_client)
        return ZendeskTestResponse(success=True, message="Zendesk connection is healthy.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — must never surface as a 500
        logger.warning("Zendesk test failed for org %s: %s", current_org.id, exc)
        return ZendeskTestResponse(success=False, message=str(exc))
