"""
Response Templates CRUD + suggestion endpoint.

Endpoints:
  GET    /api/v1/response-templates          — List all (system + org custom)
  POST   /api/v1/response-templates          — Create custom template (admin/owner)
  GET    /api/v1/response-templates/{id}     — Get single template
  PUT    /api/v1/response-templates/{id}     — Update custom template (admin/owner)
  DELETE /api/v1/response-templates/{id}     — Delete custom template (admin/owner)
  POST   /api/v1/response-templates/suggest  — Best template for a feedback item
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
    require_feature,
)
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.response_template import ResponseTemplate
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/response-templates",
    tags=["response-templates"],
    dependencies=[Depends(require_feature("response_suggestions"))],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class ResponseTemplateOut(BaseModel):
    id: int
    organization_id: Optional[int] = None
    name: str
    category: str
    body: str
    is_system: bool
    usage_count: int

    class Config:
        from_attributes = True


class ListTemplatesResponse(BaseModel):
    templates: List[ResponseTemplateOut]


class CreateTemplateRequest(BaseModel):
    name: str = Field(..., max_length=200)
    category: str = Field(..., max_length=100)
    body: str = Field(...)


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    body: Optional[str] = None


class SuggestTemplateRequest(BaseModel):
    feedback_id: int


class SuggestTemplateResponse(BaseModel):
    template: Optional[ResponseTemplateOut] = None
    score: int


# ============================================================================
# Scoring algorithm (PRD Section 7)
# ============================================================================

# Sentiment name → list of template names that align with that sentiment
SENTIMENT_TEMPLATE_MAP = {
    "positive": ["Positive Feedback Thanks"],
    "negative": ["General Complaint Response", "Bug Report Acknowledgment", "Churn Risk Outreach"],
    "neutral": ["Feature Request Acknowledgment", "Follow-up Check-in"],
}

MIN_SCORE_THRESHOLD = 10


def _score_template(template: ResponseTemplate, feedback: FeedbackItem) -> int:
    """Return a relevance score for a template given a feedback item."""
    score = 0

    # Category match is the strongest signal.
    # The feedback's pain_point_category is used as the primary category field.
    feedback_category = feedback.pain_point_category or ""

    if template.category and feedback_category:
        if template.category.lower() == feedback_category.lower():
            score += 50

    # Sentiment alignment
    sentiment = (feedback.sentiment_label or "").lower()
    if template.name in SENTIMENT_TEMPLATE_MAP.get(sentiment, []):
        score += 20

    # Urgency match
    if feedback.is_urgent and template.category == "Urgent":
        score += 30

    # Churn risk match
    churn_score = feedback.churn_risk_score or 0
    if churn_score > 70 and template.category == "Churn Risk":
        score += 25

    return score


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=ListTemplatesResponse)
def list_templates(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all response templates visible to this org (system + own custom)."""
    templates = (
        db.query(ResponseTemplate)
        .filter(
            or_(
                ResponseTemplate.is_system.is_(True),
                ResponseTemplate.organization_id == current_org.id,
            )
        )
        .order_by(ResponseTemplate.is_system.desc(), ResponseTemplate.id.asc())
        .all()
    )
    return ListTemplatesResponse(templates=templates)


@router.post(
    "",
    response_model=ResponseTemplateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_owner)],
)
def create_template(
    data: CreateTemplateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a custom response template for this org (admin/owner only)."""
    template = ResponseTemplate(
        organization_id=current_org.id,
        name=data.name,
        category=data.category,
        body=data.body,
        is_system=False,
        usage_count=0,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    logger.info(f"Created custom template '{template.name}' for org {current_org.id}")
    return template


@router.get("/{template_id}", response_model=ResponseTemplateOut)
def get_template(
    template_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get a single template by ID. System templates are accessible to all orgs."""
    template = db.query(ResponseTemplate).filter(ResponseTemplate.id == template_id).first()

    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Custom templates are only accessible to the owning org
    if not template.is_system and template.organization_id != current_org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    return template


@router.put(
    "/{template_id}",
    response_model=ResponseTemplateOut,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_template(
    template_id: int,
    data: UpdateTemplateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update a custom template. System templates cannot be edited."""
    template = db.query(ResponseTemplate).filter(ResponseTemplate.id == template_id).first()

    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if template.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System templates cannot be edited",
        )

    if template.organization_id != current_org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if data.name is not None:
        template.name = data.name
    if data.category is not None:
        template.category = data.category
    if data.body is not None:
        template.body = data.body

    db.commit()
    db.refresh(template)
    return template


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_owner)],
)
def delete_template(
    template_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a custom template. System templates cannot be deleted."""
    template = db.query(ResponseTemplate).filter(ResponseTemplate.id == template_id).first()

    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if template.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System templates cannot be deleted",
        )

    if template.organization_id != current_org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    db.delete(template)
    db.commit()


@router.post("/suggest", response_model=SuggestTemplateResponse)
def suggest_template(
    data: SuggestTemplateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return the best-matching template for a feedback item using the scoring algorithm."""
    feedback = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == data.feedback_id,
            FeedbackItem.organization_id == current_org.id,
        )
        .first()
    )
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback item not found")

    # Score all templates visible to this org
    templates = (
        db.query(ResponseTemplate)
        .filter(
            or_(
                ResponseTemplate.is_system.is_(True),
                ResponseTemplate.organization_id == current_org.id,
            )
        )
        .all()
    )

    best_template = None
    best_score = 0

    for tmpl in templates:
        score = _score_template(tmpl, feedback)
        if score > best_score:
            best_score = score
            best_template = tmpl

    if best_score <= MIN_SCORE_THRESHOLD:
        return SuggestTemplateResponse(template=None, score=0)

    return SuggestTemplateResponse(template=best_template, score=best_score)
