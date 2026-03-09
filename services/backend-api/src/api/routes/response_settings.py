"""
Response Settings endpoints — brand voice, tone, product name, support email.

Endpoints:
  GET  /api/v1/response-settings         — Get org response settings
  PUT  /api/v1/response-settings         — Update settings (admin/owner)
  GET  /api/v1/response-settings/usage   — AI response usage this month
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_usage,
    require_admin_or_owner,
    require_feature,
)
from src.database.session import get_db
from src.models.feedback_response import FeedbackResponse
from src.models.organization import Organization
from src.models.usage import UsageRecord

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/response-settings",
    tags=["response-settings"],
    dependencies=[Depends(require_feature("response_suggestions"))],
)

# Monthly AI response limits per plan
PLAN_AI_RESPONSE_LIMITS = {
    "free": 0,
    "pro": 50,
    "business": 500,
    "enterprise": -1,  # unlimited
}


# ============================================================================
# Pydantic Schemas
# ============================================================================


class ResponseSettingsOut(BaseModel):
    brand_voice: Optional[str] = None
    default_tone: Optional[str] = None
    product_name_display: Optional[str] = None
    support_email_display: Optional[str] = None

    class Config:
        from_attributes = True


class UpdateResponseSettingsRequest(BaseModel):
    brand_voice: Optional[str] = Field(None, max_length=500)
    default_tone: Optional[str] = Field(None, max_length=50)
    product_name_display: Optional[str] = Field(None, max_length=200)
    support_email_display: Optional[str] = Field(None, max_length=200)


class ResponseUsageOut(BaseModel):
    ai_responses_generated: int
    monthly_limit: int  # -1 = unlimited
    templates_used: int
    responses_sent: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=ResponseSettingsOut)
def get_response_settings(
    current_org: Organization = Depends(get_current_org),
):
    """Return org-wide response settings (brand voice, tone, product name, support email)."""
    return ResponseSettingsOut(
        brand_voice=current_org.brand_voice,
        default_tone=current_org.default_tone,
        product_name_display=current_org.product_name_display,
        support_email_display=current_org.support_email_display,
    )


@router.put(
    "",
    response_model=ResponseSettingsOut,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_response_settings(
    data: UpdateResponseSettingsRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update org-wide response settings (admin/owner only)."""
    if data.brand_voice is not None:
        current_org.brand_voice = data.brand_voice
    if data.default_tone is not None:
        current_org.default_tone = data.default_tone
    if data.product_name_display is not None:
        current_org.product_name_display = data.product_name_display
    if data.support_email_display is not None:
        current_org.support_email_display = data.support_email_display

    db.commit()
    db.refresh(current_org)

    return ResponseSettingsOut(
        brand_voice=current_org.brand_voice,
        default_tone=current_org.default_tone,
        product_name_display=current_org.product_name_display,
        support_email_display=current_org.support_email_display,
    )


@router.get("/usage", response_model=ResponseUsageOut)
def get_response_usage(
    current_org: Organization = Depends(get_current_org),
    usage: UsageRecord = Depends(get_current_usage),
    db: Session = Depends(get_db),
):
    """Return AI response usage for the current billing period."""
    plan = current_org.plan or "free"
    monthly_limit = PLAN_AI_RESPONSE_LIMITS.get(plan, 0)

    # Count templates used — FeedbackResponses this period where source = 'template'
    templates_used = (
        db.query(FeedbackResponse)
        .filter(
            FeedbackResponse.organization_id == current_org.id,
            FeedbackResponse.created_at >= usage.period_start,
            FeedbackResponse.created_at < usage.period_end,
            FeedbackResponse.source == "template",
        )
        .count()
    )

    # Count responses sent (all channels except clipboard counts as "sent")
    responses_sent = (
        db.query(FeedbackResponse)
        .filter(
            FeedbackResponse.organization_id == current_org.id,
            FeedbackResponse.created_at >= usage.period_start,
            FeedbackResponse.created_at < usage.period_end,
            FeedbackResponse.channel != "clipboard",
            FeedbackResponse.status == "sent",
        )
        .count()
    )

    return ResponseUsageOut(
        ai_responses_generated=current_org.ai_responses_generated or 0,
        monthly_limit=monthly_limit,
        templates_used=templates_used,
        responses_sent=responses_sent,
    )
