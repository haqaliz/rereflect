"""
Admin User management API endpoints.
All endpoints require system admin access.
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel

from src.database.session import get_db
from src.api.dependencies import get_current_user, require_system_admin
from src.models.user import User
from src.models.organization import Organization
from src.services.user_service import cleanup_and_delete_user

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


# Schemas

class AdminUserResponse(BaseModel):
    id: int
    email: str
    role: str
    organization_id: int
    organization_name: str
    plan: str
    is_system_admin: bool
    auth_provider: str
    created_at: datetime
    last_active_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    users: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


class AdminUserUpdate(BaseModel):
    organization_id: Optional[int] = None
    role: Optional[str] = None
    is_system_admin: Optional[bool] = None


# Endpoints

@router.get("", response_model=AdminUserListResponse, dependencies=[Depends(require_system_admin)])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """List all users across all organizations."""
    query = db.query(User).options(joinedload(User.organization))

    if search:
        query = query.filter(User.email.ilike(f"%{search}%"))

    if organization_id:
        query = query.filter(User.organization_id == organization_id)

    total = query.count()

    users = (
        query
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return AdminUserListResponse(
        users=[
            AdminUserResponse(
                id=u.id,
                email=u.email,
                role=u.role,
                organization_id=u.organization_id,
                organization_name=u.organization.name if u.organization else "Unknown",
                plan=u.organization.plan if u.organization else "free",
                is_system_admin=u.is_system_admin,
                auth_provider=u.auth_provider or "email",
                created_at=u.created_at,
                last_active_at=u.last_active_at,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=AdminUserResponse, dependencies=[Depends(require_system_admin)])
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a single user by ID."""
    user = db.query(User).options(joinedload(User.organization)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else "Unknown",
        plan=user.organization.plan if user.organization else "free",
        is_system_admin=user.is_system_admin,
        auth_provider=user.auth_provider or "email",
        created_at=user.created_at,
        last_active_at=user.last_active_at,
    )


@router.patch("/{user_id}", response_model=AdminUserResponse, dependencies=[Depends(require_system_admin)])
def update_user(
    user_id: int,
    data: AdminUserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a user's organization, role, or system admin status."""
    user = db.query(User).options(joinedload(User.organization)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if data.organization_id is not None:
        org = db.query(Organization).filter(Organization.id == data.organization_id).first()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target organization not found")
        user.organization_id = data.organization_id
        # Reset role to member when moving orgs (unless explicitly set)
        if data.role is None:
            user.role = "member"

    if data.role is not None:
        if data.role not in ("owner", "admin", "member"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be owner, admin, or member")
        user.role = data.role

    if data.is_system_admin is not None:
        user.is_system_admin = data.is_system_admin

    db.commit()
    db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else "Unknown",
        plan=user.organization.plan if user.organization else "free",
        is_system_admin=user.is_system_admin,
        auth_provider=user.auth_provider or "email",
        created_at=user.created_at,
        last_active_at=user.last_active_at,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_system_admin)])
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a user and clean up all related records."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete yourself"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    cleanup_and_delete_user(db, user)
    db.commit()

    return None
