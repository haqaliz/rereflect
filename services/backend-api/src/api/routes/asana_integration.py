"""
Asana integration routes (backend-connection aspect, Phase 3;
backend-routes / inbound status-sync aspect).

Routes:
  POST   /api/v1/integrations/asana/connect      — validate + encrypt + store
  GET    /api/v1/integrations/asana/status       — connection + status-sync status (no token)
  DELETE /api/v1/integrations/asana/disconnect   — deactivate (soft; preserves
                                                     feedback_asana_tasks)
  POST   /api/v1/integrations/asana/test         — re-validate stored token
  GET    /api/v1/integrations/asana/workspaces   — list workspaces
  GET    /api/v1/integrations/asana/projects     — list projects in a workspace
  PATCH  /api/v1/integrations/asana/status-sync  — toggle inbound status sync + set mapping
  POST   /api/v1/integrations/asana/sync         — manually enqueue an inbound status-sync run

All endpoints require admin/owner role. Asana is a PAT-only integration
against a fixed host (https://app.asana.com/api/1.0) — there is no
site_url/email in the connect payload, and no SSRF DNS gate is needed
(unlike Jira/Zendesk which accept a per-org subdomain).

The api_token is Fernet-encrypted via encrypt_api_key and is NEVER returned
in any response body.

R6 safeguard: POST /connect catches ValueError from encrypt_api_key (raised
when LLM_ENCRYPTION_KEY is unset) and returns HTTP 422 — never a 500.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_admin_or_owner
from src.database.session import get_db
from src.models.asana_integration import AsanaIntegration, FeedbackAsanaTask
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.organization import Organization
from src.models.user import User
from src.services.asana_client import (
    AsanaAuthError,
    AsanaClient,
    AsanaTransientError,
)
from src.utils.encryption import decrypt_api_key, encrypt_api_key, get_key_hint

# Asana enforces a 255-character max on task `name` (matches Jira's summary cap).
ASANA_TASK_NAME_MAX_LEN = 255

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/asana", tags=["asana"])


# ──────────────────────── Pydantic schemas ────────────────────────────────────


class AsanaConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=1)


class AsanaConnectResponse(BaseModel):
    connected: bool
    token_hint: Optional[str] = None
    account_gid: Optional[str] = None
    display_name: Optional[str] = None
    # api_token is intentionally NEVER included


class AsanaStatusResponse(BaseModel):
    connected: bool
    token_hint: Optional[str] = None
    account_gid: Optional[str] = None
    display_name: Optional[str] = None
    is_active: Optional[bool] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    connected_at: Optional[datetime] = None
    # Inbound status-sync fields (operator control surface)
    status_sync_enabled: bool = False
    last_status_synced_at: Optional[datetime] = None
    # api_token is intentionally NEVER included


class AsanaStatusSyncUpdateRequest(BaseModel):
    enabled: bool
    status_mapping: Optional[Dict[str, str]] = None


class AsanaSyncTriggerResponse(BaseModel):
    status: str


class AsanaDisconnectResponse(BaseModel):
    success: bool
    message: str


class AsanaTestResponse(BaseModel):
    success: bool
    message: Optional[str] = None


class AsanaWorkspaceResponse(BaseModel):
    gid: Optional[str] = None
    name: Optional[str] = None


class AsanaProjectResponse(BaseModel):
    gid: Optional[str] = None
    name: Optional[str] = None


class AsanaCreateTaskRequest(BaseModel):
    feedback_id: int
    workspace_gid: str = Field(..., min_length=1)
    project_gid: str = Field(..., min_length=1)
    name: str
    notes: Optional[str] = None
    force: bool = False


class AsanaCreateTaskResponse(BaseModel):
    asana_task_gid: Optional[str] = None
    asana_task_url: Optional[str] = None
    asana_task_name: Optional[str] = None
    warning: Optional[str] = None
    existing_tasks: Optional[List[dict]] = None


class AsanaLinkedTaskResponse(BaseModel):
    id: int
    feedback_id: int
    asana_task_gid: str
    asana_task_url: str
    asana_task_name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────── Internal helpers ───────────────────────────────────


def _get_active_integration(db: Session, org_id: int) -> Optional[AsanaIntegration]:
    """Return the active Asana integration for an org, or None."""
    return (
        db.query(AsanaIntegration)
        .filter(
            AsanaIntegration.organization_id == org_id,
            AsanaIntegration.is_active.is_(True),
        )
        .first()
    )


def _require_active_integration(db: Session, org_id: int) -> AsanaIntegration:
    """Return the active Asana integration for an org, or raise 404."""
    row = _get_active_integration(db, org_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Asana integration found.",
        )
    return row


def _get_org_integration(db: Session, org_id: int) -> Optional[AsanaIntegration]:
    """Return the Asana integration row for an org regardless of is_active (for upsert/disconnect)."""
    return db.query(AsanaIntegration).filter(AsanaIntegration.organization_id == org_id).first()


# Category keys accepted from the Asana completion→category adapter (mapping source) and
# Rereflect workflow statuses (mapping target). Only `new`/`done` are meaningful for Asana;
# `indeterminate` is accepted for forward-compat/parity with Jira but is inert here.
VALID_ASANA_CATEGORIES = {"new", "indeterminate", "done"}
VALID_WORKFLOW_STATUSES = {"new", "in_review", "resolved", "closed"}


def _validate_status_mapping(mapping: Optional[Dict[str, str]]) -> None:
    """422 if any status_mapping key/value falls outside the valid sets."""
    if mapping is None:
        return
    for key, value in mapping.items():
        if key not in VALID_ASANA_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status_mapping key '{key}'. Must be one of "
                    f"{sorted(VALID_ASANA_CATEGORIES)}."
                ),
            )
        if value not in VALID_WORKFLOW_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status_mapping value '{value}' for key '{key}'. "
                    f"Must be one of {sorted(VALID_WORKFLOW_STATUSES)}."
                ),
            )


def _last_status_synced_at(db: Session, org_id: int) -> Optional[datetime]:
    """Max FeedbackAsanaTask.last_status_synced_at across the org's linked tasks, or None."""
    return (
        db.query(func.max(FeedbackAsanaTask.last_status_synced_at))
        .filter(FeedbackAsanaTask.organization_id == org_id)
        .scalar()
    )


