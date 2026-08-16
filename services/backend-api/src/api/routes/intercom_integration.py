"""Intercom token-paste connection routes.

Connect, status and disconnect for an Intercom **private app** Access Token.

Why this exists alongside the OAuth routes in `integrations.py`: Intercom was
the last integration still requiring OAuth, which was judged awkward for
self-host and rejected for HubSpot, Zendesk, Jira and Asana alike. Intercom's
own documentation designates the Access Token as the mechanism for "building a
private app" against "your own Intercom workspace" -- exactly the self-host
case. Both paths coexist (existing OAuth connections keep working), with a
one-connection-per-org guard below.

No SSRF DNS gate here, unlike Zendesk: the host is the fixed `api.intercom.io`,
so there is no per-org subdomain to resolve. Same reasoning recorded for Asana's
fixed `app.asana.com`.

See docs/planning/intercom-selfhost-ingestion/token-paste-connect/.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Literal, Optional

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
)
from src.database.session import get_db
from src.models.feedback_source import FeedbackSource
from src.models.integration import Integration
from src.models.intercom_integration import IntercomIntegration
from src.models.organization import Organization
from src.models.user import User
from src.utils.encryption import decrypt_api_key, encrypt_api_key, get_key_hint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/intercom", tags=["intercom"])

INTERCOM_API_BASE = "https://api.intercom.io"
_TIMEOUT_SECONDS = 15.0


# ──────────────────────── Client ─────────────────────────────────────────────


class IntercomAuthError(Exception):
    """The token was rejected (401/403). Operator-fixable; never retried."""


class IntercomTransientError(Exception):
    """Upstream 5xx / network failure. Not the operator's fault."""


