"""
Salesforce CRM integration routes — web-server OAuth 2.0.

Mirrors the in-repo Linear OAuth pattern (getConnectUrl -> auth_url ->
callback), NOT HubSpot's pasted-token form. Credentials are stored as an
encrypted refresh_token + instance_url; a short-lived access token is minted
from the refresh token before each sync (worker-side, aspect 3).

Routes:
  GET    /api/v1/integrations/salesforce/connect-url  — build authorize URL
  GET    /api/v1/integrations/salesforce/callback     — OAuth code exchange
  GET    /api/v1/integrations/salesforce/status       — connection status (no tokens)
  DELETE /api/v1/integrations/salesforce/disconnect   — deactivate + purge
  POST   /api/v1/integrations/salesforce/test         — validate stored refresh token
  POST   /api/v1/integrations/salesforce/sync         — manual sync trigger

All endpoints (except the OAuth callback, which Salesforce itself calls)
require admin/owner role + salesforce_integration feature.

One-CRM guard: connecting Salesforce while HubSpot is active is blocked
(409) via the shared `another_crm_active` helper — see
src/services/crm_integration_common.py. The same guard is applied
symmetrically to hubspot_integration.py's connect endpoint.

R6 safeguard: refresh_token encryption catches ValueError from
encrypt_api_key (raised when LLM_ENCRYPTION_KEY is unset) and returns
HTTP 422 with an operator-actionable message — never a 500.

SEC-1 safeguard: the signed `state` param is bound to the initiating
browser via an HttpOnly session-nonce cookie (`SF_OAUTH_NONCE_COOKIE`) set
by /connect-url and re-checked (hmac.compare_digest over the SHA-256 hash)
by /callback before org_id/user_id are trusted. The callback is
unauthenticated (Salesforce redirects to it; no JWT reaches it), so
without this binding an attacker-minted signed state completed by a
victim's browser would link the VICTIM's Salesforce refresh token into the
ATTACKER's org (OAuth CSRF / account-linking). Kept stateless — no
server-side store, just the cookie + a hash embedded in the signed state.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
    require_feature,
)
from src.database.session import get_db
from src.models.organization import Organization
from src.models.salesforce_integration import SalesforceIntegration
from src.models.user import User
from src.services.crm_integration_common import another_crm_active, purge_crm_enrichment
from src.services.salesforce_writeback_validation import validate_writeback_field
from src.utils.encryption import decrypt_api_key, encrypt_api_key, get_key_hint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/salesforce", tags=["salesforce"])

# Salesforce Connected App configuration — read at call time (not baked in at
# import) so tests can override via patch.dict(os.environ, ...).
def _client_id() -> str:
    return os.environ.get("SALESFORCE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.environ.get("SALESFORCE_CLIENT_SECRET", "")


def _redirect_uri() -> str:
    return os.environ.get(
        "SALESFORCE_REDIRECT_URI",
        "http://localhost:8000/api/v1/integrations/salesforce/callback",
    )


def _login_base() -> str:
    return os.environ.get("SALESFORCE_LOGIN_BASE", "https://login.salesforce.com")


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


# JWT_SECRET is already used app-wide to sign auth tokens; reuse it to sign
# the OAuth `state` param (stateless — no server-side session needed, works
# across multiple worker processes).
def _app_secret() -> str:
    from src.api.auth import JWT_SECRET
    return JWT_SECRET


STATE_TTL_SECONDS = 600  # 10 minutes
SALESFORCE_SCOPE = "refresh_token offline_access api"

# SEC-1: HttpOnly cookie binding the signed OAuth `state` to the browser
# that initiated the flow. Scoped to the callback path only.
SF_OAUTH_NONCE_COOKIE = "sf_oauth_nonce"
SF_CALLBACK_PATH = "/api/v1/integrations/salesforce/callback"


# ──────────────────────── Pydantic schemas ────────────────────────────────────


class SalesforceConnectUrlResponse(BaseModel):
    auth_url: str


class SalesforceStatusResponse(BaseModel):
    connected: bool
    instance_url: Optional[str] = None
    sf_org_id: Optional[str] = None
    token_hint: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    contacts_synced: int = 0
    contacts_matched: int = 0
    connected_at: Optional[datetime] = None
    # CRM writeback config/status (writeback-config-api aspect)
    writeback_enabled: bool = False
    writeback_field_name: Optional[str] = None
    last_writeback_at: Optional[datetime] = None
    last_writeback_status: Optional[str] = None
    last_writeback_error: Optional[str] = None
    contacts_written: int = 0
    # refresh_token / access_token are intentionally NEVER included


class SalesforceDisconnectResponse(BaseModel):
    success: bool
    message: str


class SalesforceSyncResponse(BaseModel):
    status: str
    integration_id: int


class SalesforceWritebackRequest(BaseModel):
    enabled: bool
    field_name: Optional[str] = Field(default=None, min_length=1)


class SalesforceWritebackResponse(BaseModel):
    writeback_enabled: bool
    writeback_field_name: Optional[str] = None
    last_writeback_at: Optional[datetime] = None
    last_writeback_status: Optional[str] = None
    last_writeback_error: Optional[str] = None
    contacts_written: int = 0


class SalesforceWritebackTestRequest(BaseModel):
    field_name: str = Field(..., min_length=1)


class SalesforceWritebackTestResponse(BaseModel):
    ok: bool
    reason: Optional[str] = None


# CRM writeback (writeback-task-trigger aspect): bound on backfill-on-enable
# fan-out so a huge org can't enqueue an unbounded burst of pushes.
WRITEBACK_BACKFILL_CAP = 500


# ──────────────────────── State signing (CSRF) ────────────────────────────────


def _hash_nonce(nonce: str) -> str:
    """SHA-256 hex digest of a session nonce (stored in state, never the raw nonce)."""
    return hashlib.sha256(nonce.encode()).hexdigest()


def _sign_state(org_id: int, user_id: int, session_nonce_hash: str) -> str:
    """
    Sign a stateless OAuth `state` param (HMAC-SHA256, app-secret keyed).

    `session_nonce_hash` (SHA-256 of the raw nonce set as an HttpOnly cookie
    by /connect-url) binds this state to the initiating browser — see
    SEC-1 in the module docstring. The callback must verify it via
    hmac.compare_digest before trusting org_id/user_id.
    """
    payload = {
        "org_id": org_id,
        "user_id": user_id,
        "ts": int(time.time()),
        "nonce": secrets.token_urlsafe(8),
        "session_nonce_hash": session_nonce_hash,
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
    sig = hmac.new(_app_secret().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_state(state: str) -> Optional[dict]:
    """Verify + decode a signed state. Returns the payload dict, or None if invalid/expired."""
    if not state or "." not in state:
        return None
    payload_b64, _, sig = state.rpartition(".")
    expected_sig = hmac.new(_app_secret().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None
    if time.time() - payload.get("ts", 0) > STATE_TTL_SECONDS:
        return None
    return payload


def _parse_sf_org_id(identity_url: Optional[str]) -> Optional[str]:
    """
    Derive the Salesforce org id from the OAuth token response's `id` field,
    e.g. "https://login.salesforce.com/id/00Dxx0000001gPFEAY/005xx000001Sv6AAAS"
    -> "00Dxx0000001gPFEAY".
    """
    if not identity_url or "/id/" not in identity_url:
        return None
    tail = identity_url.split("/id/", 1)[1]
    parts = [p for p in tail.split("/") if p]
    return parts[0] if parts else None


# ──────────────────────── Internal helpers ───────────────────────────────────


def _get_active_integration(org_id: int, db: Session) -> Optional[SalesforceIntegration]:
    """Return the active Salesforce integration for an org, or None."""
    return (
        db.query(SalesforceIntegration)
        .filter(
            SalesforceIntegration.organization_id == org_id,
            SalesforceIntegration.is_active.is_(True),
        )
        .first()
    )


def _get_celery_app():
    """Lazy accessor for the Celery client app — injectable in tests."""
    from src.background.celery_client import get_celery_app
    return get_celery_app()


def _exchange_code_for_token(code: str) -> dict:
    """
    POST the OAuth authorization code to Salesforce's token endpoint.

    Raises httpx.HTTPStatusError on a non-2xx response (e.g. invalid_grant)
    and httpx.RequestError on a network failure. Callers must handle both.
    """
    with httpx.Client(timeout=15.0) as http_client:
        resp = http_client.post(
            f"{_login_base()}/services/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": _redirect_uri(),
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


def _refresh_access_token(refresh_token: str) -> dict:
    """Mint a short-lived access token from a stored refresh token."""
    with httpx.Client(timeout=15.0) as http_client:
        resp = http_client.post(
            f"{_login_base()}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


def _validate_access_token(instance_url: str, access_token: str) -> dict:
    """Lightweight probe that the access token + instance_url are usable."""
    with httpx.Client(timeout=10.0) as http_client:
        resp = http_client.get(
            f"{instance_url}/services/oauth2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.get(
    "/connect-url",
    response_model=SalesforceConnectUrlResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("salesforce_integration")),
    ],
)
def salesforce_connect_url(
    response: Response,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build the Salesforce OAuth authorize URL. Blocked (409) if HubSpot is active."""
    other = another_crm_active(db, current_org.id, exclude_provider="salesforce")
    if other:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Another CRM ({other}) is already connected for this organization. "
                f"Disconnect {other} first before connecting Salesforce."
            ),
        )

    # M5: a missing Connected App credential is an operator misconfiguration,
    # not a server fault — surface it as a 422 (mirrors the R6
    # encryption-key 422 pattern above) rather than a 500.
    if not _client_id() or not _client_secret() or not _redirect_uri():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Salesforce OAuth is not configured. Set SALESFORCE_CLIENT_ID, "
                "SALESFORCE_CLIENT_SECRET, and SALESFORCE_REDIRECT_URI environment "
                "variables and restart the service to connect Salesforce."
            ),
        )

    # SEC-1: mint a session nonce, embed its hash in the signed state, and
    # set the raw nonce as an HttpOnly/Secure cookie scoped to the callback
    # path. /callback must see the same cookie back before it trusts the
    # state's org_id/user_id.
    session_nonce = secrets.token_urlsafe(32)
    state = _sign_state(current_org.id, current_user.id, _hash_nonce(session_nonce))
    response.set_cookie(
        key=SF_OAUTH_NONCE_COOKIE,
        value=session_nonce,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path=SF_CALLBACK_PATH,
    )

    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "scope": SALESFORCE_SCOPE,
        "state": state,
    }
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    auth_url = f"{_login_base()}/services/oauth2/authorize?{query}"
    logger.info("Generated Salesforce OAuth URL for org %s", current_org.id)
    return SalesforceConnectUrlResponse(auth_url=auth_url)