def _build_status_response(db: Session, org_id: int, row: AsanaIntegration) -> AsanaStatusResponse:
    """Build the full AsanaStatusResponse (connection + status-sync fields) for an existing row."""
    return AsanaStatusResponse(
        connected=True,
        token_hint=row.token_hint,
        account_gid=row.account_gid,
        display_name=row.display_name,
        is_active=row.is_active,
        last_synced_at=row.last_synced_at,
        last_sync_status=row.last_sync_status,
        last_error=row.last_error,
        connected_at=row.connected_at,
        status_sync_enabled=bool(row.status_sync_enabled),
        last_status_synced_at=_last_status_synced_at(db, org_id),
    )


def _get_celery_app():
    """Lazy accessor for the Celery client app — injectable in tests (mirrors
    jira_integration.py's _get_celery_app)."""
    from src.background.celery_client import get_celery_app
    return get_celery_app()


def get_decrypted_token(integration: AsanaIntegration) -> str:
    """
    Decrypt and return the plaintext Asana PAT stored in integration.

    Exported for use by the backend-create-task aspect.
    Raises cryptography.fernet.InvalidToken on corruption — callers should
    handle this and treat it as a failed validation (never a 500).
    """
    return decrypt_api_key(integration.api_token)


def _close_client(asana_client: AsanaClient) -> None:
    """Best-effort close — never let a close failure mask the real error."""
    try:
        asana_client.close()
    except Exception:  # noqa: BLE001 — best-effort cleanup only
        pass