class IntercomClient:
    """Minimal Intercom API client for connection validation.

    Only `validate()` is needed by this aspect; the pull path adds its own
    client under worker-service/src/clients/ (worker-service cannot import
    backend-api, so that is a separate module by necessity, not by choice).
    """

    def __init__(self, access_token: str):
        self._access_token = access_token
        self._client = httpx.Client(timeout=_TIMEOUT_SECONDS)

    def validate(self) -> Dict[str, Any]:
        """GET /me -- confirm the token works and identify the workspace.

        The response shape is the one the existing OAuth callback already
        parses (`app.id_code`, `app.name`, `id`); it is read here rather than
        re-invented so the two paths cannot drift.
        """
        try:
            response = self._client.get(
                f"{INTERCOM_API_BASE}/me",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise IntercomTransientError(str(exc)) from exc

        if response.status_code in (401, 403):
            raise IntercomAuthError(f"Intercom rejected the token ({response.status_code})")
        if response.status_code >= 500:
            raise IntercomTransientError(f"Intercom returned {response.status_code}")
        if response.status_code != 200:
            raise IntercomAuthError(f"Unexpected Intercom response {response.status_code}")

        payload = response.json()
        app = payload.get("app") or {}
        return {
            "workspace_id": app.get("id_code"),
            "workspace_name": app.get("name"),
            "admin_id": payload.get("id"),
        }

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # pragma: no cover - close must never mask a real error
            logger.debug("Failed to close Intercom client", exc_info=True)


def _close_client(client: Optional[IntercomClient]) -> None:
    if client is not None:
        client.close()


# ──────────────────────── Pydantic schemas ───────────────────────────────────


class IntercomConnectRequest(BaseModel):
    access_token: str = Field(..., min_length=1)
    # The Developer Hub app's client secret, which is what Intercom signs
    # X-Hub-Signature with. Optional: an operator who only wants the pull path
    # should not have to hand over a secret nothing currently reads.
    client_secret: Optional[str] = Field(default=None)


class IntercomConnectResponse(BaseModel):
    connected: bool
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    token_hint: Optional[str] = None
    admin_id: Optional[str] = None
    has_client_secret: bool = False
    has_feedback_source: bool = False


class IntercomStatusResponse(BaseModel):
    connected: bool
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    token_hint: Optional[str] = None
    admin_id: Optional[str] = None
    has_client_secret: bool = False
    has_feedback_source: bool = False
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    # How many feedback items this integration has actually produced.
    # Whether self-hosters use Intercom at all is unvalidated; this measures it
    # rather than assuming it, following the readiness-counter precedent set by
    # usage-decline-churn-labels. A connected integration sitting at 0 is the
    # single most useful thing an operator can know about it.
    feedback_items_ingested: int = 0
    # Backlog drain estimate (intercom-backlog-drain-visibility): how many
    # conversations remain in the sync window after the last completed run.
    # None = no estimate (never-synced, error reset, OAuth path has no pull).
    backlog_remaining: Optional[int] = None
    # Write-back config/status (config-api-routes aspect)
    writeback_enabled: bool = False
    writeback_action: str = "note_and_close"
    last_writeback_at: Optional[datetime] = None
    last_writeback_status: Optional[str] = None
    last_writeback_error: Optional[str] = None


class IntercomDisconnectResponse(BaseModel):
    disconnected: bool


class IntercomWritebackRequest(BaseModel):
    enabled: bool
    action: Optional[Literal["note_only", "note_and_close"]] = None
    model_config = {"extra": "forbid"}


class IntercomWritebackResponse(BaseModel):
    writeback_enabled: bool
    writeback_action: str
    last_writeback_at: Optional[datetime] = None
    last_writeback_status: Optional[str] = None
    last_writeback_error: Optional[str] = None


class IntercomWritebackTestResponse(BaseModel):
    ok: bool
    reason: Optional[str] = None


# ──────────────────────── Helpers ────────────────────────────────────────────


def _get_org_integration(db: Session, org_id: int) -> Optional[IntercomIntegration]:
    return (
        db.query(IntercomIntegration)
        .filter(IntercomIntegration.organization_id == org_id)
        .first()
    )


def _get_active_integration(db: Session, org_id: int) -> Optional[IntercomIntegration]:
    row = _get_org_integration(db, org_id)
    return row if row and row.is_active else None


def _has_active_oauth_connection(db: Session, org_id: int) -> bool:
    """True when this org already has an OAuth-connected Intercom integration.

    Two live credential sources for one workspace would mean two tenancy
    discriminators to keep correct on the inbound path. Rejecting is cheaper
    and safer than reconciling.
    """
    return (
        db.query(Integration)
        .filter(
            Integration.organization_id == org_id,
            Integration.type == "intercom",
            Integration.is_active == True,  # noqa: E712 - SQLAlchemy needs ==
        )
        .first()
        is not None
    )


def _count_ingested_items(db: Session, org_id: int) -> int:
    """Feedback items this org has ingested from Intercom."""
    from src.models.feedback import FeedbackItem

    return (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.source == "intercom",
        )
        .count()
    )


def _has_intercom_source(db: Session, org_id: int) -> bool:
    return (
        db.query(FeedbackSource)
        .filter(
            FeedbackSource.organization_id == org_id,
            FeedbackSource.source_type == "intercom",
        )
        .first()
        is not None
    )


def _ensure_default_feedback_source(db: Session, org_id: int, workspace_id: str) -> bool:
    """Auto-provision an Intercom FeedbackSource if the org has none.

    The `triggers` seed is load-bearing, not cosmetic. IntercomAdapter's
    check_triggers() (services/worker-service/src/adapters/intercom.py) reports
    a match ONLY when one of all_conversations / new_conversations / replies /
    ratings is truthy -- a source created with `triggers={}` silently drops
    every delivery, webhook and pull alike, while still looking connected in
    the UI. Zendesk hit the identical trap and seeds `new_ticket` for the same
    reason.
    """
    if _has_intercom_source(db, org_id):
        return True

    source = FeedbackSource(
        organization_id=org_id,
        integration_id=None,  # intercom token-paste is own-auth, like zendesk/jira
        source_type="intercom",
        name="Intercom",
        provider_config={"workspace_id": workspace_id},
        triggers={"new_conversations": True},
        field_mapping={},
        auto_import=True,
    )
    db.add(source)
    db.flush()
    return True


