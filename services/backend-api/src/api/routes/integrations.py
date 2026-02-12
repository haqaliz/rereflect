"""
Integrations API routes for managing Slack, Intercom, and other third-party integrations.
"""

from typing import Optional, List
from datetime import datetime
import httpx
import logging
import os
import secrets
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl, field_validator

from src.database.session import get_db
from src.models.integration import Integration, SlackAlertLog
from src.models.organization import Organization
from src.api.dependencies import get_current_org, require_feature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

# Slack OAuth Configuration
SLACK_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
SLACK_REDIRECT_URI = os.environ.get("SLACK_REDIRECT_URI", "http://localhost:8000/api/v1/integrations/slack/oauth/callback")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Intercom OAuth Configuration
INTERCOM_CLIENT_ID = os.environ.get("INTERCOM_CLIENT_ID", "")
INTERCOM_CLIENT_SECRET = os.environ.get("INTERCOM_CLIENT_SECRET", "")
INTERCOM_REDIRECT_URI = os.environ.get("INTERCOM_REDIRECT_URI", "http://localhost:8000/api/v1/integrations/intercom/oauth/callback")

# OAuth state storage (in production, use Redis or database)
oauth_states: dict = {}


# ============================================================================
# Pydantic Schemas
# ============================================================================

DEFAULT_MESSAGE_TEMPLATE = """*{{sentiment_emoji}} New Feedback Alert*

> {{text}}

*Sentiment:* {{sentiment}} ({{sentiment_score}})
{{#pain_point_category}}*Pain Point:* {{pain_point_category}} ({{pain_point_severity}}){{/pain_point_category}}
{{#feature_request_category}}*Feature Request:* {{feature_request_category}} ({{feature_request_priority}}){{/feature_request_category}}
{{#urgent_category}}*Urgent:* {{urgent_category}} - Response: {{urgent_response_time}}{{/urgent_category}}
*Source:* {{source}} | *Created:* {{created_at}}"""


class SlackWebhookCreateRequest(BaseModel):
    """Request to create a Slack webhook integration."""
    name: str
    webhook_url: str
    triggers: List[str] = ["urgent"]  # urgent, negative, all, daily_digest, weekly_digest
    included_fields: List[str] = ["text", "sentiment"]  # Legacy field
    digest_time: Optional[str] = "09:00"  # HH:MM format
    message_template: Optional[str] = None  # Custom message template with variables

    @field_validator('webhook_url')
    @classmethod
    def validate_webhook_url(cls, v):
        if not v.startswith('https://hooks.slack.com/'):
            raise ValueError('Invalid Slack webhook URL. Must start with https://hooks.slack.com/')
        return v

    @field_validator('triggers')
    @classmethod
    def validate_triggers(cls, v):
        valid_triggers = {'urgent', 'negative', 'all', 'daily_digest', 'weekly_digest'}
        for trigger in v:
            if trigger not in valid_triggers:
                raise ValueError(f'Invalid trigger: {trigger}. Valid options: {valid_triggers}')
        return v

    @field_validator('included_fields')
    @classmethod
    def validate_fields(cls, v):
        valid_fields = {
            'text', 'sentiment', 'sentiment_score', 'pain_point_category',
            'pain_point_severity', 'feature_request_category', 'feature_request_priority',
            'urgent_category', 'urgent_response_time', 'source', 'link'
        }
        for field in v:
            if field not in valid_fields:
                raise ValueError(f'Invalid field: {field}. Valid options: {valid_fields}')
        return v


class IntegrationUpdateRequest(BaseModel):
    """Request to update an integration."""
    name: Optional[str] = None
    triggers: Optional[List[str]] = None
    included_fields: Optional[List[str]] = None
    digest_time: Optional[str] = None
    is_active: Optional[bool] = None
    message_template: Optional[str] = None


class IntegrationResponse(BaseModel):
    """Response for a single integration."""
    id: int
    type: str
    name: Optional[str]
    integration_type: str = "webhook"  # 'webhook' or 'oauth'
    channel_name: Optional[str] = None
    team_name: Optional[str] = None
    triggers: List[str]
    included_fields: List[str]
    digest_time: Optional[str]
    message_template: Optional[str] = None
    is_active: bool
    last_used_at: Optional[datetime]
    error_count: int
    last_error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IntegrationListResponse(BaseModel):
    """Response for listing integrations."""
    integrations: List[IntegrationResponse]
    total: int