def _add_timeline_entry(
    db: Session,
    feedback_id: int,
    org_id: int,
    event_type: str,
    actor_id: Optional[int],
    metadata: dict,
) -> None:
    """Add a workflow event timeline entry for a feedback item (mirrors Jira's helper)."""
    event = FeedbackWorkflowEvent(
        feedback_id=feedback_id,
        organization_id=org_id,
        actor_id=actor_id,
        event_type=event_type,
        metadata_=metadata,
    )
    db.add(event)
    db.commit()


# ──────────────────────── Routes ─────────────────────────────────────────────


@router.post(
    "/connect",
    response_model=AsanaConnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_connect(
    payload: AsanaConnectRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect or reconnect Asana via a Personal Access Token (Bearer auth).

    1. Validates the token against Asana's /users/me endpoint (422 on auth
       failure, 502 on transient upstream errors).
    2. Encrypts with Fernet (422 if LLM_ENCRYPTION_KEY is unset — R6).
    3. Upserts the row by organization_id (reconnect rotates the token).
    4. Returns metadata only. api_token is NEVER included in the response.
    """
    asana_client = AsanaClient(payload.api_token)
    try:
        try:
            info = asana_client.validate()
        except AsanaAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Asana token is invalid or lacks required permissions.",
            ) from exc
        except AsanaTransientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Asana API returned a transient error: {exc}",
            ) from exc
    finally:
        _close_client(asana_client)

    try:
        encrypted = encrypt_api_key(payload.api_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot store Asana token: LLM_ENCRYPTION_KEY is not set. "
                "Set this environment variable and restart the service to "
                "connect an Asana integration."
            ),
        ) from exc

    hint = get_key_hint(payload.api_token)
    account_gid = info.get("gid")
    display_name = info.get("name")

    existing = _get_org_integration(db, current_org.id)
    if existing:
        existing.api_token = encrypted
        existing.token_hint = hint
        existing.account_gid = account_gid
        existing.display_name = display_name
        existing.is_active = True
        existing.connected_by_user_id = current_user.id
        existing.connected_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        integration = existing
    else:
        integration = AsanaIntegration(
            organization_id=current_org.id,
            api_token=encrypted,
            token_hint=hint,
            account_gid=account_gid,
            display_name=display_name,
            is_active=True,
            connected_by_user_id=current_user.id,
            connected_at=datetime.utcnow(),
        )
        db.add(integration)

    db.commit()
    db.refresh(integration)

    logger.info("Asana connected for org %s", current_org.id)
    return AsanaConnectResponse(
        connected=True,
        token_hint=integration.token_hint,
        account_gid=integration.account_gid,
        display_name=integration.display_name,
    )


@router.get(
    "/status",
    response_model=AsanaStatusResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return connection status (and inbound status-sync status). Never returns the api_token."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        return AsanaStatusResponse(connected=False)
    return _build_status_response(db, current_org.id, row)


@router.delete(
    "/disconnect",
    response_model=AsanaDisconnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Deactivate (soft-delete) the Asana integration for this org.

    Preserves feedback_asana_tasks rows.
    """
    row = _get_org_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Asana integration found.",
        )
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()

    return AsanaDisconnectResponse(
        success=True,
        message="Asana integration disconnected.",
    )