@router.get(
    "/status",
    response_model=SalesforceStatusResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("salesforce_integration")),
    ],
)
def salesforce_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return connection status. Never returns the refresh/access token."""
    row = _get_active_integration(current_org.id, db)
    if not row:
        return SalesforceStatusResponse(connected=False)
    return SalesforceStatusResponse(
        connected=True,
        instance_url=row.instance_url,
        sf_org_id=row.sf_org_id,
        token_hint=row.token_hint,
        last_synced_at=row.last_synced_at,
        last_sync_status=row.last_sync_status,
        last_error=row.last_error,
        contacts_synced=row.contacts_synced,
        contacts_matched=row.contacts_matched,
        connected_at=row.connected_at,
        writeback_enabled=row.writeback_enabled,
        writeback_field_name=row.writeback_field_name,
        last_writeback_at=row.last_writeback_at,
        last_writeback_status=row.last_writeback_status,
        last_writeback_error=row.last_writeback_error,
        contacts_written=row.contacts_written,
    )


@router.get("/callback")
def salesforce_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Handle the Salesforce OAuth redirect. Exchanges `code` for tokens,
    validates them, encrypts + upserts the integration, and redirects back
    to the frontend settings page (mirrors linear_integration.py's callback).
    """
    error_redirect_base = f"{_frontend_url()}/settings/integrations/salesforce"

    if error:
        logger.error("Salesforce OAuth error: %s", error)
        return RedirectResponse(
            url=f"{error_redirect_base}?oauth_error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        return RedirectResponse(url=f"{error_redirect_base}?oauth_error=missing_params")

    payload = _verify_state(state)
    if not payload:
        logger.error("Invalid or expired Salesforce OAuth state")
        return RedirectResponse(url=f"{error_redirect_base}?oauth_error=invalid_state")

    # SEC-1: the callback is unauthenticated (Salesforce calls it directly;
    # no JWT reaches it), so a validly-signed state is not enough — it must
    # also have been minted for THIS browser. Require the HttpOnly nonce
    # cookie set by /connect-url to match the hash embedded in the state
    # BEFORE trusting org_id/user_id or doing any token exchange / DB write.
    # Without this, an attacker-minted state completed by a victim's
    # browser would link the victim's Salesforce token into the attacker's
    # org (OAuth CSRF / account-linking).
    cookie_nonce = request.cookies.get(SF_OAUTH_NONCE_COOKIE)
    expected_nonce_hash = payload.get("session_nonce_hash")
    if not cookie_nonce or not expected_nonce_hash or not hmac.compare_digest(
        _hash_nonce(cookie_nonce), expected_nonce_hash
    ):
        logger.error(
            "Salesforce OAuth callback rejected: missing/mismatched session "
            "nonce cookie (possible OAuth CSRF / account-linking attempt)"
        )
        redirect = RedirectResponse(url=f"{error_redirect_base}?oauth_error=invalid_state")
        redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
        return redirect

    org_id = payload["org_id"]
    user_id = payload["user_id"]

    # Re-check the one-CRM guard (defense-in-depth against a race between
    # connect-url and callback).
    other = another_crm_active(db, org_id, exclude_provider="salesforce")
    if other:
        logger.warning(
            "Salesforce callback blocked for org %s: %s already active", org_id, other
        )
        redirect = RedirectResponse(url=f"{error_redirect_base}?oauth_error=another_crm_active")
        redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
        return redirect

    try:
        token_data = _exchange_code_for_token(code)
    except httpx.HTTPStatusError as exc:
        sf_error = "token_exchange_failed"
        try:
            sf_error = exc.response.json().get("error", sf_error)
        except Exception:
            pass
        logger.error("Salesforce token exchange failed for org %s: %s", org_id, sf_error)
        redirect = RedirectResponse(
            url=f"{error_redirect_base}?oauth_error={urllib.parse.quote(sf_error)}"
        )
        redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
        return redirect
    except httpx.RequestError as exc:
        logger.error("Salesforce token exchange network error for org %s: %s", org_id, exc)
        redirect = RedirectResponse(url=f"{error_redirect_base}?oauth_error=network_error")
        redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
        return redirect

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    instance_url = token_data.get("instance_url")
    identity_url = token_data.get("id")

    if not access_token or not refresh_token or not instance_url:
        logger.error("Salesforce token response incomplete for org %s", org_id)
        redirect = RedirectResponse(
            url=f"{error_redirect_base}?oauth_error=incomplete_token_response"
        )
        redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
        return redirect

    try:
        _validate_access_token(instance_url, access_token)
    except Exception as exc:
        logger.error("Salesforce token validation failed for org %s: %s", org_id, exc)
        redirect = RedirectResponse(url=f"{error_redirect_base}?oauth_error=validation_failed")
        redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
        return redirect

    sf_org_id = _parse_sf_org_id(identity_url)

    # R6: encrypt — catch ValueError from missing LLM_ENCRYPTION_KEY. This is
    # an operator configuration error, so surface it directly as a 422
    # rather than a silent redirect.
    try:
        encrypted = encrypt_api_key(refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot store Salesforce refresh token: LLM_ENCRYPTION_KEY is not set. "
                "Set this environment variable and restart the service to connect "
                "a CRM integration."
            ),
        ) from exc

    hint = get_key_hint(refresh_token)

    existing = (
        db.query(SalesforceIntegration)
        .filter(SalesforceIntegration.organization_id == org_id)
        .first()
    )
    if existing:
        existing.refresh_token = encrypted
        existing.instance_url = instance_url
        existing.sf_org_id = sf_org_id
        existing.token_hint = hint
        existing.connected_by_user_id = user_id
        existing.connected_at = datetime.utcnow()
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
    else:
        integration = SalesforceIntegration(
            organization_id=org_id,
            refresh_token=encrypted,
            instance_url=instance_url,
            sf_org_id=sf_org_id,
            token_hint=hint,
            connected_by_user_id=user_id,
            connected_at=datetime.utcnow(),
            is_active=True,
        )
        db.add(integration)

    db.commit()
    logger.info("Salesforce connected for org %s (sf_org_id=%s)", org_id, sf_org_id)

    redirect = RedirectResponse(url=f"{error_redirect_base}?connected=1")
    redirect.delete_cookie(SF_OAUTH_NONCE_COOKIE, path=SF_CALLBACK_PATH)
    return redirect


