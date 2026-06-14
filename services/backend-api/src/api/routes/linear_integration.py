"""
Linear integration API routes.
Covers: OAuth flow, issue creation, configuration endpoints (team/status mappings),
        and proxy endpoints to the Linear API (teams, projects, labels).
"""

import hashlib
import hmac
import logging
import os
import secrets
import urllib.parse
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_feature
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.linear_integration import (
    FeedbackLinearIssue,
    LinearIntegration,
    LinearStatusMapping,
    LinearTeamMapping,
)
from src.models.organization import Organization
from src.models.user import User
from src.services.linear_client import LinearClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/linear", tags=["linear"])

# Linear OAuth Configuration
LINEAR_CLIENT_ID = os.environ.get("LINEAR_CLIENT_ID", "")
LINEAR_CLIENT_SECRET = os.environ.get("LINEAR_CLIENT_SECRET", "")
LINEAR_REDIRECT_URI = os.environ.get(
    "LINEAR_REDIRECT_URI",
    "http://localhost:8000/api/v1/integrations/linear/callback",
)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# In-memory OAuth state (use Redis with TTL in production)
linear_oauth_states: dict = {}

# Default status mappings applied on first connect
DEFAULT_STATUS_MAPPINGS = [
    {"linear_status_name": "Backlog", "linear_status_type": "backlog", "rereflect_status": "new"},
    {"linear_status_name": "Todo", "linear_status_type": "unstarted", "rereflect_status": "new"},
    {"linear_status_name": "In Progress", "linear_status_type": "started", "rereflect_status": "in_review"},
    {"linear_status_name": "Done", "linear_status_type": "completed", "rereflect_status": "resolved"},
    {"linear_status_name": "Canceled", "linear_status_type": "canceled", "rereflect_status": "closed"},
]

VALID_REREFLECT_STATUSES = {"new", "in_review", "resolved", "closed"}


# ============================================================================
# Pydantic Schemas
# ============================================================================

class LinearConnectResponse(BaseModel):
    auth_url: str
    state: str


class LinearStatusResponse(BaseModel):
    connected: bool
    org_name: Optional[str] = None
    org_id: Optional[str] = None
    connected_by_email: Optional[str] = None
    connected_at: Optional[datetime] = None
    is_active: bool = False


class LinearDisconnectResponse(BaseModel):
    success: bool
    message: str


class LinearConfigResponse(BaseModel):
    issue_title_template: Optional[str] = None
    issue_description_template: Optional[str] = None


class LinearConfigUpdateRequest(BaseModel):
    issue_title_template: Optional[str] = None
    issue_description_template: Optional[str] = None


class CreateIssueRequest(BaseModel):
    feedback_id: int
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None  # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    label_ids: Optional[List[str]] = None
    force: bool = False  # Force create even if duplicate exists


class LinkedIssueResponse(BaseModel):
    id: int
    feedback_id: int
    linear_issue_id: str
    linear_issue_identifier: str
    linear_issue_url: str
    linear_issue_title: str
    linear_status: Optional[str] = None
    linear_assignee: Optional[str] = None
    linear_priority: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TeamMappingItem(BaseModel):
    rereflect_category: str
    linear_team_id: str
    linear_team_name: str
    linear_project_id: Optional[str] = None
    linear_project_name: Optional[str] = None
    priority: int = 1


class TeamMappingResponse(TeamMappingItem):
    id: int
    organization_id: int

    class Config:
        from_attributes = True


class StatusMappingItem(BaseModel):
    linear_status_name: str
    linear_status_type: str
    rereflect_status: str

    @field_validator("rereflect_status")
    @classmethod
    def validate_rereflect_status(cls, v: str) -> str:
        if v not in VALID_REREFLECT_STATUSES:
            raise ValueError(
                f"Invalid rereflect_status '{v}'. Must be one of: {sorted(VALID_REREFLECT_STATUSES)}"
            )
        return v