class SlackTestRequest(BaseModel):
    """Request to send a test Slack message."""
    integration_id: int


class SlackTestResponse(BaseModel):
    """Response from test message."""
    success: bool
    message: str


class AlertLogResponse(BaseModel):
    """Response for alert log entry."""
    id: int
    integration_id: int
    feedback_id: Optional[int]
    alert_type: str
    status: str
    error_message: Optional[str]
    sent_at: datetime

    class Config:
        from_attributes = True


class TemplateVariable(BaseModel):
    """A template variable that can be used in message templates."""
    name: str
    description: str
    example: str


class TemplateVariablesResponse(BaseModel):
    """Response containing available template variables."""
    variables: List[TemplateVariable]
    default_template: str


# Available template variables
TEMPLATE_VARIABLES = [
    TemplateVariable(name="text", description="The feedback text content", example="The app keeps crashing..."),
    TemplateVariable(name="sentiment", description="Sentiment label (positive/neutral/negative)", example="negative"),
    TemplateVariable(name="sentiment_score", description="Sentiment score (-1.0 to 1.0)", example="-0.85"),
    TemplateVariable(name="sentiment_emoji", description="Emoji based on sentiment", example="😟"),
    TemplateVariable(name="pain_point_category", description="Pain point category if detected", example="Performance"),
    TemplateVariable(name="pain_point_severity", description="Severity (critical/major/moderate/minor/trivial)", example="critical"),
    TemplateVariable(name="feature_request_category", description="Feature request category if detected", example="UI/UX"),
    TemplateVariable(name="feature_request_priority", description="Priority (high/medium/low)", example="high"),
    TemplateVariable(name="urgent_category", description="Urgent category if flagged", example="Bug Report"),
    TemplateVariable(name="urgent_response_time", description="Suggested response time", example="immediate"),
    TemplateVariable(name="source", description="Feedback source", example="email"),
    TemplateVariable(name="created_at", description="When feedback was created", example="2026-01-31 10:30:00"),
    TemplateVariable(name="feedback_id", description="Unique feedback ID", example="1234"),
]


# ============================================================================
# Helper Functions
# ============================================================================

def integration_to_response(integration: Integration) -> IntegrationResponse:
    """Convert Integration model to response schema."""
    config = integration.config or {}
    return IntegrationResponse(
        id=integration.id,
        type=integration.type,
        name=integration.name,
        integration_type=config.get('integration_type', 'webhook'),
        channel_name=config.get('channel_name'),
        team_name=config.get('team_name'),
        triggers=integration.triggers or ['urgent'],
        included_fields=integration.included_fields or ['text', 'sentiment'],
        digest_time=integration.digest_time.strftime('%H:%M') if integration.digest_time else '09:00',
        message_template=integration.message_template,
        is_active=integration.is_active,
        last_used_at=integration.last_used_at,
        error_count=integration.error_count or 0,
        last_error=integration.last_error,
        created_at=integration.created_at,
    )


