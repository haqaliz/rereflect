"""
Jira Cloud integration routes (backend-connection aspect, Phase 3).

Routes:
  POST   /api/v1/integrations/jira/connect      — validate + encrypt + store
  GET    /api/v1/integrations/jira/status       — connection + status-sync status (no token)
  DELETE /api/v1/integrations/jira/disconnect   — deactivate (soft; preserves
                                                    feedback_jira_issues)
  POST   /api/v1/integrations/jira/test         — re-validate stored token
  PATCH  /api/v1/integrations/jira/status-sync  — toggle inbound status sync + set mapping
  POST   /api/v1/integrations/jira/sync         — manually enqueue an inbound status-sync run

All endpoints require admin/owner role. Jira is NOT a CRM — disconnect does
NOT call crm_integration_common.another_crm_active / purge_crm_enrichment.

The api_token is Fernet-encrypted via encrypt_api_key and is NEVER returned
in any response body.

R6 safeguard: POST /connect catches ValueError from encrypt_api_key (raised
when LLM_ENCRYPTION_KEY is unset) and returns HTTP 422 — never a 500.

SSRF gate: after normalizing site_url, the host is resolved via
socket.getaddrinfo and rejected if any resolved address is loopback,
RFC1918-private, or link-local. This is the primary SSRF gate on untrusted
operator input; JiraClient re-asserts scheme + host-suffix as defense in
depth (see src/services/jira_client.py::_assert_safe_site_url).
"""
import ipaddress
import logging
import socket
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_admin_or_owner
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.jira_integration import FeedbackJiraIssue, JiraIntegration
from src.models.organization import Organization
from src.models.user import User
from src.services.jira_client import (
    JiraAuthError,
    JiraClient,
    JiraTransientError,
    text_to_adf,
)
from src.utils.encryption import decrypt_api_key, encrypt_api_key, get_key_hint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/jira", tags=["jira"])


# ──────────────────────── Pydantic schemas ────────────────────────────────────


class JiraConnectRequest(BaseModel):
    site_url: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    api_token: str = Field(..., min_length=1)


class JiraConnectResponse(BaseModel):
    connected: bool
    site_url: Optional[str] = None
    email: Optional[str] = None
    token_hint: Optional[str] = None
    account_id: Optional[str] = None
    display_name: Optional[str] = None
    # api_token is intentionally NEVER included


class JiraStatusResponse(BaseModel):
    connected: bool
    site_url: Optional[str] = None
    email: Optional[str] = None
    token_hint: Optional[str] = None
    account_id: Optional[str] = None
    display_name: Optional[str] = None
    is_active: Optional[bool] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    connected_at: Optional[datetime] = None
    # Inbound status-sync fields (Phase 5 — operator control surface)
    status_sync_enabled: bool = False
    last_status_synced_at: Optional[datetime] = None
    # api_token is intentionally NEVER included


class JiraStatusSyncUpdateRequest(BaseModel):
    enabled: bool
    status_mapping: Optional[Dict[str, str]] = None


class JiraSyncTriggerResponse(BaseModel):
    status: str


class JiraDisconnectResponse(BaseModel):
    success: bool
    message: str


class JiraTestResponse(BaseModel):
    success: bool
    message: Optional[str] = None


class JiraProjectResponse(BaseModel):
    id: str
    key: Optional[str] = None
    name: Optional[str] = None


class JiraIssueTypeResponse(BaseModel):
    id: str
    name: Optional[str] = None


class JiraCreateIssueRequest(BaseModel):
    feedback_id: int
    project_id: str = Field(..., min_length=1)
    issue_type_id: str = Field(..., min_length=1)
    summary: str
    description: Optional[str] = None
    force: bool = False


class JiraCreateIssueResponse(BaseModel):
    jira_issue_id: str
    jira_issue_key: str
    jira_issue_url: str
    jira_issue_title: str


class JiraLinkedIssueResponse(BaseModel):
    id: int
    feedback_id: int
    jira_issue_id: str
    jira_issue_key: str
    jira_issue_url: str
    jira_issue_title: str
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────── Internal helpers ───────────────────────────────────


