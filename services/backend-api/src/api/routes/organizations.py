from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


# Schemas
class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None


class OrganizationResponse(BaseModel):
    id: int
    name: str
    plan: str
    stripe_customer_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationStatsResponse(BaseModel):
    total_users: int
    total_feedback: int
    plan: str


# Endpoints
@router.get("/me", response_model=OrganizationResponse)
def get_my_organization(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get current user's organization."""
    return current_org


@router.patch("/me", response_model=OrganizationResponse)
def update_my_organization(
    data: OrganizationUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Update current organization (admin only)."""

    # Check if user is admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins can update organization settings"
        )

    # Update fields
    if data.name is not None:
        current_org.name = data.name

    if data.plan is not None:
        # Validate plan
        valid_plans = ["free", "starter", "professional", "business", "enterprise"]
        if data.plan not in valid_plans:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid plan. Must be one of: {', '.join(valid_plans)}"
            )
        current_org.plan = data.plan

    db.commit()
    db.refresh(current_org)

    return current_org


@router.get("/me/stats", response_model=OrganizationStatsResponse)
def get_organization_stats(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get organization statistics."""
    from src.models.user import User
    from src.models.feedback import FeedbackItem

    total_users = db.query(User).filter(
        User.organization_id == current_org.id
    ).count()

    total_feedback = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id
    ).count()

    return OrganizationStatsResponse(
        total_users=total_users,
        total_feedback=total_feedback,
        plan=current_org.plan
    )