def send_slack_message(webhook_url: str, blocks: list, text: str = "Rereflect Alert") -> dict:
    """Send a message to Slack via webhook."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                webhook_url,
                json={
                    "text": text,  # Fallback for notifications
                    "blocks": blocks
                }
            )
            response.raise_for_status()
            return {"success": True, "response": response.text}
    except httpx.HTTPError as e:
        logger.error(f"Slack webhook failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=IntegrationListResponse)
def list_integrations(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """List all integrations for the current organization."""
    integrations = db.query(Integration).filter(
        Integration.organization_id == current_org.id
    ).order_by(Integration.created_at.desc()).all()

    return IntegrationListResponse(
        integrations=[integration_to_response(i) for i in integrations],
        total=len(integrations)
    )


@router.post("/slack/webhook", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_feature("slack_integration"))])
def create_slack_webhook(
    data: SlackWebhookCreateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Create a new Slack webhook integration."""
    from datetime import time

    # Parse digest time
    digest_time_obj = None
    if data.digest_time:
        try:
            hours, minutes = map(int, data.digest_time.split(':'))
            digest_time_obj = time(hours, minutes)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid digest_time format. Use HH:MM (e.g., 09:00)"
            )

    # Create integration
    integration = Integration(
        organization_id=current_org.id,
        type="slack",
        name=data.name,
        config={
            "webhook_url": data.webhook_url,
            "integration_type": "webhook"
        },
        triggers=data.triggers,
        included_fields=data.included_fields,
        digest_time=digest_time_obj,
        message_template=data.message_template,
        is_active=True,
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    logger.info(f"Created Slack integration {integration.id} for org {current_org.id}")

    return integration_to_response(integration)


@router.get("/{integration_id}", response_model=IntegrationResponse)
def get_integration(
    integration_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get a single integration by ID."""
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.organization_id == current_org.id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    return integration_to_response(integration)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
def update_integration(
    integration_id: int,
    data: IntegrationUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Update an integration's settings."""
    from datetime import time

    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.organization_id == current_org.id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    # Update fields
    if data.name is not None:
        integration.name = data.name

    if data.triggers is not None:
        integration.triggers = data.triggers

    if data.included_fields is not None:
        integration.included_fields = data.included_fields

    if data.digest_time is not None:
        try:
            hours, minutes = map(int, data.digest_time.split(':'))
            integration.digest_time = time(hours, minutes)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid digest_time format. Use HH:MM (e.g., 09:00)"
            )

    if data.is_active is not None:
        integration.is_active = data.is_active
        # Reset error count when re-enabling
        if data.is_active:
            integration.error_count = 0
            integration.last_error = None

    if data.message_template is not None:
        integration.message_template = data.message_template

    db.commit()
    db.refresh(integration)

    return integration_to_response(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Delete an integration."""
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.organization_id == current_org.id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    db.delete(integration)
    db.commit()

    logger.info(f"Deleted integration {integration_id} for org {current_org.id}")
    return None


@router.post("/slack/test", response_model=SlackTestResponse, dependencies=[Depends(require_feature("slack_integration"))])
def test_slack_integration(
    data: SlackTestRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Send a test message to verify Slack integration (webhook or OAuth)."""
    integration = db.query(Integration).filter(
        Integration.id == data.integration_id,
        Integration.organization_id == current_org.id,
        Integration.type == "slack"
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Slack integration not found"
        )

    config = integration.config or {}
    integration_type = config.get('integration_type', 'webhook')

    # Build test message
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "✅ Rereflect Test Message",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Your Slack integration *{integration.name}* is working correctly!\n\n"
                        f"You'll receive alerts for: `{', '.join(integration.triggers or ['urgent'])}`"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕐 Sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                }
            ]
        }
    ]

    # Send via webhook or OAuth depending on integration type
    if integration_type == "oauth":
        access_token = integration.oauth_access_token
        channel_id = config.get('channel_id')

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Integration has no OAuth token configured"
            )

        if not channel_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Integration has no channel configured. Please reconnect to Slack."
            )

        result = send_slack_message_oauth(access_token, channel_id, blocks, "Rereflect Test Message")
    else:
        # Webhook integration
        webhook_url = config.get('webhook_url')

        if not webhook_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Integration has no webhook URL configured"
            )

        result = send_slack_message(webhook_url, blocks, "Rereflect Test Message")

    if result["success"]:
        # Update last_used_at
        integration.last_used_at = datetime.utcnow()
        integration.error_count = 0
        integration.last_error = None
        db.commit()

        return SlackTestResponse(
            success=True,
            message="Test message sent successfully! Check your Slack channel."
        )
    else:
        # Log the error
        integration.error_count = (integration.error_count or 0) + 1
        integration.last_error = result.get("error", "Unknown error")
        db.commit()

        return SlackTestResponse(
            success=False,
            message=f"Failed to send test message: {result.get('error', 'Unknown error')}"
        )