def _normalize_site_url(raw: str) -> str:
    """
    Normalize a user-supplied Jira site URL to the canonical
    `https://{site}.atlassian.net` form.

    Accepts: `acme`, `acme.atlassian.net`, `https://acme.atlassian.net`,
    `https://acme.atlassian.net/` (trailing slash). Rejects any host that
    doesn't resolve to a `*.atlassian.net` host (Cloud-only slice).
    """
    value = (raw or "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="site_url is required.",
        )

    if "://" in value:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
    else:
        host = value.rstrip("/").lower()

    if host and "." not in host:
        # Bare subdomain, e.g. "acme" -> "acme.atlassian.net"
        host = f"{host}.atlassian.net"

    if not host or not host.endswith(".atlassian.net"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="site_url must be a *.atlassian.net host (Jira Cloud only).",
        )

    return f"https://{host}"


def _assert_host_not_ssrf(host: str) -> None:
    """
    Resolve `host` and reject it if any resolved address is loopback,
    RFC1918-private, or link-local (SSRF gate — MEDIUM finding).

    This is the primary gate: it runs on untrusted operator input (a
    `*.atlassian.net` host whose DNS could be pointed at
    169.254.169.254 / internal ranges).
    """
    try:
        infos = socket.getaddrinfo(host, 443)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not resolve site_url host: {exc}",
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
                detail="site_url resolves to a disallowed address.",
            )


# Valid Jira statusCategory keys (mapping source) and Rereflect workflow
# statuses (mapping target) for the inbound status-sync feature.
VALID_JIRA_CATEGORIES = {"new", "indeterminate", "done"}
VALID_WORKFLOW_STATUSES = {"new", "in_review", "resolved", "closed"}


def _validate_status_mapping(mapping: Optional[Dict[str, str]]) -> None:
    """422 if any status_mapping key/value falls outside the valid sets."""
    if mapping is None:
        return
    for key, value in mapping.items():
        if key not in VALID_JIRA_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status_mapping key '{key}'. Must be one of "
                    f"{sorted(VALID_JIRA_CATEGORIES)}."
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
    """Max FeedbackJiraIssue.last_status_synced_at across the org's linked issues, or None."""
    return (
        db.query(func.max(FeedbackJiraIssue.last_status_synced_at))
        .filter(FeedbackJiraIssue.organization_id == org_id)
        .scalar()
    )


def _build_status_response(db: Session, org_id: int, row: JiraIntegration) -> JiraStatusResponse:
    """Build the full JiraStatusResponse (connection + status-sync fields) for an existing row."""
    return JiraStatusResponse(
        connected=True,
        site_url=row.site_url,
        email=row.email,
        token_hint=row.token_hint,
        account_id=row.account_id,
        display_name=row.display_name,
        is_active=row.is_active,
        last_synced_at=row.last_synced_at,
        last_sync_status=row.last_sync_status,
        last_error=row.last_error,
        connected_at=row.connected_at,
        status_sync_enabled=bool(row.status_sync_enabled),
        last_status_synced_at=_last_status_synced_at(db, org_id),
    )


def _get_active_integration(db: Session, org_id: int) -> Optional[JiraIntegration]:
    """Return the active Jira integration for an org, or None."""
    return (
        db.query(JiraIntegration)
        .filter(
            JiraIntegration.organization_id == org_id,
            JiraIntegration.is_active.is_(True),
        )
        .first()
    )


def _require_active_integration(db: Session, org_id: int) -> JiraIntegration:
    """Return the active Jira integration for an org, or raise 404."""
    row = _get_active_integration(db, org_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Jira integration found.",
        )
    return row


def _get_org_integration(db: Session, org_id: int) -> Optional[JiraIntegration]:
    """Return the Jira integration row for an org regardless of is_active (for upsert/disconnect)."""
    return db.query(JiraIntegration).filter(JiraIntegration.organization_id == org_id).first()


def get_decrypted_token(integration: JiraIntegration) -> str:
    """
    Decrypt and return the plaintext Jira API token stored in integration.

    Exported for use by the backend-create-issue aspect.
    Raises cryptography.fernet.InvalidToken on corruption — callers should
    handle this and treat it as a failed validation (never a 500).
    """
    return decrypt_api_key(integration.api_token)


