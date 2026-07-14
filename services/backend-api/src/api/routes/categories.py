"""
Custom categories API endpoints.
Allows organizations to define custom categories for AI-powered categorization.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, model_validator
from datetime import datetime

from src.database.session import get_db
from src.models.custom_category import CustomCategory
from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig
from src.api.dependencies import get_current_user, get_current_org, require_admin_or_owner
from src.services import custom_category_service as category_service

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


# Schemas
class CustomCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    category_type: str = Field(pattern="^(pain_point|feature_request|urgency|general)$")


class CustomCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CustomCategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    category_type: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get(
    "/custom",
    response_model=List[CustomCategoryResponse],
)
def list_custom_categories(
    category_type: Optional[str] = None,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List custom categories for the current organization."""
    return category_service.list_categories(db, current_org.id, category_type)


@router.post(
    "/custom",
    response_model=CustomCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_owner)],
)
def create_custom_category(
    data: CustomCategoryCreate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new custom category. Admin or Owner only."""
    try:
        return category_service.create_category(
            db,
            current_org.id,
            name=data.name,
            description=data.description,
            category_type=data.category_type,
        )
    except category_service.DuplicateCategoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.patch(
    "/custom/{category_id}",
    response_model=CustomCategoryResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_custom_category(
    category_id: int,
    data: CustomCategoryUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update a custom category. Admin or Owner only."""
    try:
        return category_service.update_category(
            db,
            current_org.id,
            category_id,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
    except category_service.CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Category not found")
    except category_service.DuplicateCategoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete(
    "/custom/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_owner)],
)
def delete_custom_category(
    category_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a custom category. Admin or Owner only."""
    try:
        category_service.delete_category(db, current_org.id, category_id)
    except category_service.CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Category not found")


# ── Health weights ──────────────────────────────────────────────────────────

_DEFAULT_WEIGHTS = {
    "churn": 35, "sentiment": 25, "resolution": 25,
    "frequency": 15, "usage": 0, "crm": 0,
}


class HealthWeightsResponse(BaseModel):
    churn: int
    sentiment: int
    resolution: int
    frequency: int
    usage: int = 0   # Opt-in usage component; 0 = disabled
    crm: int = 0     # Opt-in CRM component weight; 0 = disabled


class HealthWeightsUpdate(BaseModel):
    churn: int = Field(..., ge=0, le=100)
    sentiment: int = Field(..., ge=0, le=100)
    resolution: int = Field(..., ge=0, le=100)
    frequency: int = Field(..., ge=0, le=100)
    usage: int = Field(default=0, ge=0, le=100)  # Optional; defaults to 0
    crm: int = Field(default=0, ge=0, le=100)    # Optional; defaults to 0

    @model_validator(mode="after")
    def validate_sum_is_100(self) -> "HealthWeightsUpdate":
        total = (self.churn + self.sentiment + self.resolution +
                 self.frequency + self.usage + self.crm)
        if total != 100:
            raise ValueError(f"Health weights must sum to exactly 100, got {total}")
        return self


@router.get("/health-weights", response_model=HealthWeightsResponse)
def get_health_weights(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return the organization's health-score weights, or defaults if none configured."""
    config = db.query(OrgAIConfig).filter_by(organization_id=current_org.id).first()
    if config is not None:
        return HealthWeightsResponse(
            churn=config.health_weight_churn,
            sentiment=config.health_weight_sentiment,
            resolution=config.health_weight_resolution,
            frequency=config.health_weight_frequency,
            usage=config.health_weight_usage,
            crm=config.health_weight_crm,
        )
    return HealthWeightsResponse(**_DEFAULT_WEIGHTS)


@router.put(
    "/health-weights",
    response_model=HealthWeightsResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_health_weights(
    data: HealthWeightsUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Persist per-org health-score weights. Admin or Owner only. Must sum to 100."""
    config = db.query(OrgAIConfig).filter_by(organization_id=current_org.id).first()
    if config is None:
        config = OrgAIConfig(organization_id=current_org.id)
        db.add(config)

    config.health_weight_churn = data.churn
    config.health_weight_sentiment = data.sentiment
    config.health_weight_resolution = data.resolution
    config.health_weight_frequency = data.frequency
    config.health_weight_usage = data.usage
    config.health_weight_crm = data.crm

    db.commit()
    db.refresh(config)
    return HealthWeightsResponse(
        churn=config.health_weight_churn,
        sentiment=config.health_weight_sentiment,
        resolution=config.health_weight_resolution,
        frequency=config.health_weight_frequency,
        usage=config.health_weight_usage,
        crm=config.health_weight_crm,
    )
