"""
Feedback Sources API - CRUD endpoints for managing inbound feedback sources.
Supports Slack, Discord, Webhooks, and other integrations.
"""

import logging
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.api.dependencies import get_current_org, require_feature
from src.models import Organization, FeedbackSource, FeedbackSourceEvent, Integration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feedback-sources", tags=["feedback-sources"])


# ============ Pydantic Schemas ============

class TriggerConfig(BaseModel):
    """Configuration for what events trigger feedback capture."""
    all_messages: bool = False
    reactions: List[str] = Field(default_factory=list)  # Emoji names
    mentions: Optional[dict] = Field(default_factory=lambda: {"bot": False, "users": []})
    keywords: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    custom_rules: List[dict] = Field(default_factory=list)


class FieldMappingConfig(BaseModel):
    """Configuration for how to extract feedback from source events."""
    text_source: str = "message"  # message, thread, full
    include_author: bool = True
    include_source_name: bool = True
    include_context: bool = False
    max_context_messages: int = 5
    custom_template: Optional[str] = None


class FeedbackSourceCreate(BaseModel):
    """Request body for creating a feedback source."""
    source_type: str = Field(..., description="Source type: slack, webhook, discord, email")
    name: Optional[str] = Field(None, description="User-defined name")
    integration_id: Optional[int] = Field(None, description="Link to existing integration (for OAuth sources)")
    provider_config: Optional[dict] = Field(default_factory=dict)
    triggers: Optional[TriggerConfig] = None
    field_mapping: Optional[FieldMappingConfig] = None
    auto_import: bool = True


class FeedbackSourceUpdate(BaseModel):
    """Request body for updating a feedback source."""
    name: Optional[str] = None
    provider_config: Optional[dict] = None
    triggers: Optional[TriggerConfig] = None
    field_mapping: Optional[FieldMappingConfig] = None
    auto_import: Optional[bool] = None
    is_active: Optional[bool] = None


class FeedbackSourceResponse(BaseModel):
    """Response model for feedback source."""
    id: int
    organization_id: int
    integration_id: Optional[int]
    source_type: str
    name: Optional[str]
    provider_config: dict
    triggers: dict
    field_mapping: dict
    auto_import: bool
    is_active: bool
    last_event_at: Optional[datetime]
    events_processed: int
    error_count: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    # Computed fields
    webhook_url: Optional[str] = None

    class Config:
        from_attributes = True


class FeedbackSourceListResponse(BaseModel):
    """Response model for listing feedback sources."""
    sources: List[FeedbackSourceResponse]
    total: int


class SourceTypeInfo(BaseModel):
    """Information about a supported source type."""
    type: str
    name: str
    description: str
    requires_integration: bool
    available: bool


class FeedbackSourceEventResponse(BaseModel):
    """Response model for source events."""
    id: int
    external_event_id: str
    external_message_id: Optional[str]
    event_type: str
    status: str
    trigger_matched: Optional[str]
    feedback_id: Optional[int]
    pending_feedback_id: Optional[int]
    error_message: Optional[str]
    received_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ChannelInfo(BaseModel):
    """Information about a Slack/Discord channel."""
    id: str
    name: str
    is_private: bool = False
    is_configured: bool = False


# ============ Helper Functions ============

def _get_source_or_404(db: Session, source_id: int, org_id: int) -> FeedbackSource:
    """Get a feedback source or raise 404."""
    source = db.query(FeedbackSource).filter(
        FeedbackSource.id == source_id,
        FeedbackSource.organization_id == org_id,
    ).first()

    if not source:
        raise HTTPException(status_code=404, detail="Feedback source not found")

    return source


def _generate_webhook_url(webhook_id: str) -> str:
    """Generate the webhook URL for a source."""
    import os
    base_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    return f"{base_url}/api/v1/webhooks/inbound/{webhook_id}"


# ============ Endpoints ============