def _close_client(jira_client: JiraClient) -> None:
    """Best-effort close — never let a close failure mask the real error."""
    try:
        jira_client.close()
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
    """Add a workflow event timeline entry for a feedback item (mirrors Linear's helper)."""
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
    response_model=JiraConnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_connect(
    payload: JiraConnectRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect or reconnect a Jira Cloud site via email + API token (Basic auth).

    1. Normalizes site_url to the canonical https://{site}.atlassian.net form
       (422 if not a *.atlassian.net host).
    2. Resolves the host and rejects loopback/private/link-local addresses
       (SSRF gate, 422).
    3. Validates the token against Jira's /myself endpoint (422 on auth
       failure, 502 on transient upstream errors).
    4. Encrypts with Fernet (422 if LLM_ENCRYPTION_KEY is unset — R6).
    5. Upserts the row by organization_id (reconnect rotates the token).
    6. Returns metadata only. api_token is NEVER included in the response.
    """
    site_url = _normalize_site_url(payload.site_url)
    host = urlparse(site_url).hostname or ""
    _assert_host_not_ssrf(host)

    jira_client = JiraClient(site_url, payload.email, payload.api_token)
    try:
        try:
            info = jira_client.validate()
        except JiraAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Jira token is invalid or lacks required permissions.",
            ) from exc
        except JiraTransientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Jira API returned a transient error: {exc}",
            ) from exc
    finally:
        _close_client(jira_client)

    try:
        encrypted = encrypt_api_key(payload.api_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot store Jira token: LLM_ENCRYPTION_KEY is not set. "
                "Set this environment variable and restart the service to "
                "connect a Jira integration."
            ),
        ) from exc

    hint = get_key_hint(payload.api_token)
    account_id = info.get("account_id")
    display_name = info.get("display_name")

    existing = _get_org_integration(db, current_org.id)
    if existing:
        existing.site_url = site_url
        existing.email = payload.email
        existing.api_token = encrypted
        existing.token_hint = hint
        existing.account_id = account_id
        existing.display_name = display_name
        existing.is_active = True
        existing.connected_by_user_id = current_user.id
        existing.connected_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        integration = existing
    else:
        integration = JiraIntegration(
            organization_id=current_org.id,
            site_url=site_url,
            email=payload.email,
            api_token=encrypted,
            token_hint=hint,
            account_id=account_id,
            display_name=display_name,
            is_active=True,
            connected_by_user_id=current_user.id,
            connected_at=datetime.utcnow(),
        )
        db.add(integration)

    db.commit()
    db.refresh(integration)

    logger.info(
        "Jira connected for org %s (site %s)", current_org.id, integration.site_url
    )
    return JiraConnectResponse(
        connected=True,
        site_url=integration.site_url,
        email=integration.email,
        token_hint=integration.token_hint,
        account_id=integration.account_id,
        display_name=integration.display_name,
    )


@router.get(
    "/status",
    response_model=JiraStatusResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return connection status (and inbound status-sync status). Never returns the api_token."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        return JiraStatusResponse(connected=False)
    return _build_status_response(db, current_org.id, row)


@router.delete(
    "/disconnect",
    response_model=JiraDisconnectResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Deactivate (soft-delete) the Jira integration for this org.

    Preserves feedback_jira_issues rows. Jira is not a CRM — this must NOT
    call crm_integration_common.purge_crm_enrichment or any CRM purge path.
    """
    row = _get_org_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Jira integration found.",
        )
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()

    return JiraDisconnectResponse(
        success=True,
        message="Jira integration disconnected.",
    )


