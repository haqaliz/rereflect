"""
Admin Organization management API endpoints.
All endpoints require system admin access.
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from src.database.session import get_db
from src.api.dependencies import require_system_admin
from src.models.organization import Organization
from src.models.user import User

router = APIRouter(prefix="/api/v1/admin/organizations", tags=["admin-organizations"])


# Schemas

class AdminOrgUser(BaseModel):
    id: int
    email: str
    role: str
    is_system_admin: bool
    last_active_at: Optional[datetime] = None


class AdminOrgResponse(BaseModel):
    id: int
    name: str
    plan: str
    user_count: int
    stripe_customer_id: Optional[str] = None
    promo_code_used: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminOrgListResponse(BaseModel):
    organizations: List[AdminOrgResponse]
    total: int
    page: int
    page_size: int


class AdminOrgDetailResponse(AdminOrgResponse):
    users: List[AdminOrgUser] = []
    seat_count: int
    max_seats: Optional[int] = None
    ai_analysis_enabled: bool
    auto_assignment_enabled: bool


# Endpoints

@router.get("", response_model=AdminOrgListResponse, dependencies=[Depends(require_system_admin)])
def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all organizations with user counts."""
    # Subquery for user count
    user_count_subq = (
        db.query(
            User.organization_id,
            func.count(User.id).label("user_count"),
        )
        .group_by(User.organization_id)
        .subquery()
    )

    query = db.query(Organization, func.coalesce(user_count_subq.c.user_count, 0).label("user_count")).outerjoin(
        user_count_subq, Organization.id == user_count_subq.c.organization_id
    )

    if search:
        query = query.filter(Organization.name.ilike(f"%{search}%"))

    total = query.count()

    results = (
        query
        .order_by(Organization.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return AdminOrgListResponse(
        organizations=[
            AdminOrgResponse(
                id=org.id,
                name=org.name,
                plan=org.plan,
                user_count=user_count,
                stripe_customer_id=org.stripe_customer_id,
                promo_code_used=org.promo_code_used,
                created_at=org.created_at,
            )
            for org, user_count in results
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{org_id}", response_model=AdminOrgDetailResponse, dependencies=[Depends(require_system_admin)])
def get_organization(org_id: int, db: Session = Depends(get_db)):
    """Get organization detail with its users."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    users = db.query(User).filter(User.organization_id == org_id).order_by(User.created_at).all()

    return AdminOrgDetailResponse(
        id=org.id,
        name=org.name,
        plan=org.plan,
        user_count=len(users),
        stripe_customer_id=org.stripe_customer_id,
        promo_code_used=org.promo_code_used,
        created_at=org.created_at,
        seat_count=org.seat_count,
        max_seats=org.max_seats,
        ai_analysis_enabled=org.ai_analysis_enabled,
        auto_assignment_enabled=org.auto_assignment_enabled,
        users=[
            AdminOrgUser(
                id=u.id,
                email=u.email,
                role=u.role,
                is_system_admin=u.is_system_admin,
                last_active_at=u.last_active_at,
            )
            for u in users
        ],
    )