def _build_status_response(
    db: Session, org_id: int, row: IntercomIntegration
) -> IntercomStatusResponse:
    return IntercomStatusResponse(
        connected=True,
        workspace_id=row.workspace_id,
        workspace_name=row.workspace_name,
        token_hint=row.token_hint,
        admin_id=row.admin_id,
        has_client_secret=row.client_secret is not None,
        has_feedback_source=_has_intercom_source(db, org_id),
        last_synced_at=row.last_synced_at,
        last_sync_status=row.last_sync_status,
        last_error=row.last_error,
        feedback_items_ingested=_count_ingested_items(db, org_id),
        backlog_remaining=row.backlog_remaining,
        writeback_enabled=row.writeback_enabled,
        writeback_action=row.writeback_action,
        last_writeback_at=row.last_writeback_at,
        last_writeback_status=row.last_writeback_status,
        last_writeback_error=row.last_writeback_error,
    )


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.post(
    "/connect",
    response_model=IntercomConnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def intercom_connect(
    payload: IntercomConnectRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Connect or reconnect Intercom via a private-app Access Token.

    1. Rejects if the org already has an active OAuth Intercom connection.
    2. Validates the token against GET /me, deriving the workspace id.
    3. Rejects a workspace-less response -- a row with no discriminator can
       never match a feedback source, so failing loudly beats storing a
       connection that silently ingests nothing.
    4. Encrypts both secrets (422 if LLM_ENCRYPTION_KEY is unset).
    5. Upserts by organization_id; a reconnect that omits client_secret
       preserves the stored one.
    6. Auto-provisions a default `intercom` FeedbackSource with a seeded
       trigger.

    Neither secret is ever returned in the response or written to a log.
    """
    if _has_active_oauth_connection(db, current_org.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This organization already has an Intercom connection via OAuth. "
                "Disconnect it before connecting with an access token — only one "
                "Intercom connection per organization is supported."
            ),
        )

    client = IntercomClient(payload.access_token)
    try:
        try:
            info = client.validate()
        except IntercomAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Intercom access token is invalid or lacks required permissions.",
            ) from exc
        except IntercomTransientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Intercom API returned a transient error: {exc}",
            ) from exc
    finally:
        _close_client(client)

    workspace_id = info.get("workspace_id")
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Intercom did not return a workspace id for this token. Without it "
                "inbound events cannot be matched to this organization, so the "
                "connection was not saved."
            ),
        )

    try:
        encrypted_token = encrypt_api_key(payload.access_token)
        encrypted_secret = (
            encrypt_api_key(payload.client_secret) if payload.client_secret else None
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot store Intercom credentials: LLM_ENCRYPTION_KEY is not set. "
                "Set this environment variable and restart the service to connect "
                "an Intercom integration."
            ),
        ) from exc

    hint = get_key_hint(payload.access_token)
    existing = _get_org_integration(db, current_org.id)

    if existing:
        existing.access_token = encrypted_token
        # A reconnect that omits client_secret keeps the stored one rather than
        # silently clearing it (mirrors Zendesk's webhook_secret preservation).
        if encrypted_secret is not None:
            existing.client_secret = encrypted_secret
        existing.token_hint = hint
        existing.workspace_id = workspace_id
        existing.workspace_name = info.get("workspace_name")
        existing.admin_id = info.get("admin_id")
        existing.is_active = True
        existing.connected_by_user_id = current_user.id
        existing.connected_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        integration = existing
    else:
        integration = IntercomIntegration(
            organization_id=current_org.id,
            access_token=encrypted_token,
            client_secret=encrypted_secret,
            token_hint=hint,
            workspace_id=workspace_id,
            workspace_name=info.get("workspace_name"),
            admin_id=info.get("admin_id"),
            is_active=True,
            connected_by_user_id=current_user.id,
            connected_at=datetime.utcnow(),
        )
        db.add(integration)

    has_feedback_source = _ensure_default_feedback_source(
        db, current_org.id, workspace_id
    )

    db.commit()
    db.refresh(integration)

    logger.info(
        "Intercom connected for org %s (workspace %s)",
        current_org.id,
        integration.workspace_id,
    )
    return IntercomConnectResponse(
        connected=True,
        workspace_id=integration.workspace_id,
        workspace_name=integration.workspace_name,
        token_hint=integration.token_hint,
        admin_id=integration.admin_id,
        has_client_secret=integration.client_secret is not None,
        has_feedback_source=has_feedback_source,
    )


@router.get(
    "/status",
    response_model=IntercomStatusResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def intercom_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Connection status. Never returns the access token or client secret."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        return IntercomStatusResponse(connected=False)
    return _build_status_response(db, current_org.id, row)


@router.delete(
    "/disconnect",
    response_model=IntercomDisconnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def intercom_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Deactivate (soft-delete) the Intercom connection for this org.

    Connection and source lifecycle are intentionally decoupled, matching
    Zendesk: this does NOT touch the auto-provisioned FeedbackSource, so
    ingested history and the source's configuration survive a reconnect.
    """
    row = _get_org_integration(db, current_org.id)
    if row and row.is_active:
        row.is_active = False
        row.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Intercom disconnected for org %s", current_org.id)
    return IntercomDisconnectResponse(disconnected=True)


@router.patch(
    "/writeback",
    response_model=IntercomWritebackResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def intercom_configure_writeback(
    payload: IntercomWritebackRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Per-org write-back opt-in.

    Pure config write: enabling/disabling never calls Intercom, never
    enqueues a task, and never touches already-resolved items (no
    backfill-on-enable, prd.md OQ2). Writes only the token-paste
    IntercomIntegration row — the legacy OAuth row has no writeback
    columns, so an OAuth-only org gets a 409 rather than a silent
    write-nowhere.
    """
    row = _get_active_integration(db, current_org.id)
    if not row:
        if _has_active_oauth_connection(db, current_org.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This organization's Intercom connection uses the "
                    "legacy OAuth path, which cannot store write-back "
                    "configuration. Connect with an access token to "
                    "enable write-back."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Intercom integration found.",
        )

    if payload.action is not None:
        row.writeback_action = payload.action
    row.writeback_enabled = payload.enabled
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    logger.info(
        "Intercom write-back %s for org %s (action=%s)",
        "enabled" if payload.enabled else "disabled",
        current_org.id,
        row.writeback_action,
    )
    return IntercomWritebackResponse(
        writeback_enabled=row.writeback_enabled,
        writeback_action=row.writeback_action,
        last_writeback_at=row.last_writeback_at,
        last_writeback_status=row.last_writeback_status,
        last_writeback_error=row.last_writeback_error,
    )


@router.post(
    "/writeback/test",
    response_model=IntercomWritebackTestResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def intercom_writeback_test(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Live credential probe for the write-back path (S1).

    Checks exactly two things: the stored token still validates
    (GET /me) and an admin id resolves. It does NOT claim write scope:
    Intercom's /me does not report scopes, and the only honest live
    scope check would mutate, so `missing_write_scope` is reported only
    from recorded evidence on the row (a prior real write-back that
    failed with that status). A 200 {ok: true} therefore means "credible
    credential", not "scope confirmed". Never mutates anything and never
    dispatches a task.
    """
    row = _get_active_integration(db, current_org.id)
    if not row:
        if _has_active_oauth_connection(db, current_org.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This organization's Intercom connection uses the "
                    "legacy OAuth path, which cannot store write-back "
                    "configuration. Connect with an access token to "
                    "enable write-back."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Intercom integration found.",
        )

    if row.last_writeback_status == "missing_write_scope":
        return IntercomWritebackTestResponse(
            ok=False, reason="missing_write_scope"
        )

    try:
        plain_token = decrypt_api_key(row.access_token)
    except (ValueError, InvalidToken) as exc:
        logger.warning(
            "Intercom writeback probe: token decrypt failed for org %s: %s",
            current_org.id, exc,
        )
        return IntercomWritebackTestResponse(ok=False, reason="auth_error")

    client = IntercomClient(plain_token)
    try:
        try:
            info = client.validate()
        except IntercomAuthError:
            return IntercomWritebackTestResponse(ok=False, reason="auth_error")
        except IntercomTransientError:
            return IntercomWritebackTestResponse(
                ok=False, reason="transient_error"
            )
    finally:
        _close_client(client)

    if not info.get("admin_id"):
        return IntercomWritebackTestResponse(ok=False, reason="no_admin")
    return IntercomWritebackTestResponse(ok=True, reason=None)
