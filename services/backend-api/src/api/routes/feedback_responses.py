"""
Feedback Responses endpoints.

Endpoints (all nested under /api/v1/feedback/{feedback_id}):
  GET  /responses          — List response history for a feedback item
  POST /responses/generate — AI-generate a response (counts against monthly limit)
  POST /responses/send     — Save/send a response (clipboard or integration channel)
"""

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_feature
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.feedback_response import FeedbackResponse
from src.models.organization import Organization
from src.models.user import User
from src.services.response_generator import generate_response, resolve_variables
from src.api.routes.response_settings import PLAN_AI_RESPONSE_LIMITS

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["feedback-responses"],
    dependencies=[Depends(require_feature("response_suggestions"))],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class FeedbackResponseOut(BaseModel):
    id: int
    feedback_id: int
    user_id: Optional[int] = None
    response_text: str
    channel: str
    source: str
    template_id: Optional[int] = None
    tone: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: str
    user_name: Optional[str] = None

    class Config:
        from_attributes = True


class GenerateResponseRequest(BaseModel):
    tone: Optional[str] = None  # overrides org default


class GenerateResponseResult(BaseModel):
    response_text: str
    tokens_used: int
    remaining_this_month: int


class SendResponseRequest(BaseModel):
    response_text: str
    channel: Literal["clipboard", "slack", "intercom", "linear", "email"]
    source: Literal["template", "ai_generated", "manual"]
    template_id: Optional[int] = None
    tone: Optional[str] = None


class SendResponseResult(BaseModel):
    success: bool
    response_id: int
    channel: str
    error: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================


def _get_feedback_or_404(
    feedback_id: int,
    org_id: int,
    db: Session,
) -> FeedbackItem:
    feedback = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == feedback_id,
            FeedbackItem.organization_id == org_id,
        )
        .first()
    )
    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback item {feedback_id} not found",
        )
    return feedback


def _user_display_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    if hasattr(user, "name") and user.name:
        return user.name
    return user.email.split("@")[0]


def _get_remaining_this_month(org: Organization, plan: str) -> int:
    monthly_limit = PLAN_AI_RESPONSE_LIMITS.get(plan, 0)
    if monthly_limit == -1:
        return -1  # unlimited
    used = org.ai_responses_generated or 0
    return max(0, monthly_limit - used)


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/{feedback_id}/responses", response_model=List[FeedbackResponseOut])
def list_responses(
    feedback_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all responses recorded for a feedback item (newest first)."""
    # Verify feedback belongs to org
    _get_feedback_or_404(feedback_id, current_org.id, db)

    responses = (
        db.query(FeedbackResponse)
        .filter(
            FeedbackResponse.feedback_id == feedback_id,
            FeedbackResponse.organization_id == current_org.id,
        )
        .order_by(FeedbackResponse.created_at.desc())
        .all()
    )

    result = []
    for r in responses:
        user = db.query(User).filter(User.id == r.user_id).first() if r.user_id else None
        result.append(
            FeedbackResponseOut(
                id=r.id,
                feedback_id=r.feedback_id,
                user_id=r.user_id,
                response_text=r.response_text,
                channel=r.channel,
                source=r.source,
                template_id=r.template_id,
                tone=r.tone,
                status=r.status,
                error_message=r.error_message,
                created_at=r.created_at.isoformat() if r.created_at else "",
                user_name=_user_display_name(user),
            )
        )
    return result


@router.post("/{feedback_id}/responses/generate", response_model=GenerateResponseResult)
async def generate_ai_response(
    feedback_id: int,
    data: GenerateResponseRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI-generate a response for a feedback item.

    Checks the monthly AI response limit, calls the LLM, increments the usage
    counter, and returns the generated text with remaining quota.
    """
    feedback = _get_feedback_or_404(feedback_id, current_org.id, db)
    plan = current_org.plan or "free"

    # Check usage limit
    monthly_limit = PLAN_AI_RESPONSE_LIMITS.get(plan, 0)
    used = current_org.ai_responses_generated or 0
    if monthly_limit != -1 and used >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "ai_response_limit_exceeded",
                "limit": monthly_limit,
                "used": used,
                "message": f"You've used all {monthly_limit} AI responses for this month.",
                "upgrade_url": "/settings/billing",
            },
        )

    try:
        result = await generate_response(
            feedback=feedback,
            org=current_org,
            user=current_user,
            tone=data.tone,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI generation failed: {str(exc)}",
        )
    except Exception as exc:
        logger.error(f"AI generation error for feedback {feedback_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation failed. Please try again.",
        )

    # Increment counter
    current_org.ai_responses_generated = (current_org.ai_responses_generated or 0) + 1
    db.commit()
    db.refresh(current_org)

    remaining = _get_remaining_this_month(current_org, plan)

    return GenerateResponseResult(
        response_text=result["response_text"],
        tokens_used=result["tokens_used"],
        remaining_this_month=remaining,
    )


