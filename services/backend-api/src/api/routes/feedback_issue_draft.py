"""
AI-drafted issue content endpoint.

  POST /api/v1/feedback/{feedback_id}/issue-draft — draft a {title, body}
  work-tracker (Jira/Asana) issue from a feedback item using the org's
  configured LLM.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, get_current_user, require_admin_or_owner
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.services.issue_drafter import (
    IssueDraftError,
    LLMNotConfiguredError,
    draft_issue_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class IssueDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["jira", "asana"]
    tone: Optional[str] = None


class IssueDraftResponse(BaseModel):
    title: str
    body: str


# ============================================================================
# Helpers
# ============================================================================


def _get_feedback_or_404(feedback_id: int, org_id: int, db: Session) -> FeedbackItem:
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


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/{feedback_id}/issue-draft",
    response_model=IssueDraftResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
async def create_issue_draft(
    feedback_id: int,
    payload: IssueDraftRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-draft a {title, body} issue for the given feedback item."""
    feedback = _get_feedback_or_404(feedback_id, current_org.id, db)

    try:
        draft = await draft_issue_content(feedback, current_org, payload.target, db, payload.tone)
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc)
            or "No AI model configured. Configure a provider in AI Settings or set a local LLM to use AI drafting.",
        )
    except IssueDraftError as exc:
        logger.warning("issue-draft: unusable model output for feedback %s: %s", feedback_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI model returned an unusable draft. Try again.",
        )
    except Exception as exc:
        logger.error("issue-draft: provider error for feedback %s: %s", feedback_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI drafting failed due to an upstream error. Try again.",
        )

    return IssueDraftResponse(title=draft["title"], body=draft["body"])
