"""
Custom categories API endpoints.
Allows organizations to define custom categories for AI-powered categorization.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime

from src.database.session import get_db
from src.models.custom_category import CustomCategory
from src.models.organization import Organization
from src.api.dependencies import get_current_user, get_current_org, require_admin_or_owner

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


# Schemas
class CustomCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    category_type: str = Field(pattern="^(pain_point|feature_request|general)$")


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
    query = db.query(CustomCategory).filter(
        CustomCategory.organization_id == current_org.id,
    )
    if category_type:
        query = query.filter(CustomCategory.category_type == category_type)

    return query.order_by(CustomCategory.name).all()


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
    # Check for duplicate name within org + type
    existing = db.query(CustomCategory).filter(
        CustomCategory.organization_id == current_org.id,
        CustomCategory.name == data.name,
        CustomCategory.category_type == data.category_type,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {data.category_type} category named '{data.name}' already exists",
        )

    category = CustomCategory(
        organization_id=current_org.id,
        name=data.name,
        description=data.description,
        category_type=data.category_type,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


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
    category = db.query(CustomCategory).filter(
        CustomCategory.id == category_id,
        CustomCategory.organization_id == current_org.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if data.name is not None:
        # Check for duplicate name
        existing = db.query(CustomCategory).filter(
            CustomCategory.organization_id == current_org.id,
            CustomCategory.name == data.name,
            CustomCategory.category_type == category.category_type,
            CustomCategory.id != category_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A category named '{data.name}' already exists",
            )
        category.name = data.name

    if data.description is not None:
        category.description = data.description
    if data.is_active is not None:
        category.is_active = data.is_active

    db.commit()
    db.refresh(category)
    return category


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
    category = db.query(CustomCategory).filter(
        CustomCategory.id == category_id,
        CustomCategory.organization_id == current_org.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.delete(category)
    db.commit()