@router.get("/types", response_model=List[SourceTypeInfo])
def list_source_types():
    """List all supported source types."""
    return [
        SourceTypeInfo(
            type="slack",
            name="Slack",
            description="Receive messages from Slack channels",
            requires_integration=True,
            available=True,
        ),
        SourceTypeInfo(
            type="intercom",
            name="Intercom",
            description="Analyze support conversations with AI",
            requires_integration=True,
            available=True,
        ),
        SourceTypeInfo(
            type="webhook",
            name="Webhook",
            description="Receive data via HTTP POST requests",
            requires_integration=False,
            available=True,
        ),
        SourceTypeInfo(
            type="discord",
            name="Discord",
            description="Receive messages from Discord servers",
            requires_integration=True,
            available=False,  # Coming soon
        ),
        SourceTypeInfo(
            type="email",
            name="Email",
            description="Forward emails to become feedback",
            requires_integration=False,
            available=False,  # Coming soon
        ),
    ]


@router.get("/", response_model=FeedbackSourceListResponse)
def list_feedback_sources(
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all feedback sources for the organization."""
    query = db.query(FeedbackSource).filter(
        FeedbackSource.organization_id == current_org.id
    )

    if source_type:
        query = query.filter(FeedbackSource.source_type == source_type)
    if is_active is not None:
        query = query.filter(FeedbackSource.is_active == is_active)

    sources = query.order_by(FeedbackSource.created_at.desc()).all()

    # Add webhook URLs for webhook sources
    response_sources = []
    for source in sources:
        source_dict = {
            "id": source.id,
            "organization_id": source.organization_id,
            "integration_id": source.integration_id,
            "source_type": source.source_type,
            "name": source.name,
            "provider_config": source.provider_config or {},
            "triggers": source.triggers or {},
            "field_mapping": source.field_mapping or {},
            "auto_import": source.auto_import,
            "is_active": source.is_active,
            "last_event_at": source.last_event_at,
            "events_processed": source.events_processed or 0,
            "error_count": source.error_count or 0,
            "last_error": source.last_error,
            "created_at": source.created_at,
            "updated_at": source.updated_at,
            "webhook_url": None,
        }

        # Add webhook URL for webhook sources
        if source.source_type == "webhook":
            webhook_id = (source.provider_config or {}).get("webhook_id")
            if webhook_id:
                source_dict["webhook_url"] = _generate_webhook_url(webhook_id)

        response_sources.append(FeedbackSourceResponse(**source_dict))

    return FeedbackSourceListResponse(sources=response_sources, total=len(sources))


@router.post("/", response_model=FeedbackSourceResponse, status_code=status.HTTP_201_CREATED)
def create_feedback_source(
    data: FeedbackSourceCreate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new feedback source."""
    from src.config.plans import has_feature, get_plan_for_feature

    # Validate source type
    valid_types = ["slack", "intercom", "webhook", "discord", "email"]
    if data.source_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid source type. Must be one of: {valid_types}")

    # Feature gating based on source type
    plan = current_org.plan or "free"

    if data.source_type == "slack":
        if not has_feature(plan, "slack_integration"):
            required_plan = get_plan_for_feature("slack_integration")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_not_available",
                    "feature": "slack_integration",
                    "current_plan": plan,
                    "required_plan": required_plan,
                    "message": f"Slack integration requires the {required_plan.title()} plan or higher.",
                    "upgrade_url": "/settings/billing"
                }
            )

    if data.source_type == "intercom":
        if not has_feature(plan, "intercom_integration"):
            required_plan = get_plan_for_feature("intercom_integration")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_not_available",
                    "feature": "intercom_integration",
                    "current_plan": plan,
                    "required_plan": required_plan,
                    "message": f"Intercom integration requires the {required_plan.title()} plan or higher.",
                    "upgrade_url": "/settings/billing"
                }
            )

    if data.source_type == "webhook":
        if not has_feature(plan, "webhooks"):
            required_plan = get_plan_for_feature("webhooks")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_not_available",
                    "feature": "webhooks",
                    "current_plan": plan,
                    "required_plan": required_plan,
                    "message": f"Webhooks require the {required_plan.title()} plan or higher.",
                    "upgrade_url": "/settings/billing"
                }
            )

    # Check if type is available
    unavailable_types = ["discord", "email"]
    if data.source_type in unavailable_types:
        raise HTTPException(status_code=400, detail=f"Source type '{data.source_type}' is coming soon")

    # Validate integration for OAuth sources
    integration = None
    if data.source_type == "slack":
        if not data.integration_id:
            raise HTTPException(status_code=400, detail="Slack sources require an integration_id")

        integration = db.query(Integration).filter(
            Integration.id == data.integration_id,
            Integration.organization_id == current_org.id,
            Integration.type == "slack",
        ).first()

        if not integration:
            raise HTTPException(status_code=400, detail="Integration not found or not a Slack integration")

    if data.source_type == "intercom":
        if not data.integration_id:
            raise HTTPException(status_code=400, detail="Intercom sources require an integration_id")

        integration = db.query(Integration).filter(
            Integration.id == data.integration_id,
            Integration.organization_id == current_org.id,
            Integration.type == "intercom",
        ).first()

        if not integration:
            raise HTTPException(status_code=400, detail="Integration not found or not an Intercom integration")

    # Build provider_config
    provider_config = data.provider_config or {}

    # For Slack sources, copy team_id from integration
    if data.source_type == "slack" and integration:
        integration_config = integration.config or {}
        if integration_config.get("team_id"):
            provider_config["team_id"] = integration_config["team_id"]
        if integration_config.get("team_name"):
            provider_config["team_name"] = integration_config["team_name"]

    # For Intercom sources, copy workspace_id from integration
    if data.source_type == "intercom" and integration:
        integration_config = integration.config or {}
        if integration_config.get("workspace_id"):
            provider_config["workspace_id"] = integration_config["workspace_id"]
        if integration_config.get("workspace_name"):
            provider_config["workspace_name"] = integration_config["workspace_name"]

    if data.source_type == "webhook":
        webhook_id = str(uuid.uuid4())
        provider_config["webhook_id"] = webhook_id

    # Create the source
    source = FeedbackSource(
        organization_id=current_org.id,
        integration_id=data.integration_id,
        source_type=data.source_type,
        name=data.name,
        provider_config=provider_config,
        triggers=data.triggers.model_dump() if data.triggers else {},
        field_mapping=data.field_mapping.model_dump() if data.field_mapping else {},
        auto_import=data.auto_import,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    # Build response
    response_dict = {
        "id": source.id,
        "organization_id": source.organization_id,
        "integration_id": source.integration_id,
        "source_type": source.source_type,
        "name": source.name,
        "provider_config": source.provider_config or {},
        "triggers": source.triggers or {},
        "field_mapping": source.field_mapping or {},
        "auto_import": source.auto_import,
        "is_active": source.is_active,
        "last_event_at": source.last_event_at,
        "events_processed": source.events_processed or 0,
        "error_count": source.error_count or 0,
        "last_error": source.last_error,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
        "webhook_url": None,
    }

    if source.source_type == "webhook":
        response_dict["webhook_url"] = _generate_webhook_url(provider_config["webhook_id"])

    return FeedbackSourceResponse(**response_dict)


@router.get("/{source_id}", response_model=FeedbackSourceResponse)
def get_feedback_source(
    source_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get a specific feedback source."""
    source = _get_source_or_404(db, source_id, current_org.id)

    response_dict = {
        "id": source.id,
        "organization_id": source.organization_id,
        "integration_id": source.integration_id,
        "source_type": source.source_type,
        "name": source.name,
        "provider_config": source.provider_config or {},
        "triggers": source.triggers or {},
        "field_mapping": source.field_mapping or {},
        "auto_import": source.auto_import,
        "is_active": source.is_active,
        "last_event_at": source.last_event_at,
        "events_processed": source.events_processed or 0,
        "error_count": source.error_count or 0,
        "last_error": source.last_error,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
        "webhook_url": None,
    }

    if source.source_type == "webhook":
        webhook_id = (source.provider_config or {}).get("webhook_id")
        if webhook_id:
            response_dict["webhook_url"] = _generate_webhook_url(webhook_id)

    return FeedbackSourceResponse(**response_dict)


@router.patch("/{source_id}", response_model=FeedbackSourceResponse)
def update_feedback_source(
    source_id: int,
    data: FeedbackSourceUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update a feedback source."""
    source = _get_source_or_404(db, source_id, current_org.id)

    if data.name is not None:
        source.name = data.name
    if data.provider_config is not None:
        # Preserve webhook_id for webhook sources
        if source.source_type == "webhook":
            existing_webhook_id = (source.provider_config or {}).get("webhook_id")
            if existing_webhook_id:
                data.provider_config["webhook_id"] = existing_webhook_id
        source.provider_config = data.provider_config
    if data.triggers is not None:
        source.triggers = data.triggers.model_dump()
    if data.field_mapping is not None:
        source.field_mapping = data.field_mapping.model_dump()
    if data.auto_import is not None:
        source.auto_import = data.auto_import
    if data.is_active is not None:
        source.is_active = data.is_active

    db.commit()
    db.refresh(source)

    response_dict = {
        "id": source.id,
        "organization_id": source.organization_id,
        "integration_id": source.integration_id,
        "source_type": source.source_type,
        "name": source.name,
        "provider_config": source.provider_config or {},
        "triggers": source.triggers or {},
        "field_mapping": source.field_mapping or {},
        "auto_import": source.auto_import,
        "is_active": source.is_active,
        "last_event_at": source.last_event_at,
        "events_processed": source.events_processed or 0,
        "error_count": source.error_count or 0,
        "last_error": source.last_error,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
        "webhook_url": None,
    }

    if source.source_type == "webhook":
        webhook_id = (source.provider_config or {}).get("webhook_id")
        if webhook_id:
            response_dict["webhook_url"] = _generate_webhook_url(webhook_id)

    return FeedbackSourceResponse(**response_dict)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback_source(
    source_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a feedback source."""
    source = _get_source_or_404(db, source_id, current_org.id)
    db.delete(source)
    db.commit()


@router.get("/{source_id}/events", response_model=List[FeedbackSourceEventResponse])
def list_source_events(
    source_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List events for a feedback source."""
    source = _get_source_or_404(db, source_id, current_org.id)

    query = db.query(FeedbackSourceEvent).filter(
        FeedbackSourceEvent.source_id == source.id
    )

    if status:
        query = query.filter(FeedbackSourceEvent.status == status)

    events = query.order_by(FeedbackSourceEvent.received_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return events


# ============ Provider-Specific Endpoints ============

@router.get("/{source_id}/slack/channels", response_model=List[ChannelInfo])
def list_slack_channels(
    source_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List available Slack channels for a source."""
    import httpx

    source = _get_source_or_404(db, source_id, current_org.id)

    if source.source_type != "slack":
        raise HTTPException(status_code=400, detail="Source is not a Slack source")

    if not source.integration_id:
        raise HTTPException(status_code=400, detail="Source has no linked integration")

    # Get the integration for OAuth token
    integration = db.query(Integration).filter(
        Integration.id == source.integration_id,
        Integration.organization_id == current_org.id,
    ).first()

    if not integration or not integration.oauth_access_token:
        raise HTTPException(status_code=400, detail="Integration has no OAuth token")

    # Fetch channels from Slack API
    channels = []
    cursor = None

    try:
        with httpx.Client(timeout=30) as client:
            while True:
                params = {"limit": 200, "types": "public_channel,private_channel"}
                if cursor:
                    params["cursor"] = cursor

                response = client.get(
                    "https://slack.com/api/conversations.list",
                    headers={"Authorization": f"Bearer {integration.oauth_access_token}"},
                    params=params
                )
                data = response.json()

                if data.get("ok"):
                    channels.extend(data.get("channels", []))
                    cursor = data.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                else:
                    logger.error(f"Slack API error: {data.get('error')}")
                    break
    except Exception as e:
        logger.error(f"Failed to fetch Slack channels: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch channels from Slack")

    # Check which channels are already configured
    configured_channel_id = (source.provider_config or {}).get("channel_id")

    return [
        ChannelInfo(
            id=ch["id"],
            name=ch["name"],
            is_private=ch.get("is_private", False),
            is_configured=ch["id"] == configured_channel_id,
        )
        for ch in channels
    ]