@router.post("/{feedback_id}/responses/send", response_model=SendResponseResult)
async def send_response(
    feedback_id: int,
    data: SendResponseRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save a response and optionally send it via an integration channel.

    For 'clipboard': saves with status='copied'.
    For integration channels: attempts to send, saves with status='sent' or 'send_failed'.
    """
    feedback = _get_feedback_or_404(feedback_id, current_org.id, db)

    send_error: Optional[str] = None
    final_status: str

    if data.channel == "clipboard":
        final_status = "copied"
    else:
        # Attempt to send via the requested channel
        send_result = await _dispatch_send(data.channel, data.response_text, feedback, current_org, db)
        if send_result["success"]:
            final_status = "sent"
            send_error = None
        else:
            final_status = "send_failed"
            send_error = send_result.get("error")

    # Always save to feedback_responses
    response_record = FeedbackResponse(
        feedback_id=feedback_id,
        organization_id=current_org.id,
        user_id=current_user.id,
        response_text=data.response_text,
        channel=data.channel,
        source=data.source,
        template_id=data.template_id,
        tone=data.tone,
        status=final_status,
        error_message=send_error,
    )
    db.add(response_record)
    db.commit()
    db.refresh(response_record)

    return SendResponseResult(
        success=(final_status != "send_failed"),
        response_id=response_record.id,
        channel=data.channel,
        error=send_error,
    )


async def _dispatch_send(
    channel: str,
    response_text: str,
    feedback: FeedbackItem,
    org: Organization,
    db: Session,
) -> dict:
    """Route the send request to the correct integration handler."""
    from src.services import response_sender

    if channel == "slack":
        # Look up the org's Slack integration token
        access_token = _get_integration_token(org.id, "slack", db)
        if not access_token:
            return {"success": False, "error": "Slack integration not connected"}
        return await response_sender.send_via_slack(response_text, feedback, org, access_token)

    if channel == "intercom":
        access_token = _get_integration_token(org.id, "intercom", db)
        if not access_token:
            return {"success": False, "error": "Intercom integration not connected"}
        return await response_sender.send_via_intercom(response_text, feedback, org, access_token)

    if channel == "linear":
        access_token = _get_integration_token(org.id, "linear", db)
        if not access_token:
            return {"success": False, "error": "Linear integration not connected"}
        return await response_sender.send_via_linear(response_text, feedback, org, access_token)

    if channel == "email":
        customer_email = feedback.customer_email
        if not customer_email:
            return {"success": False, "error": "No customer email on this feedback item"}
        return await response_sender.send_via_email(response_text, feedback, org, customer_email)

    return {"success": False, "error": f"Unknown channel: {channel}"}


def _get_integration_token(org_id: int, provider: str, db: Session) -> Optional[str]:
    """
    Retrieve the active access token for an integration provider.
    Supports: slack, intercom, linear.
    """
    if provider == "linear":
        try:
            from src.models.linear_integration import LinearIntegration
            integration = (
                db.query(LinearIntegration)
                .filter(
                    LinearIntegration.organization_id == org_id,
                    LinearIntegration.is_active.is_(True),
                )
                .first()
            )
            return integration.access_token if integration else None
        except Exception:
            return None

    # For Slack and Intercom, use the generic Integration model
    try:
        from src.models.integration import Integration
        integration = (
            db.query(Integration)
            .filter(
                Integration.organization_id == org_id,
                Integration.provider == provider,
                Integration.is_active.is_(True),
            )
            .first()
        )
        if integration is None:
            return None
        # Access token may be stored in config JSON
        config = integration.config or {}
        return config.get("access_token") or getattr(integration, "access_token", None)
    except Exception:
        return None