@router.get("/{integration_id}/logs", response_model=List[AlertLogResponse])
def get_integration_logs(
    integration_id: int,
    limit: int = 50,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get alert logs for an integration."""
    # Verify integration belongs to org
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.organization_id == current_org.id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found"
        )

    logs = db.query(SlackAlertLog).filter(
        SlackAlertLog.integration_id == integration_id
    ).order_by(SlackAlertLog.sent_at.desc()).limit(limit).all()

    return logs


@router.get("/slack/template-variables", response_model=TemplateVariablesResponse)
def get_template_variables():
    """Get available template variables for Slack message customization."""
    return TemplateVariablesResponse(
        variables=TEMPLATE_VARIABLES,
        default_template=DEFAULT_MESSAGE_TEMPLATE
    )


# ============================================================================
# Slack OAuth Endpoints
# ============================================================================

class OAuthConnectResponse(BaseModel):
    """Response containing OAuth authorization URL."""
    auth_url: str
    state: str


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback."""
    success: bool
    integration_id: Optional[int] = None
    team_name: Optional[str] = None
    channel_name: Optional[str] = None
    message: str


@router.get("/slack/oauth/connect", response_model=OAuthConnectResponse, dependencies=[Depends(require_feature("slack_integration"))])
def slack_oauth_connect(
    name: str = Query(..., description="Name for the integration"),
    current_org: Organization = Depends(get_current_org),
):
    """
    Initiate Slack OAuth flow.
    Returns the authorization URL to redirect the user to.
    """
    if not SLACK_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack OAuth is not configured. Set SLACK_CLIENT_ID environment variable."
        )

    # Generate a secure state parameter
    state = secrets.token_urlsafe(32)

    # Store state with org info (expires after 10 minutes in production, use Redis with TTL)
    oauth_states[state] = {
        "organization_id": current_org.id,
        "name": name,
        "created_at": datetime.utcnow()
    }

    # Build OAuth authorization URL
    # Scopes: chat:write allows posting messages, channels:read allows listing channels
    scopes = "chat:write,channels:read,groups:read"

    params = {
        "client_id": SLACK_CLIENT_ID,
        "scope": scopes,
        "redirect_uri": SLACK_REDIRECT_URI,
        "state": state,
    }

    auth_url = f"https://slack.com/oauth/v2/authorize?{urllib.parse.urlencode(params)}"

    logger.info(f"Generated Slack OAuth URL for org {current_org.id}")

    return OAuthConnectResponse(auth_url=auth_url, state=state)


@router.get("/slack/oauth/callback")
def slack_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Handle Slack OAuth callback.
    Exchanges the authorization code for an access token and creates the integration.
    Redirects to frontend with success or error.
    """
    # Handle errors from Slack
    if error:
        logger.error(f"Slack OAuth error: {error}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=missing_params"
        )

    # Validate state
    state_data = oauth_states.pop(state, None)
    if not state_data:
        logger.error(f"Invalid or expired OAuth state: {state}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=invalid_state"
        )

    organization_id = state_data["organization_id"]
    integration_name = state_data["name"]

    # Exchange code for access token
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": SLACK_CLIENT_ID,
                    "client_secret": SLACK_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": SLACK_REDIRECT_URI,
                }
            )
            response.raise_for_status()
            data = response.json()

        if not data.get("ok"):
            error_msg = data.get("error", "unknown_error")
            logger.error(f"Slack OAuth token exchange failed: {error_msg}")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/settings/integrations?oauth_error={urllib.parse.quote(error_msg)}"
            )

        # Extract token and team info
        access_token = data.get("access_token")
        team_info = data.get("team", {})
        team_id = team_info.get("id")
        team_name = team_info.get("name")
        bot_user_id = data.get("bot_user_id")
        incoming_webhook = data.get("incoming_webhook", {})

        logger.info(f"Slack OAuth successful for team {team_name} ({team_id})")

        # Create integration with OAuth token
        integration = Integration(
            organization_id=organization_id,
            type="slack",
            name=integration_name,
            config={
                "integration_type": "oauth",
                "team_id": team_id,
                "team_name": team_name,
                "bot_user_id": bot_user_id,
                "channel_id": incoming_webhook.get("channel_id"),
                "channel_name": incoming_webhook.get("channel"),
            },
            oauth_access_token=access_token,  # In production, encrypt this!
            triggers=["urgent"],
            is_active=True,
        )

        db.add(integration)
        db.commit()
        db.refresh(integration)

        logger.info(f"Created OAuth integration {integration.id} for org {organization_id}")

        # Redirect to the new integration page
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations/{integration.id}?oauth_success=true"
        )

    except httpx.HTTPError as e:
        logger.error(f"Slack OAuth HTTP error: {e}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=network_error"
        )
    except Exception as e:
        logger.error(f"Slack OAuth unexpected error: {e}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=unexpected_error"
        )


def send_slack_message_oauth(access_token: str, channel_id: str, blocks: list, text: str = "Rereflect Alert") -> dict:
    """Send a message to Slack via OAuth token (Bot API)."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": channel_id,
                    "text": text,
                    "blocks": blocks,
                }
            )
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                return {"success": True, "response": data}
            else:
                return {"success": False, "error": data.get("error", "Unknown Slack API error")}
    except httpx.HTTPError as e:
        logger.error(f"Slack OAuth message failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Intercom OAuth Endpoints
# ============================================================================

@router.get("/intercom/oauth/connect", response_model=OAuthConnectResponse, dependencies=[Depends(require_feature("intercom_integration"))])
def intercom_oauth_connect(
    name: str = Query(..., description="Name for the integration"),
    current_org: Organization = Depends(get_current_org),
):
    """
    Initiate Intercom OAuth flow.
    Returns the authorization URL to redirect the user to.
    """
    if not INTERCOM_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Intercom OAuth is not configured. Set INTERCOM_CLIENT_ID environment variable."
        )

    # Generate a secure state parameter
    state = secrets.token_urlsafe(32)

    # Store state with org info
    oauth_states[state] = {
        "organization_id": current_org.id,
        "name": name,
        "provider": "intercom",
        "created_at": datetime.utcnow(),
    }

    # Build Intercom OAuth authorization URL
    params = {
        "client_id": INTERCOM_CLIENT_ID,
        "state": state,
        "redirect_uri": INTERCOM_REDIRECT_URI,
    }

    auth_url = f"https://app.intercom.com/oauth?{urllib.parse.urlencode(params)}"

    logger.info(f"Generated Intercom OAuth URL for org {current_org.id}")

    return OAuthConnectResponse(auth_url=auth_url, state=state)