class StatusMappingResponse(StatusMappingItem):
    id: int
    organization_id: int

    class Config:
        from_attributes = True


# ============================================================================
# Helper Functions
# ============================================================================

def _get_active_integration(org_id: int, db: Session) -> Optional[LinearIntegration]:
    """Return the active LinearIntegration for this org, or None."""
    return (
        db.query(LinearIntegration)
        .filter(
            LinearIntegration.organization_id == org_id,
            LinearIntegration.is_active.is_(True),
        )
        .first()
    )


def _require_active_integration(org_id: int, db: Session) -> LinearIntegration:
    """Return active integration or raise 400."""
    integration = _get_active_integration(org_id, db)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Linear integration. Connect Linear first via /integrations/linear/connect.",
        )
    return integration


async def generate_linear_issue_content(feedback_data: dict, org_id: int, db=None) -> dict:
    """
    Generate AI-crafted issue title and description from feedback data.
    Falls back to basic content if AI is unavailable.
    """
    try:
        result = await call_ai_for_linear_issue(feedback_data=feedback_data, org_id=org_id, db=db)
        # Enforce max title length
        if len(result.get("title", "")) > 80:
            result["title"] = result["title"][:77] + "..."
        return result
    except Exception as exc:
        logger.warning(f"AI issue generation failed: {exc}. Falling back to basic content.")
        text = feedback_data.get("text", "Customer feedback")
        title = text[:77] + "..." if len(text) > 80 else text
        description = f"## Customer Feedback\n\n{text}\n\n*Sentiment:* {feedback_data.get('sentiment_label', 'unknown')}"
        return {"title": title, "description": description}


async def call_ai_for_linear_issue(feedback_data: dict, org_id: int, db=None) -> dict:
    """
    Call the configured LLM to generate a Linear issue title + description.
    Uses the org's BYOK OpenAI key; raises if absent so the caller falls back.
    """
    import json

    import httpx

    # A4: resolve BYOK key — no system/env key fallback
    from src.utils.byok import resolve_org_byok_key
    openai_api_key = resolve_org_byok_key("openai", org_id, db)
    if not openai_api_key:
        raise RuntimeError(
            "No OpenAI API key configured. "
            "Please add your key in Settings → AI → API Keys."
        )

    system_prompt = (
        "You are a product manager writing a Linear issue from customer feedback data.\n"
        "Generate a clear, actionable issue title and description.\n\n"
        "The description should include:\n"
        "1. A 2-3 sentence summary of the problem/request\n"
        "2. Customer impact (sentiment, urgency level)\n"
        "3. Original customer quote (as a blockquote)\n\n"
        "Keep the title under 80 characters. Be specific and actionable.\n"
        "Do not use marketing language. Write for engineers.\n\n"
        'Respond with valid JSON only: {"title": "...", "description": "..."}'
    )

    user_message = (
        f"Feedback text: {feedback_data.get('text', '')}\n"
        f"Sentiment: {feedback_data.get('sentiment_label', 'unknown')} "
        f"({feedback_data.get('sentiment_score', 0)})\n"
        f"Urgent: {feedback_data.get('is_urgent', False)}\n"
        f"Issue category: {feedback_data.get('extracted_issue', 'N/A')}"
    )

    async with httpx.AsyncClient(timeout=30) as http_client:
        response = await http_client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 800,
            },
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)
    return {
        "title": result.get("title", "Customer feedback issue"),
        "description": result.get("description", ""),
    }


def _add_timeline_entry(
    db: Session,
    feedback_id: int,
    org_id: int,
    event_type: str,
    actor_id: Optional[int],
    metadata: dict,
) -> None:
    """Add a workflow event timeline entry for a feedback item."""
    event = FeedbackWorkflowEvent(
        feedback_id=feedback_id,
        organization_id=org_id,
        actor_id=actor_id,
        event_type=event_type,
        metadata_=metadata,
    )
    db.add(event)
    db.commit()