@router.post(
    "/test",
    response_model=JiraTestResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_test(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Re-validate the stored Jira token.

    Returns {"success": true/false, "message": "..."}.
    Never raises a 500 — all errors (decrypt failure, auth failure,
    transient upstream errors, network errors) are surfaced as
    {"success": false}.
    """
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Jira integration.",
        )
    try:
        plain_token = get_decrypted_token(row)
        jira_client = JiraClient(row.site_url, row.email, plain_token)
        try:
            jira_client.validate()
        finally:
            _close_client(jira_client)
        return JiraTestResponse(success=True, message="Jira connection is healthy.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — must never surface as a 500
        logger.warning("Jira test failed for org %s: %s", current_org.id, exc)
        return JiraTestResponse(success=False, message=str(exc))


# ────────────────────── Inbound status-sync operator controls ─────────────────


@router.patch(
    "/status-sync",
    response_model=JiraStatusResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_update_status_sync(
    payload: JiraStatusSyncUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Toggle inbound Jira status sync and/or update the status_mapping override.

    404 if the org has no Jira integration row at all (connected or not — the
    setting is persisted on the integration row, so one must exist first).
    422 if status_mapping contains a key outside {new, indeterminate, done}
    or a value outside {new, in_review, resolved, closed}.
    """
    row = _get_org_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Jira integration found. Connect Jira first.",
        )

    _validate_status_mapping(payload.status_mapping)

    row.status_sync_enabled = payload.enabled
    if payload.status_mapping is not None:
        row.status_mapping = payload.status_mapping
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    logger.info(
        "Jira status-sync updated for org %s (enabled=%s)",
        current_org.id,
        row.status_sync_enabled,
    )
    return _build_status_response(db, current_org.id, row)


def _get_celery_app():
    """Lazy accessor for the Celery client app — injectable in tests (mirrors
    zendesk_integration.py's _get_celery_app)."""
    from src.background.celery_client import get_celery_app
    return get_celery_app()


@router.post(
    "/sync",
    response_model=JiraSyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_trigger_sync(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Manually enqueue an inbound Jira status-sync run for this org.

    Requires an ACTIVE Jira integration (400 if none — mirrors /test and the
    create-issue aspect's active-integration guard). Enqueues
    sync_jira_org via Celery send_task (non-blocking). Never surfaces a 500 —
    a broker/dispatch failure is reported as a clean 502.
    """
    integ = _get_active_integration(db, current_org.id)
    if not integ:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Jira integration.",
        )

    try:
        _get_celery_app().send_task(
            "src.tasks.jira_sync.sync_jira_org",
            args=[integ.id],
        )
    except Exception as exc:  # noqa: BLE001 — must never surface as a 500
        logger.error(
            "Jira status sync could not be enqueued for org %s (integration_id=%s): %s",
            current_org.id,
            integ.id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Jira status sync could not be enqueued. Please try again shortly.",
        ) from exc

    logger.info(
        "Jira status sync manually triggered for org %s (integration_id=%s)",
        current_org.id,
        integ.id,
    )
    return JiraSyncTriggerResponse(status="queued")


# ──────────────────────────── Create-issue aspect ─────────────────────────────
# GET /projects, GET /issuetypes, POST /issues, GET /issues
# (backend-create-issue aspect — mirrors Linear's create_linear_issue route)


@router.get(
    "/projects",
    response_model=List[JiraProjectResponse],
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_get_projects(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Proxy `JiraClient.get_projects()` for the connected Jira site."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Jira integration. Connect Jira first via /integrations/jira/connect.",
        )
    plain_token = get_decrypted_token(row)
    jira_client = JiraClient(row.site_url, row.email, plain_token)
    try:
        return jira_client.get_projects()
    except JiraAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jira token is invalid or lacks required permissions. Reconnect Jira.",
        ) from exc
    except JiraTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira API returned a transient error: {exc}",
        ) from exc
    finally:
        _close_client(jira_client)


@router.get(
    "/issuetypes",
    response_model=List[JiraIssueTypeResponse],
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_get_issue_types(
    project_id: str = Query(..., description="Jira project id"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Proxy `JiraClient.get_issue_types(project_id)` for the connected Jira site."""
    row = _get_active_integration(db, current_org.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Jira integration. Connect Jira first via /integrations/jira/connect.",
        )
    plain_token = get_decrypted_token(row)
    jira_client = JiraClient(row.site_url, row.email, plain_token)
    try:
        return jira_client.get_issue_types(project_id)
    except JiraAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jira token is invalid or lacks required permissions. Reconnect Jira.",
        ) from exc
    except JiraTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira API returned a transient error: {exc}",
        ) from exc
    finally:
        _close_client(jira_client)


@router.post(
    "/issues",
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_create_issue(
    payload: JiraCreateIssueRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Jira issue from a feedback item.

    1. verify the feedback belongs to the caller's org (404 if not);
    2. duplicate check — if a FeedbackJiraIssue already links this feedback
       and `force` is not set, return 200 with `{warning: "duplicate", ...}`
       (mirrors Linear's create_linear_issue);
    3. validate + trim summary, build the ADF description, call
       `create_issue(...)`;
    4. stale-token handling: JiraAuthError -> 403 (never 500) + set
       last_error/last_sync_status on the integration; JiraTransientError -> 502;
    5. persist a FeedbackJiraIssue row + a jira_issue_created timeline event;
    6. return {jira_issue_id, jira_issue_key, jira_issue_url, jira_issue_title}.
    """
    integration = _require_active_integration(db, current_org.id)

    summary = (payload.summary or "").strip()
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="summary must not be empty.",
        )
    summary = summary[:255]

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
        db.query(FeedbackJiraIssue)
        .filter(
            FeedbackJiraIssue.feedback_id == payload.feedback_id,
            FeedbackJiraIssue.organization_id == current_org.id,
        )
        .all()
    )
    if existing_links and not payload.force:
        return JSONResponse(
            status_code=200,
            content={
                "warning": "duplicate",
                "existing_issues": [
                    {
                        "id": link.id,
                        "jira_issue_key": link.jira_issue_key,
                        "jira_issue_url": link.jira_issue_url,
                        "jira_issue_title": link.jira_issue_title,
                    }
                    for link in existing_links
                ],
            },
        )

    description_adf = text_to_adf(payload.description)

    plain_token = get_decrypted_token(integration)
    jira_client = JiraClient(integration.site_url, integration.email, plain_token)
    try:
        created_issue = jira_client.create_issue({
            "project_id": payload.project_id,
            "issue_type_id": payload.issue_type_id,
            "summary": summary,
            "description_adf": description_adf,
        })
    except JiraAuthError as exc:
        integration.last_sync_status = "error"
        integration.last_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Jira token is invalid or lacks required project permissions. "
                "Reconnect Jira or check project permissions."
            ),
        ) from exc
    except JiraTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira API returned a transient error: {exc}",
        ) from exc
    finally:
        _close_client(jira_client)

    link = FeedbackJiraIssue(
        organization_id=current_org.id,
        feedback_id=payload.feedback_id,
        jira_issue_id=str(created_issue["id"]),
        jira_issue_key=created_issue["key"],
        jira_issue_url=created_issue["url"],
        jira_issue_title=summary,
        created_by_user_id=current_user.id,
    )
    db.add(link)
    db.flush()

    _add_timeline_entry(
        db=db,
        feedback_id=payload.feedback_id,
        org_id=current_org.id,
        event_type="jira_issue_created",
        actor_id=current_user.id,
        metadata={
            "jira_issue_key": created_issue["key"],
            "jira_issue_url": created_issue["url"],
            "jira_issue_title": summary,
            "created_by": current_user.email,
        },
    )

    db.commit()
    db.refresh(link)

    logger.info(
        "Created Jira issue %s for feedback %s", created_issue["key"], payload.feedback_id
    )

    return JiraCreateIssueResponse(
        jira_issue_id=link.jira_issue_id,
        jira_issue_key=link.jira_issue_key,
        jira_issue_url=link.jira_issue_url,
        jira_issue_title=link.jira_issue_title,
    )


@router.get(
    "/issues",
    response_model=List[JiraLinkedIssueResponse],
    dependencies=[Depends(require_admin_or_owner)],
)
def jira_get_linked_issues(
    feedback_id: int = Query(..., description="Feedback item ID"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all Jira issues linked to a feedback item (for the wizard duplicate warning)."""
    links = (
        db.query(FeedbackJiraIssue)
        .filter(
            FeedbackJiraIssue.feedback_id == feedback_id,
            FeedbackJiraIssue.organization_id == current_org.id,
        )
        .order_by(FeedbackJiraIssue.created_at.desc())
        .all()
    )
    return links