@router.get("/intercom/oauth/callback")
def intercom_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Handle Intercom OAuth callback.
    Exchanges the authorization code for an access token and creates the integration.
    Redirects to frontend with success or error.
    """
    # Handle errors from Intercom
    if error:
        logger.error(f"Intercom OAuth error: {error}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=missing_params"
        )

    # Validate state
    state_data = oauth_states.pop(state, None)
    if not state_data:
        logger.error(f"Invalid or expired Intercom OAuth state: {state}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=invalid_state"
        )

    organization_id = state_data["organization_id"]
    integration_name = state_data["name"]

    # Exchange code for access token
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                "https://api.intercom.io/auth/eagle/token",
                json={
                    "code": code,
                    "client_id": INTERCOM_CLIENT_ID,
                    "client_secret": INTERCOM_CLIENT_SECRET,
                }
            )
            response.raise_for_status()
            token_data = response.json()

        access_token = token_data.get("token")

        # Fetch workspace info
        with httpx.Client(timeout=30) as client:
            me_response = client.get(
                "https://api.intercom.io/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            me_response.raise_for_status()
            me_data = me_response.json()

        workspace_name = me_data.get("app", {}).get("name", "Unknown Workspace")
        workspace_id = me_data.get("app", {}).get("id_code", "")
        admin_id = me_data.get("id", "")

        logger.info(f"Intercom OAuth successful for workspace {workspace_name} ({workspace_id})")

        # Create integration with OAuth token
        integration = Integration(
            organization_id=organization_id,
            type="intercom",
            name=integration_name,
            config={
                "integration_type": "oauth",
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "admin_id": admin_id,
            },
            oauth_access_token=access_token,
            triggers=["urgent"],
            is_active=True,
        )

        db.add(integration)
        db.commit()
        db.refresh(integration)

        logger.info(f"Created Intercom integration {integration.id} for org {organization_id}")

        # Redirect to the new integration page
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations/{integration.id}?oauth_success=true"
        )

    except httpx.HTTPError as e:
        logger.error(f"Intercom OAuth HTTP error: {e}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=network_error"
        )
    except Exception as e:
        logger.error(f"Intercom OAuth unexpected error: {e}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings/integrations?oauth_error=unexpected_error"
        )