# ============================================================================
# OAuth Flow Endpoints
# ============================================================================

@router.get(
    "/connect",
    response_model=LinearConnectResponse,
    dependencies=[Depends(require_feature("linear_integration"))],
)
def linear_oauth_connect(
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
):
    """Initiate Linear OAuth flow. Returns the authorization URL."""
    if not LINEAR_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Linear OAuth is not configured. Set LINEAR_CLIENT_ID environment variable.",
        )

    state = secrets.token_urlsafe(32)
    linear_oauth_states[state] = {
        "organization_id": current_org.id,
        "user_id": current_user.id,
    }

    params = {
        "client_id": LINEAR_CLIENT_ID,
        "redirect_uri": LINEAR_REDIRECT_URI,
        "response_type": "code",
        "scope": "read,write",
        "state": state,
        "prompt": "consent",
    }

    auth_url = f"https://linear.app/oauth/authorize?{urllib.parse.urlencode(params)}"
    logger.info(f"Generated Linear OAuth URL for org {current_org.id}")

    return LinearConnectResponse(auth_url=auth_url, state=state)


@router.get("/callback")
async def linear_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Handle Linear OAuth callback. Exchange code for token, store integration."""
    if error:
        logger.error(f"Linear OAuth error: {error}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=missing_params"
        )

    state_data = linear_oauth_states.pop(state, None)
    if not state_data:
        logger.error(f"Invalid or expired Linear OAuth state: {state}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=invalid_state"
        )

    organization_id = state_data["organization_id"]
    user_id = state_data["user_id"]

    try:
        # Exchange code for access token
        async with httpx.AsyncClient(timeout=30) as http_client:
            response = await http_client.post(
                "https://api.linear.app/oauth/token",
                data={
                    "client_id": LINEAR_CLIENT_ID,
                    "client_secret": LINEAR_CLIENT_SECRET,
                    "redirect_uri": LINEAR_REDIRECT_URI,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("No access_token in response")

        # Fetch org info + create webhook via the async Linear client
        linear_client = LinearClient(access_token=access_token)
        org_info = await linear_client.get_organization()

        webhook_secret = secrets.token_urlsafe(32)
        webhook_id = ""
        webhook_url = f"{BACKEND_URL}/api/v1/webhooks/linear/inbound"

        # Only create webhook if backend is publicly reachable (not localhost)
        if "localhost" not in BACKEND_URL and "127.0.0.1" not in BACKEND_URL:
            try:
                webhook_info = await linear_client.create_webhook(
                    url=webhook_url, team_id=None, secret=webhook_secret
                )
                webhook_id = webhook_info.get("id", "")
            except Exception as wh_exc:
                logger.warning(f"Failed to create Linear webhook (non-blocking): {wh_exc}")
        else:
            logger.info("Skipping Linear webhook creation for localhost environment")

        # Upsert LinearIntegration (deactivate old if exists)
        existing = (
            db.query(LinearIntegration)
            .filter(LinearIntegration.organization_id == organization_id)
            .first()
        )
        if existing:
            existing.access_token = access_token
            existing.linear_org_id = org_info["id"]
            existing.linear_org_name = org_info["name"]
            existing.connected_by_user_id = user_id
            existing.connected_at = datetime.utcnow()
            existing.is_active = True
            existing.webhook_secret = webhook_secret
            existing.webhook_id = webhook_id
            existing.updated_at = datetime.utcnow()
            integration = existing
        else:
            integration = LinearIntegration(
                organization_id=organization_id,
                access_token=access_token,
                linear_org_id=org_info["id"],
                linear_org_name=org_info["name"],
                connected_by_user_id=user_id,
                is_active=True,
                webhook_secret=webhook_secret,
                webhook_id=webhook_id,
            )
            db.add(integration)

        db.flush()

        # Create default status mappings if none exist
        existing_mappings = (
            db.query(LinearStatusMapping)
            .filter(LinearStatusMapping.organization_id == organization_id)
            .count()
        )
        if existing_mappings == 0:
            for mapping_data in DEFAULT_STATUS_MAPPINGS:
                mapping = LinearStatusMapping(
                    organization_id=organization_id,
                    **mapping_data,
                )
                db.add(mapping)

        db.commit()
        logger.info(f"Linear integration created for org {organization_id}")

        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_success=true&provider=linear"
        )

    except httpx.HTTPError as exc:
        logger.error(f"Linear OAuth HTTP error: {exc}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=network_error"
        )
    except Exception as exc:
        logger.error(f"Linear OAuth unexpected error: {exc}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=unexpected_error"
        )


@router.delete(
    "/disconnect",
    response_model=LinearDisconnectResponse,
    dependencies=[Depends(require_feature("linear_integration"))],
)
async def linear_disconnect(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Revoke Linear integration. Preserves existing issue links."""
    integration = (
        db.query(LinearIntegration)
        .filter(LinearIntegration.organization_id == current_org.id)
        .first()
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Linear integration found.",
        )

    # Attempt to delete the webhook (best effort)
    if integration.webhook_id:
        try:
            linear_client = LinearClient(access_token=integration.access_token)
            await linear_client.delete_webhook(webhook_id=integration.webhook_id)
        except Exception as exc:
            logger.warning(f"Failed to delete Linear webhook: {exc}")

    integration.is_active = False
    integration.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"Linear integration deactivated for org {current_org.id}")
    return LinearDisconnectResponse(
        success=True,
        message="Linear integration disconnected. Existing issue links are preserved.",
    )


