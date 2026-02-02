"""
Team Management API routes for managing organization members.
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from src.database.session import get_db
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import (
    get_current_user,
    get_current_org,
    require_admin_or_owner,
    require_owner,
    check_seat_limit,
)


router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class TeamMember(BaseModel):
    id: int
    email: str
    role: str  # 'owner', 'admin', 'member'
    last_active_at: Optional[datetime] = None
    joined_at: Optional[datetime] = None
    invited_by_id: Optional[int] = None

    class Config:
        from_attributes = True


class TeamListResponse(BaseModel):
    members: list[TeamMember]
    total: int


class RoleUpdateRequest(BaseModel):
    role: str  # 'admin' or 'member'


class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # 'admin' or 'member'


class MessageResponse(BaseModel):
    message: str


# ============================================================================
# Team Endpoints
# ============================================================================

@router.get("", response_model=TeamListResponse)
def list_team_members(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """
    List all team members in the organization.
    All roles can access this endpoint.
    """
    members = db.query(User).filter(
        User.organization_id == current_org.id
    ).order_by(User.created_at.asc()).all()

    return TeamListResponse(
        members=[
            TeamMember(
                id=m.id,
                email=m.email,
                role=m.role,
                last_active_at=m.last_active_at,
                joined_at=m.joined_at,
                invited_by_id=m.invited_by_id,
            )
            for m in members
        ],
        total=len(members)
    )


@router.patch("/{user_id}/role", response_model=TeamMember)
def update_member_role(
    user_id: int,
    data: RoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    _admin_check: bool = Depends(require_admin_or_owner),
    db: Session = Depends(get_db)
):
    """
    Change a team member's role.
    - Owner/Admin only
    - Cannot change owner's role
    - Cannot demote owner
    - Admin can only assign 'member' role (not 'admin' or 'owner')
    """
    # Validate role
    if data.role not in ['admin', 'member']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'member'"
        )

    # Find the target user
    target_user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_org.id
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Cannot change owner's role
    if target_user.role == 'owner':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change the owner's role. Use transfer ownership instead."
        )

    # Admin cannot promote to admin (only owner can)
    if current_user.role == 'admin' and data.role == 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can promote members to admin"
        )

    # Update role
    target_user.role = data.role
    db.commit()
    db.refresh(target_user)

    return TeamMember(
        id=target_user.id,
        email=target_user.email,
        role=target_user.role,
        last_active_at=target_user.last_active_at,
        joined_at=target_user.joined_at,
        invited_by_id=target_user.invited_by_id,
    )


@router.post("/invite", response_model=TeamMember, status_code=status.HTTP_201_CREATED)
def invite_member(
    data: InviteRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    _admin_check: bool = Depends(require_admin_or_owner),
    _seat_check: bool = Depends(check_seat_limit),
    db: Session = Depends(get_db)
):
    """
    Invite a new team member.
    - Owner/Admin only
    - Validates email doesn't exist
    - Admin cannot invite as 'owner'
    - For now: Create user directly (Phase 2 will add email flow)
    """
    from src.api.auth import hash_password
    import secrets

    # Validate role
    if data.role not in ['admin', 'member']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'member'"
        )

    # Admin cannot invite as admin (only owner can)
    if current_user.role == 'admin' and data.role == 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can invite members as admin"
        )

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists"
        )

    # Create user with a temporary random password
    # In Phase 2, this will be replaced with an invitation flow
    temp_password = secrets.token_urlsafe(16)
    now = datetime.utcnow()

    new_user = User(
        email=data.email,
        password_hash=hash_password(temp_password),
        organization_id=current_org.id,
        role=data.role,
        invited_by_id=current_user.id,
        joined_at=now,
        created_at=now,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return TeamMember(
        id=new_user.id,
        email=new_user.email,
        role=new_user.role,
        last_active_at=new_user.last_active_at,
        joined_at=new_user.joined_at,
        invited_by_id=new_user.invited_by_id,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    _admin_check: bool = Depends(require_admin_or_owner),
    db: Session = Depends(get_db)
):
    """
    Remove a team member.
    - Owner/Admin only
    - Cannot remove owner
    - Cannot remove self (owner must transfer ownership first)
    """
    # Find the target user
    target_user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_org.id
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Cannot remove owner
    if target_user.role == 'owner':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove the owner. Transfer ownership first."
        )

    # Cannot remove self
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove yourself from the team"
        )

    # Admin cannot remove other admins
    if current_user.role == 'admin' and target_user.role == 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove other admins. Only the owner can."
        )

    db.delete(target_user)
    db.commit()

    return None


@router.post("/{user_id}/transfer-ownership", response_model=TeamMember)
def transfer_ownership(
    user_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    _owner_check: bool = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Transfer ownership to another member.
    - Owner only
    - Target must be in same org
    - Old owner becomes admin
    """
    # Cannot transfer to self
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer ownership to yourself"
        )

    # Find the target user
    target_user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_org.id
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Transfer ownership
    current_user.role = 'admin'  # Old owner becomes admin
    target_user.role = 'owner'  # New owner

    db.commit()
    db.refresh(target_user)

    return TeamMember(
        id=target_user.id,
        email=target_user.email,
        role=target_user.role,
        last_active_at=target_user.last_active_at,
        joined_at=target_user.joined_at,
        invited_by_id=target_user.invited_by_id,
    )