@router.post(
    "/test",
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("salesforce_integration")),
    ],
)
def salesforce_test(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Re-validate the stored Salesforce connection by refreshing an access
    token and probing it.

    Returns {"success": true/false, "message": "..."}.
    Never raises a 500 — all errors are surfaced as {"success": false}.
    """
    row = _get_active_integration(current_org.id, db)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Salesforce integration.",
        )
    try:
        plain_refresh = decrypt_api_key(row.refresh_token)
        token_data = _refresh_access_token(plain_refresh)
        access_token = token_data.get("access_token")
        instance_url = token_data.get("instance_url") or row.instance_url
        if not access_token or not instance_url:
            return {"success": False, "message": "Refresh did not return an access token."}
        _validate_access_token(instance_url, access_token)
        return {"success": True, "message": "Salesforce connection is healthy."}
    except Exception as exc:
        logger.warning("Salesforce test failed for org %s: %s", current_org.id, exc)
        return {"success": False, "message": str(exc)}


@router.delete(
    "/disconnect",
    response_model=SalesforceDisconnectResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("salesforce_integration")),
    ],
)
def salesforce_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Deactivate the Salesforce integration for this org, then purge (locked
    decision 7): delete this org's crm_enrichment rows with
    provider='salesforce' and recompute the affected customers' health
    scores, so a disconnected CRM stops influencing scores.
    """
    row = (
        db.query(SalesforceIntegration)
        .filter(SalesforceIntegration.organization_id == current_org.id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Salesforce integration found.",
        )
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()

    purge_crm_enrichment(db, current_org.id, "salesforce")

    return SalesforceDisconnectResponse(
        success=True,
        message="Salesforce integration disconnected.",
    )


@router.post(
    "/sync",
    response_model=SalesforceSyncResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("salesforce_integration")),
    ],
)
def salesforce_trigger_sync(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Manually enqueue a Salesforce CRM sync for this org.

    Requires admin or owner role and an active integration.
    Enqueues sync_salesforce_org via Celery send_task (non-blocking, lazy
    celery app — aspect-3 defines the task itself).
    """
    integ = _get_active_integration(current_org.id, db)
    if not integ:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Salesforce integration found.",
        )

    _get_celery_app().send_task(
        "src.tasks.salesforce_sync.sync_salesforce_org",
        args=[integ.id],
    )
    logger.info(
        "Salesforce sync manually triggered for org %s (integration_id=%s)",
        current_org.id,
        integ.id,
    )
    return SalesforceSyncResponse(status="queued", integration_id=integ.id)


# ──────────────────────── Exported helper for salesforce-sync ────────────────


def get_decrypted_refresh_token(integration: SalesforceIntegration) -> str:
    """
    Decrypt and return the plaintext Salesforce refresh_token stored in
    integration.

    Exported for use by the salesforce-sync aspect (worker). Raises
    cryptography.fernet.InvalidToken on corruption — callers should handle
    this and mark last_sync_status='error'.
    """
    return decrypt_api_key(integration.refresh_token)