@router.get("/status", response_model=LinearStatusResponse)
def linear_status(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return Linear connection status for the current org."""
    # Query any integration (including inactive) to show connection history
    integration = (
        db.query(LinearIntegration)
        .filter(LinearIntegration.organization_id == current_org.id)
        .first()
    )
    if not integration:
        return LinearStatusResponse(connected=False)

    # Look up the connected user's email
    connected_by_email = None
    if integration.connected_by_user_id:
        user = db.query(User).filter(User.id == integration.connected_by_user_id).first()
        if user:
            connected_by_email = user.email

    return LinearStatusResponse(
        connected=True,
        org_name=integration.linear_org_name,
        org_id=integration.linear_org_id,
        connected_by_email=connected_by_email,
        connected_at=integration.connected_at,
        is_active=integration.is_active,
    )


# ---- Default issue templates ----
DEFAULT_ISSUE_TITLE_TEMPLATE = "{{sentiment_emoji}} [{{source}}] {{text|truncate:80}}"
DEFAULT_ISSUE_DESCRIPTION_TEMPLATE = """## Feedback

{{text}}

---

**Sentiment:** {{sentiment}} ({{sentiment_score}})
{{#pain_point_category}}**Pain Point:** {{pain_point_category}} — {{pain_point_severity}}{{/pain_point_category}}
{{#feature_request_category}}**Feature Request:** {{feature_request_category}} — {{feature_request_priority}}{{/feature_request_category}}
{{#urgent_category}}**Urgent:** {{urgent_category}} — Response: {{urgent_response_time}}{{/urgent_category}}

**Source:** {{source}} | **ID:** #{{feedback_id}} | **Created:** {{created_at}}"""


ISSUE_TEMPLATE_VARIABLES = [
    {"name": "text", "description": "The feedback text content", "example": "The app keeps crashing..."},
    {"name": "sentiment", "description": "Sentiment label (positive/neutral/negative)", "example": "negative"},
    {"name": "sentiment_score", "description": "Sentiment score (-1.0 to 1.0)", "example": "-0.85"},
    {"name": "sentiment_emoji", "description": "Emoji based on sentiment", "example": "😟"},
    {"name": "pain_point_category", "description": "Pain point category if detected", "example": "Performance"},
    {"name": "pain_point_severity", "description": "Severity (critical/major/moderate/minor/trivial)", "example": "critical"},
    {"name": "feature_request_category", "description": "Feature request category if detected", "example": "UI/UX"},
    {"name": "feature_request_priority", "description": "Priority (high/medium/low)", "example": "high"},
    {"name": "urgent_category", "description": "Urgent category if flagged", "example": "Bug Report"},
    {"name": "urgent_response_time", "description": "Suggested response time", "example": "immediate"},
    {"name": "source", "description": "Feedback source", "example": "email"},
    {"name": "created_at", "description": "When feedback was created", "example": "2026-01-31 10:30:00"},
    {"name": "feedback_id", "description": "Unique feedback ID", "example": "1234"},
]


@router.get(
    "/config",
    response_model=LinearConfigResponse,
    dependencies=[Depends(require_feature("linear_integration"))],
)
def get_linear_config(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get Linear integration configuration (templates)."""
    integration = _require_active_integration(current_org.id, db)
    return LinearConfigResponse(
        issue_title_template=integration.issue_title_template or DEFAULT_ISSUE_TITLE_TEMPLATE,
        issue_description_template=integration.issue_description_template or DEFAULT_ISSUE_DESCRIPTION_TEMPLATE,
    )


@router.put(
    "/config",
    response_model=LinearConfigResponse,
    dependencies=[Depends(require_feature("linear_integration"))],
)
def update_linear_config(
    data: LinearConfigUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update Linear integration configuration (templates)."""
    integration = _require_active_integration(current_org.id, db)
    if data.issue_title_template is not None:
        integration.issue_title_template = data.issue_title_template
    if data.issue_description_template is not None:
        integration.issue_description_template = data.issue_description_template
    integration.updated_at = datetime.utcnow()
    db.commit()
    return LinearConfigResponse(
        issue_title_template=integration.issue_title_template or DEFAULT_ISSUE_TITLE_TEMPLATE,
        issue_description_template=integration.issue_description_template or DEFAULT_ISSUE_DESCRIPTION_TEMPLATE,
    )


@router.post(
    "/test",
    dependencies=[Depends(require_feature("linear_integration"))],
)
async def test_linear_connection(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Test the Linear integration by verifying the API connection."""
    integration = _require_active_integration(current_org.id, db)
    try:
        linear_client = LinearClient(access_token=integration.access_token)
        org_info = await linear_client.get_organization()
        return {
            "success": True,
            "message": f"Connected to {org_info.get('name', 'Linear')} successfully.",
        }
    except Exception as exc:
        logger.warning(f"Linear connection test failed for org {current_org.id}: {exc}")
        return {
            "success": False,
            "message": f"Connection test failed: {str(exc)}",
        }


@router.get("/template-variables")
def get_linear_template_variables():
    """Get available template variables for Linear issue templates."""
    return {
        "variables": ISSUE_TEMPLATE_VARIABLES,
        "default_title_template": DEFAULT_ISSUE_TITLE_TEMPLATE,
        "default_description_template": DEFAULT_ISSUE_DESCRIPTION_TEMPLATE,
    }


# ============================================================================
# Issue Endpoints
# ============================================================================

@router.post(
    "/issues",
    dependencies=[Depends(require_feature("linear_integration"))],
    status_code=201,
)
async def create_linear_issue(
    data: CreateIssueRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Linear issue from a feedback item with optional AI-generated content."""
    integration = _require_active_integration(current_org.id, db)

    # Verify feedback belongs to org
    feedback = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == data.feedback_id,
            FeedbackItem.organization_id == current_org.id,
        )
        .first()
    )
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback item {data.feedback_id} not found.",
        )

    # Check for existing linked issues
    existing_links = (
        db.query(FeedbackLinearIssue)
        .filter(
            FeedbackLinearIssue.feedback_id == data.feedback_id,
            FeedbackLinearIssue.organization_id == current_org.id,
        )
        .all()
    )

    if existing_links and not data.force:
        # Return duplicate warning with 200 (not 201, since no issue was created)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=200,
            content={
                "warning": "duplicate",
                "existing_issues": [
                    {
                        "id": link.id,
                        "linear_issue_identifier": link.linear_issue_identifier,
                        "linear_issue_url": link.linear_issue_url,
                        "linear_issue_title": link.linear_issue_title,
                        "linear_status": link.linear_status,
                    }
                    for link in existing_links
                ],
            },
        )

    # Generate AI content if title/description not provided
    title = data.title
    description = data.description
    if not title or not description:
        feedback_data = {
            "text": feedback.text,
            "sentiment_label": feedback.sentiment_label,
            "sentiment_score": feedback.sentiment_score,
            "is_urgent": feedback.is_urgent,
            "extracted_issue": feedback.extracted_issue,
        }
        generated = await generate_linear_issue_content(feedback_data=feedback_data, org_id=current_org.id, db=db)
        title = title or generated["title"]
        description = description or generated["description"]

    # Build issue input for Linear API
    issue_input: dict = {
        "title": title,
        "description": description,
    }
    if data.team_id:
        issue_input["teamId"] = data.team_id
    if data.project_id:
        issue_input["projectId"] = data.project_id
    if data.priority is not None:
        issue_input["priority"] = data.priority
    if data.label_ids:
        issue_input["labelIds"] = data.label_ids

    # Create issue via Linear API
    linear_client = LinearClient(access_token=integration.access_token)
    created_issue = await linear_client.create_issue(input=issue_input)

    # Store the link
    link = FeedbackLinearIssue(
        organization_id=current_org.id,
        feedback_id=data.feedback_id,
        linear_issue_id=created_issue["id"],
        linear_issue_identifier=created_issue["identifier"],
        linear_issue_url=created_issue["url"],
        linear_issue_title=created_issue["title"],
        linear_status=created_issue.get("state", {}).get("name"),
        linear_priority=created_issue.get("priority"),
        created_by_user_id=current_user.id,
    )
    db.add(link)
    db.flush()

    # Add timeline entry
    _add_timeline_entry(
        db=db,
        feedback_id=data.feedback_id,
        org_id=current_org.id,
        event_type="linear_issue_created",
        actor_id=current_user.id,
        metadata={
            "linear_issue_identifier": created_issue["identifier"],
            "linear_issue_url": created_issue["url"],
            "linear_issue_title": created_issue["title"],
            "created_by": current_user.email,
        },
    )

    db.commit()
    db.refresh(link)

    logger.info(f"Created Linear issue {created_issue['identifier']} for feedback {data.feedback_id}")

    return {
        "id": link.id,
        "feedback_id": link.feedback_id,
        "linear_issue_id": link.linear_issue_id,
        "linear_issue_identifier": link.linear_issue_identifier,
        "linear_issue_url": link.linear_issue_url,
        "linear_issue_title": link.linear_issue_title,
        "linear_status": link.linear_status,
        "linear_assignee": link.linear_assignee,
        "linear_priority": link.linear_priority,
        "created_at": link.created_at,
    }


@router.get(
    "/issues",
    response_model=List[LinkedIssueResponse],
    dependencies=[Depends(require_feature("linear_integration"))],
)
def get_linked_issues(
    feedback_id: int = Query(..., description="Feedback item ID"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get all Linear issues linked to a feedback item."""
    links = (
        db.query(FeedbackLinearIssue)
        .filter(
            FeedbackLinearIssue.feedback_id == feedback_id,
            FeedbackLinearIssue.organization_id == current_org.id,
        )
        .order_by(FeedbackLinearIssue.created_at.desc())
        .all()
    )
    return links


# ============================================================================
# Linear API Proxy Endpoints (teams, projects, labels)
# ============================================================================

@router.get(
    "/teams",
    dependencies=[Depends(require_feature("linear_integration"))],
)
async def get_linear_teams(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Fetch teams from the connected Linear organization."""
    integration = _require_active_integration(current_org.id, db)
    linear_client = LinearClient(access_token=integration.access_token)
    return await linear_client.get_teams()


@router.get(
    "/projects",
    dependencies=[Depends(require_feature("linear_integration"))],
)
async def get_linear_projects(
    team_id: str = Query(..., description="Linear team ID"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Fetch projects for a team from the connected Linear organization."""
    integration = _require_active_integration(current_org.id, db)
    linear_client = LinearClient(access_token=integration.access_token)
    return await linear_client.get_projects(team_id=team_id)


@router.get(
    "/labels",
    dependencies=[Depends(require_feature("linear_integration"))],
)
async def get_linear_labels(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Fetch all issue labels from the connected Linear organization."""
    integration = _require_active_integration(current_org.id, db)
    linear_client = LinearClient(access_token=integration.access_token)
    return await linear_client.get_labels()


# ============================================================================
# Configuration Endpoints — Team Mappings
# ============================================================================

@router.get(
    "/team-mappings",
    response_model=List[TeamMappingResponse],
    dependencies=[Depends(require_feature("linear_integration"))],
)
def get_team_mappings(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get category-to-team mappings for the current org."""
    mappings = (
        db.query(LinearTeamMapping)
        .filter(LinearTeamMapping.organization_id == current_org.id)
        .order_by(LinearTeamMapping.priority.asc(), LinearTeamMapping.id.asc())
        .all()
    )
    return mappings


@router.put(
    "/team-mappings",
    response_model=List[TeamMappingResponse],
    dependencies=[Depends(require_feature("linear_integration"))],
)
def update_team_mappings(
    mappings: List[TeamMappingItem],
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Replace all category-to-team mappings for the current org."""
    # Delete existing
    db.query(LinearTeamMapping).filter(
        LinearTeamMapping.organization_id == current_org.id
    ).delete()

    # Insert new
    new_mappings = []
    for item in mappings:
        mapping = LinearTeamMapping(
            organization_id=current_org.id,
            rereflect_category=item.rereflect_category,
            linear_team_id=item.linear_team_id,
            linear_team_name=item.linear_team_name,
            linear_project_id=item.linear_project_id,
            linear_project_name=item.linear_project_name,
            priority=item.priority,
        )
        db.add(mapping)
        new_mappings.append(mapping)

    db.commit()
    for m in new_mappings:
        db.refresh(m)

    return new_mappings


# ============================================================================
# Configuration Endpoints — Status Mappings
# ============================================================================

@router.get(
    "/status-mappings",
    response_model=List[StatusMappingResponse],
    dependencies=[Depends(require_feature("linear_integration"))],
)
def get_status_mappings(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get Linear-to-Rereflect status mappings for the current org."""
    mappings = (
        db.query(LinearStatusMapping)
        .filter(LinearStatusMapping.organization_id == current_org.id)
        .order_by(LinearStatusMapping.id.asc())
        .all()
    )
    return mappings


@router.put(
    "/status-mappings",
    response_model=List[StatusMappingResponse],
    dependencies=[Depends(require_feature("linear_integration"))],
)
def update_status_mappings(
    mappings: List[StatusMappingItem],
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Replace all Linear-to-Rereflect status mappings for the current org."""
    # Delete existing
    db.query(LinearStatusMapping).filter(
        LinearStatusMapping.organization_id == current_org.id
    ).delete()

    # Insert new
    new_mappings = []
    for item in mappings:
        mapping = LinearStatusMapping(
            organization_id=current_org.id,
            linear_status_name=item.linear_status_name,
            linear_status_type=item.linear_status_type,
            rereflect_status=item.rereflect_status,
        )
        db.add(mapping)
        new_mappings.append(mapping)

    db.commit()
    for m in new_mappings:
        db.refresh(m)

    return new_mappings
