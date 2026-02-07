"""
AI settings API endpoints.
Manage AI analysis configuration for the organization.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org, require_admin_or_owner, require_owner

router = APIRouter(prefix="/api/v1/settings/ai", tags=["ai-settings"])


class AISettingsResponse(BaseModel):
    ai_analysis_enabled: bool
    has_custom_key: bool


class AISettingsUpdate(BaseModel):
    ai_analysis_enabled: Optional[bool] = None
    openai_api_key: Optional[str] = None  # Set to empty string to remove


@router.get("", response_model=AISettingsResponse)
def get_ai_settings(
    current_org: Organization = Depends(get_current_org),
):
    """Get AI analysis settings for the organization."""
    return AISettingsResponse(
        ai_analysis_enabled=current_org.ai_analysis_enabled,
        has_custom_key=bool(current_org.openai_api_key),
    )


@router.patch(
    "",
    response_model=AISettingsResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_ai_settings(
    data: AISettingsUpdate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update AI analysis settings. Admin+ can toggle, Owner only for API key."""
    if data.ai_analysis_enabled is not None:
        current_org.ai_analysis_enabled = data.ai_analysis_enabled

    if data.openai_api_key is not None:
        # Only owners can set BYOK key
        if current_user.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the organization owner can manage API keys",
            )
        # Empty string removes the key
        current_org.openai_api_key = data.openai_api_key if data.openai_api_key else None

    db.commit()
    db.refresh(current_org)

    return AISettingsResponse(
        ai_analysis_enabled=current_org.ai_analysis_enabled,
        has_custom_key=bool(current_org.openai_api_key),
    )
