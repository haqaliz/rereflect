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
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
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


def _api_version() -> str:
    return os.environ.get("SALESFORCE_API_VERSION", "v60.0")


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
    # refresh_token / access_token are intentionally NEVER included


class SalesforceDisconnectResponse(BaseModel):
    success: bool
    message: str


class SalesforceSyncResponse(BaseModel):
    status: str
    integration_id: int


# ──────────────────────── State signing (CSRF) ────────────────────────────────


def _sign_state(org_id: int, user_id: int) -> str:
    """Sign a stateless OAuth `state` param (HMAC-SHA256, app-secret keyed)."""
    payload = {
        "org_id": org_id,
        "user_id": user_id,
        "ts": int(time.time()),
        "nonce": secrets.token_urlsafe(8),
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

    if not _client_id():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Salesforce OAuth is not configured. Set SALESFORCE_CLIENT_ID environment variable.",
        )

    state = _sign_state(current_org.id, current_user.id)
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
    )