@router.post(
    "/test",
    response_model=AsanaTestResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_test(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Re-validate the stored Asana token.

    Returns {"success": true/false, "message": "..."}.
    Never raises a 500 — all errors (decrypt failure, auth failure,
    transient upstream errors, network errors) are surfaced as
    {"success": false}.
    """
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Asana integration.",
        )
    try:
        plain_token = get_decrypted_token(row)
        asana_client = AsanaClient(plain_token)
        try:
            asana_client.validate()
        finally:
            _close_client(asana_client)
        return AsanaTestResponse(success=True, message="Asana connection is healthy.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — must never surface as a 500
        logger.warning("Asana test failed for org %s: %s", current_org.id, exc)
        return AsanaTestResponse(success=False, message=str(exc))


# ────────────────────── Inbound status-sync operator controls ─────────────────


@router.patch(
    "/status-sync",
    response_model=AsanaStatusResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_update_status_sync(
    payload: AsanaStatusSyncUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Toggle inbound Asana status sync and/or update the status_mapping override.

    404 if the org has no Asana integration row at all (connected or not — the
    setting is persisted on the integration row, so one must exist first).
    422 if status_mapping contains a key outside {new, indeterminate, done}
    or a value outside {new, in_review, resolved, closed}.
    """
    row = _get_org_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Asana integration found. Connect Asana first.",
        )

    _validate_status_mapping(payload.status_mapping)

    row.status_sync_enabled = payload.enabled
    if payload.status_mapping is not None:
        row.status_mapping = payload.status_mapping
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    logger.info(
        "Asana status-sync updated for org %s (enabled=%s)",
        current_org.id,
        row.status_sync_enabled,
    )
    return _build_status_response(db, current_org.id, row)


@router.post(
    "/sync",
    response_model=AsanaSyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_trigger_sync(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Manually enqueue an inbound Asana status-sync run for this org.

    Requires an ACTIVE Asana integration (400 if none — mirrors /test and the
    create-task aspect's active-integration guard). Enqueues
    sync_asana_org via Celery send_task (non-blocking). Never surfaces a 500 —
    a broker/dispatch failure is reported as a clean 502.
    """
    integ = _get_active_integration(db, current_org.id)
    if not integ:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Asana integration.",
        )

    try:
        _get_celery_app().send_task(
            "src.tasks.asana_sync.sync_asana_org",
            args=[integ.id],
        )
    except Exception as exc:  # noqa: BLE001 — must never surface as a 500
        logger.error(
            "Asana status sync could not be enqueued for org %s (integration_id=%s): %s",
            current_org.id,
            integ.id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Asana status sync could not be enqueued. Please try again shortly.",
        ) from exc

    logger.info(
        "Asana status sync manually triggered for org %s (integration_id=%s)",
        current_org.id,
        integ.id,
    )
    return AsanaSyncTriggerResponse(status="queued")


@router.get(
    "/workspaces",
    response_model=List[AsanaWorkspaceResponse],
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_get_workspaces(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Proxy `AsanaClient.get_workspaces()` for the connected Asana account."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Asana integration. Connect Asana first via /integrations/asana/connect.",
        )
    plain_token = get_decrypted_token(row)
    asana_client = AsanaClient(plain_token)
    try:
        return asana_client.get_workspaces()
    except AsanaAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Asana token is invalid or lacks required permissions. Reconnect Asana.",
        ) from exc
    except AsanaTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Asana API returned a transient error: {exc}",
        ) from exc
    finally:
        _close_client(asana_client)


@router.get(
    "/projects",
    response_model=List[AsanaProjectResponse],
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_get_projects(
    workspace_gid: str = Query(..., description="Asana workspace gid"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Proxy `AsanaClient.get_projects(workspace_gid)` for the connected Asana account."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Asana integration. Connect Asana first via /integrations/asana/connect.",
        )
    plain_token = get_decrypted_token(row)
    asana_client = AsanaClient(plain_token)
    try:
        return asana_client.get_projects(workspace_gid)
    except AsanaAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Asana token is invalid or lacks required permissions. Reconnect Asana.",
        ) from exc
    except AsanaTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Asana API returned a transient error: {exc}",
        ) from exc
    finally:
        _close_client(asana_client)


# ──────────────────────────── Create-task aspect ─────────────────────────────
# POST /tasks, GET /tasks
# (backend-create-task aspect — mirrors Jira's create_issue route)


@router.post(
    "/tasks",
    response_model=AsanaCreateTaskResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_create_task(
    payload: AsanaCreateTaskRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create an Asana task from a feedback item.

    1. verify the feedback belongs to the caller's org (404 if not);
    2. duplicate check — if a FeedbackAsanaTask already links this feedback
       and `force` is not set, return 200 with `{warning: "duplicate", ...}`
       (mirrors Jira's create_issue) with NO second Asana call;
    3. trim `name` to Asana's max length, call `create_task(...)`;
    4. stale-token handling: AsanaAuthError -> 403 (never 500) + set
       last_error/last_sync_status on the integration; AsanaTransientError -> 502;
    5. persist a FeedbackAsanaTask row + an asana_task_created timeline event;
    6. return {asana_task_gid, asana_task_url, asana_task_name}.
    """
    integration = _require_active_integration(db, current_org.id)

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name must not be empty.",
        )
    name = name[:ASANA_TASK_NAME_MAX_LEN]

    feedback = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == payload.feedback_id,
            FeedbackItem.organization_id == current_org.id,
        )
        .first()
    )
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback item {payload.feedback_id} not found.",
        )

    existing_links = (
        db.query(FeedbackAsanaTask)
        .filter(
            FeedbackAsanaTask.feedback_id == payload.feedback_id,
            FeedbackAsanaTask.organization_id == current_org.id,
        )
        .all()
    )
    if existing_links and not payload.force:
        return JSONResponse(
            status_code=200,
            content={
                "warning": "duplicate",
                "existing_tasks": [
                    {
                        "id": link.id,
                        "asana_task_gid": link.asana_task_gid,
                        "asana_task_url": link.asana_task_url,
                        "asana_task_name": link.asana_task_name,
                    }
                    for link in existing_links
                ],
            },
        )

    plain_token = get_decrypted_token(integration)
    asana_client = AsanaClient(plain_token)
    try:
        created_task = asana_client.create_task({
            "name": name,
            "notes": payload.notes or "",
            "project_gid": payload.project_gid,
            "workspace_gid": payload.workspace_gid,
        })
    except AsanaAuthError as exc:
        integration.last_sync_status = "error"
        integration.last_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Asana token is invalid or lacks required project permissions. "
                "Reconnect Asana or check project permissions."
            ),
        ) from exc
    except AsanaTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Asana API returned a transient error: {exc}",
        ) from exc
    finally:
        _close_client(asana_client)

    link = FeedbackAsanaTask(
        organization_id=current_org.id,
        feedback_id=payload.feedback_id,
        asana_task_gid=str(created_task["gid"]),
        asana_task_url=created_task["url"],
        asana_task_name=name,
        created_by_user_id=current_user.id,
    )
    db.add(link)
    db.flush()

    _add_timeline_entry(
        db=db,
        feedback_id=payload.feedback_id,
        org_id=current_org.id,
        event_type="asana_task_created",
        actor_id=current_user.id,
        metadata={
            "asana_task_gid": link.asana_task_gid,
            "asana_task_url": link.asana_task_url,
            "asana_task_name": name,
            "created_by": current_user.email,
        },
    )

    db.commit()
    db.refresh(link)

    logger.info(
        "Created Asana task %s for feedback %s", link.asana_task_gid, payload.feedback_id
    )

    return AsanaCreateTaskResponse(
        asana_task_gid=link.asana_task_gid,
        asana_task_url=link.asana_task_url,
        asana_task_name=link.asana_task_name,
    )


@router.get(
    "/tasks",
    response_model=List[AsanaLinkedTaskResponse],
    dependencies=[Depends(require_admin_or_owner)],
)
def asana_get_linked_tasks(
    feedback_id: int = Query(..., description="Feedback item ID"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all Asana tasks linked to a feedback item (for the wizard duplicate warning)."""
    links = (
        db.query(FeedbackAsanaTask)
        .filter(
            FeedbackAsanaTask.feedback_id == feedback_id,
            FeedbackAsanaTask.organization_id == current_org.id,
        )
        .order_by(FeedbackAsanaTask.created_at.desc())
        .all()
    )
    return links
