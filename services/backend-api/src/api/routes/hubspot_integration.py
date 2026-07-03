"""
HubSpot CRM integration routes.

Routes:
  POST   /api/v1/integrations/hubspot/connect     — store encrypted token
  GET    /api/v1/integrations/hubspot/status      — connection status (no token)
  DELETE /api/v1/integrations/hubspot/disconnect  — deactivate
  POST   /api/v1/integrations/hubspot/test        — validate stored token

All endpoints require admin/owner role + hubspot_integration feature.
Token is Fernet-encrypted via encrypt_api_key. Never returned in any response.

R6 safeguard: POST /connect catches ValueError from encrypt_api_key
(raised when LLM_ENCRYPTION_KEY is unset) and returns HTTP 422 with an
operator-actionable message — never a 500.
"""
import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
    require_feature,
)
from src.database.session import get_db
from src.models.hubspot_integration import HubSpotIntegration
from src.models.organization import Organization
from src.models.user import User
from src.services.crm_integration_common import another_crm_active, purge_crm_enrichment
from src.services.hubspot_writeback_validation import validate_writeback_field
from src.utils.encryption import decrypt_api_key, encrypt_api_key, get_key_hint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/hubspot", tags=["hubspot"])

HUBSPOT_ACCOUNT_INFO_URL = "https://api.hubapi.com/account-info/v3/details"

# ──────────────────────── Pydantic schemas ────────────────────────────────────


class HubSpotConnectRequest(BaseModel):
    access_token: str = Field(..., min_length=1)
    arr_property_name: str = Field(default="annualrevenue", min_length=1)


class HubSpotConnectResponse(BaseModel):
    connected: bool
    portal_name: Optional[str] = None
    hub_id: Optional[str] = None
    token_hint: Optional[str] = None
    # access_token is intentionally NEVER included


class HubSpotStatusResponse(BaseModel):
    connected: bool
    portal_name: Optional[str] = None
    hub_id: Optional[str] = None
    token_hint: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    contacts_synced: int = 0
    contacts_matched: int = 0
    arr_property_name: str = "annualrevenue"
    connected_at: Optional[datetime] = None
    # CRM writeback config/status (writeback-config-api aspect)
    writeback_enabled: bool = False
    writeback_field_name: Optional[str] = None
    last_writeback_at: Optional[datetime] = None
    last_writeback_status: Optional[str] = None
    last_writeback_error: Optional[str] = None
    contacts_written: int = 0
    # access_token is intentionally NEVER included


class HubSpotDisconnectResponse(BaseModel):
    success: bool
    message: str


class HubSpotWritebackRequest(BaseModel):
    enabled: bool
    field_name: Optional[str] = Field(default=None, min_length=1)


class HubSpotWritebackResponse(BaseModel):
    writeback_enabled: bool
    writeback_field_name: Optional[str] = None
    last_writeback_at: Optional[datetime] = None
    last_writeback_status: Optional[str] = None
    last_writeback_error: Optional[str] = None
    contacts_written: int = 0


class HubSpotWritebackTestRequest(BaseModel):
    field_name: str = Field(..., min_length=1)


class HubSpotWritebackTestResponse(BaseModel):
    ok: bool
    reason: Optional[str] = None


# ──────────────────────── Internal helpers ───────────────────────────────────


def _validate_hubspot_token(access_token: str) -> dict:
    """
    Validate a HubSpot private-app token by calling /account-info/v3/details.

    Returns portal metadata dict on success.
    Raises HTTPException 422 on auth failure (401/403).
    Raises HTTPException 502 on other HTTP errors or network errors.
    """
    try:
        with httpx.Client(timeout=10.0) as http_client:
            resp = http_client.get(
                HUBSPOT_ACCOUNT_INFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="HubSpot token is invalid or lacks required permissions.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HubSpot API returned {exc.response.status_code}.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach HubSpot API: {exc}",
        )


def _get_active_integration(
    org_id: int, db: Session
) -> Optional[HubSpotIntegration]:
    """Return the active HubSpot integration for an org, or None."""
    return (
        db.query(HubSpotIntegration)
        .filter(
            HubSpotIntegration.organization_id == org_id,
            HubSpotIntegration.is_active.is_(True),
        )
        .first()
    )


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.post(
    "/connect",
    response_model=HubSpotConnectResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_connect(
    payload: HubSpotConnectRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect or re-connect a HubSpot private-app token.

    1. Blocks (409) if another CRM (Salesforce) is already active for this org.
    2. Validates the token against HubSpot's account-info endpoint.
    3. Encrypts with Fernet (raises 422 if LLM_ENCRYPTION_KEY is unset — R6).
    4. Upserts the row (second connect rotates the token).
    5. Returns metadata (portal name, hub_id, token_hint). Never returns the token.
    """
    # Step 0: One-CRM guard — symmetric with salesforce_integration.py's
    # connect-url/callback, so the collision cannot be created from either side.
    other = another_crm_active(db, current_org.id, exclude_provider="hubspot")
    if other:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Another CRM ({other}) is already connected for this organization. "
                f"Disconnect {other} first before connecting HubSpot."
            ),
        )

    # Step 1: Validate token against HubSpot before storing anything
    portal_meta = _validate_hubspot_token(payload.access_token)

    # Step 2: Encrypt — catch ValueError from missing LLM_ENCRYPTION_KEY (R6)
    try:
        encrypted = encrypt_api_key(payload.access_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot store HubSpot token: LLM_ENCRYPTION_KEY is not set. "
                "Set this environment variable and restart the service to connect "
                "a CRM integration."
            ),
        ) from exc

    hint = get_key_hint(payload.access_token)  # "...last4"
    hub_id = str(portal_meta.get("portalId", ""))
    portal_name = portal_meta.get("companyName") or portal_meta.get("timeZone")

    # Step 3: Upsert — query by org (not requiring is_active so we can reactivate)
    existing = (
        db.query(HubSpotIntegration)
        .filter(HubSpotIntegration.organization_id == current_org.id)
        .first()
    )
    if existing:
        existing.access_token = encrypted
        existing.token_hint = hint
        existing.hub_id = hub_id
        existing.portal_name = portal_name
        existing.arr_property_name = payload.arr_property_name
        existing.connected_by_user_id = current_user.id
        existing.connected_at = datetime.utcnow()
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        integration = existing
    else:
        integration = HubSpotIntegration(
            organization_id=current_org.id,
            access_token=encrypted,
            token_hint=hint,
            hub_id=hub_id,
            portal_name=portal_name,
            arr_property_name=payload.arr_property_name,
            connected_by_user_id=current_user.id,
            connected_at=datetime.utcnow(),
            is_active=True,
        )
        db.add(integration)

    db.commit()
    db.refresh(integration)

    logger.info(
        "HubSpot connected for org %s (portal %s)",
        current_org.id,
        integration.hub_id,
    )
    return HubSpotConnectResponse(
        connected=True,
        portal_name=integration.portal_name,
        hub_id=integration.hub_id,
        token_hint=integration.token_hint,
    )


@router.get(
    "/status",
    response_model=HubSpotStatusResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return connection status. Never returns the access_token."""
    row = _get_active_integration(current_org.id, db)
    if not row:
        return HubSpotStatusResponse(connected=False)
    return HubSpotStatusResponse(
        connected=True,
        portal_name=row.portal_name,
        hub_id=row.hub_id,
        token_hint=row.token_hint,
        last_synced_at=row.last_synced_at,
        last_sync_status=row.last_sync_status,
        last_error=row.last_error,
        contacts_synced=row.contacts_synced,
        contacts_matched=row.contacts_matched,
        arr_property_name=row.arr_property_name,
        connected_at=row.connected_at,
        writeback_enabled=row.writeback_enabled,
        writeback_field_name=row.writeback_field_name,
        last_writeback_at=row.last_writeback_at,
        last_writeback_status=row.last_writeback_status,
        last_writeback_error=row.last_writeback_error,
        contacts_written=row.contacts_written,
    )


@router.delete(
    "/disconnect",
    response_model=HubSpotDisconnectResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Deactivate (soft-delete) the HubSpot integration for this org, then purge
    (locked decision 7): delete this org's crm_enrichment rows with
    provider='hubspot' and recompute the affected customers' health scores,
    so a disconnected CRM stops influencing scores.
    """
    row = (
        db.query(HubSpotIntegration)
        .filter(HubSpotIntegration.organization_id == current_org.id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No HubSpot integration found.",
        )
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()

    purge_crm_enrichment(db, current_org.id, "hubspot")

    return HubSpotDisconnectResponse(
        success=True,
        message="HubSpot integration disconnected.",
    )


@router.post(
    "/test",
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_test(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Re-validate the stored HubSpot token.

    Returns {"success": true/false, "message": "..."}.
    Never raises a 500 — all errors are surfaced as {"success": false}.
    """
    row = _get_active_integration(current_org.id, db)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active HubSpot integration.",
        )
    try:
        plain_token = decrypt_api_key(row.access_token)
        _validate_hubspot_token(plain_token)
        return {"success": True, "message": "HubSpot connection is healthy."}
    except HTTPException as exc:
        return {"success": False, "message": exc.detail}
    except Exception as exc:
        logger.warning(
            "HubSpot test failed for org %s: %s", current_org.id, exc
        )
        return {"success": False, "message": str(exc)}


@router.patch(
    "/writeback",
    response_model=HubSpotWritebackResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_configure_writeback(
    payload: HubSpotWritebackRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Configure per-org HubSpot writeback (push health scores back to HubSpot).

    Enabling requires a `field_name`, which is validated (exists, number type,
    writable) against HubSpot before being persisted — validation failure
    returns 400 with a machine-readable `reason` and leaves the integration
    disabled. Disabling never requires (or touches) the field name.
    """
    integration = _get_active_integration(current_org.id, db)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active HubSpot integration found.",
        )

    if payload.enabled:
        field_name = (payload.field_name or "").strip()
        if not field_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="field_name is required when enabling writeback.",
            )

        plain_token = get_decrypted_token(integration)
        ok, reason = validate_writeback_field(plain_token, field_name)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "reason": reason,
                    "message": f"Field '{field_name}' failed writeback validation: {reason}.",
                },
            )

        integration.writeback_enabled = True
        integration.writeback_field_name = field_name
        integration.last_writeback_status = None
        integration.last_writeback_error = None
    else:
        integration.writeback_enabled = False

    integration.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(integration)

    return HubSpotWritebackResponse(
        writeback_enabled=integration.writeback_enabled,
        writeback_field_name=integration.writeback_field_name,
        last_writeback_at=integration.last_writeback_at,
        last_writeback_status=integration.last_writeback_status,
        last_writeback_error=integration.last_writeback_error,
        contacts_written=integration.contacts_written,
    )


@router.post(
    "/writeback/test",
    response_model=HubSpotWritebackTestResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_writeback_test(
    payload: HubSpotWritebackTestRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    On-demand validation of a candidate writeback field, without persisting
    anything. Returns {"ok": true/false, "reason": "..." | null}.
    """
    integration = _get_active_integration(current_org.id, db)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active HubSpot integration.",
        )

    field_name = payload.field_name.strip()
    plain_token = get_decrypted_token(integration)
    ok, reason = validate_writeback_field(plain_token, field_name)
    return HubSpotWritebackTestResponse(ok=ok, reason=reason)


# ──────────────────────── Sync trigger endpoint ──────────────────────────────


def _get_celery_app():
    """Lazy accessor for the Celery client app — injectable in tests."""
    from src.background.celery_client import get_celery_app
    return get_celery_app()


class HubSpotSyncResponse(BaseModel):
    status: str
    integration_id: int


@router.post(
    "/sync",
    response_model=HubSpotSyncResponse,
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("hubspot_integration")),
    ],
)
def hubspot_trigger_sync(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Manually enqueue a HubSpot CRM sync for this org.

    Requires admin or owner role and active integration.
    Enqueues sync_hubspot_org via Celery send_task (non-blocking).
    Returns {"status": "queued", "integration_id": <id>}.
    """
    integ = _get_active_integration(current_org.id, db)
    if not integ:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active HubSpot integration found.",
        )

    _get_celery_app().send_task(
        "src.tasks.hubspot_sync.sync_hubspot_org",
        args=[integ.id],
    )
    logger.info(
        "HubSpot sync manually triggered for org %s (integration_id=%s)",
        current_org.id,
        integ.id,
    )
    return HubSpotSyncResponse(status="queued", integration_id=integ.id)


# ──────────────────────── Exported helper for hubspot-sync ───────────────────


def get_decrypted_token(integration: HubSpotIntegration) -> str:
    """
    Decrypt and return the plaintext HubSpot token stored in integration.

    Exported for use by the hubspot-sync aspect.
    Raises cryptography.fernet.InvalidToken on corruption — callers should
    handle this and mark last_sync_status='error'.
    """
    return decrypt_api_key(integration.access_token)
