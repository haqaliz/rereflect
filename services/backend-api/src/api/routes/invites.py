"""
Public Invite API routes for accepting team invitations.

These endpoints are PUBLIC - they do not require authentication.
They are used by invited users to view and accept invitations.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.models.team_invite import TeamInvite
from src.api.auth import hash_password, create_access_token
from src.services.audit_service import log_action


router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================


class PublicInviteDetails(BaseModel):
    """Public invite details shown before accepting."""
    email: str
    role: str
    organization_name: str
    expires_at: datetime
    invited_by_name: str  # Inviter's email


class AcceptInviteRequest(BaseModel):
    """Request body for accepting an invite."""
    password: str = Field(..., description="Password for the new account")


class AcceptedUserResponse(BaseModel):
    """User response after accepting invite."""
    id: int
    email: str
    role: str

    class Config:
        from_attributes = True


class AcceptInviteResponse(BaseModel):
    """Response after successfully accepting an invite."""
    user: AcceptedUserResponse
    access_token: str


# ============================================================================
# Public Endpoints
# ============================================================================


@router.get("/{token}", response_model=PublicInviteDetails)
def get_invite_details(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Get invite details by token (public endpoint).
    Used to display invite info before accepting.
    """
    invite = db.query(TeamInvite).filter(
        TeamInvite.token == token
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or invalid token"
        )

    # Check if already accepted
    if invite.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has already been accepted"
        )

    # Check if canceled
    if invite.status == "canceled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has been canceled"
        )

    # Check if expired
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has expired"
        )

    return PublicInviteDetails(
        email=invite.email,
        role=invite.role,
        organization_name=invite.organization.name,
        expires_at=invite.expires_at,
        invited_by_name=invite.invited_by.email
    )


@router.post("/{token}/accept", response_model=AcceptInviteResponse, status_code=status.HTTP_201_CREATED)
def accept_invite(
    token: str,
    data: AcceptInviteRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Accept an invite and create user account (public endpoint).
    Creates a new user in the organization with the invited role.
    """
    invite = db.query(TeamInvite).filter(
        TeamInvite.token == token
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or invalid token"
        )

    # Check if already accepted
    if invite.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has already been accepted"
        )

    # Check if canceled
    if invite.status == "canceled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has been canceled"
        )

    # Check if expired
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has expired"
        )

    # Validate password strength
    if len(data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )

    # Get the organization to update seat count
    organization = db.query(Organization).filter(
        Organization.id == invite.organization_id
    ).first()

    now = datetime.utcnow()

    # Check if user already exists with this email
    existing_user = db.query(User).filter(User.email == invite.email).first()

    if existing_user:
        # If user exists in the same organization, reject
        if existing_user.organization_id == invite.organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists in this organization"
            )

        # User exists in a different organization - update them to join the new org
        # Note: This effectively moves the user from their old org to the new one
        existing_user.organization_id = invite.organization_id
        existing_user.role = invite.role
        existing_user.invited_by_id = invite.invited_by_id
        existing_user.joined_at = now
        # Update password if provided
        existing_user.password_hash = hash_password(data.password)

        new_user = existing_user
    else:
        # Create a new user
        new_user = User(
            email=invite.email,
            password_hash=hash_password(data.password),
            organization_id=invite.organization_id,
            role=invite.role,
            invited_by_id=invite.invited_by_id,
            joined_at=now,
            created_at=now,
        )
        db.add(new_user)

    # Update invite status
    invite.status = "accepted"
    invite.accepted_at = now

    # Increment organization seat count
    organization.seat_count += 1

    db.commit()
    db.refresh(new_user)

    # Create audit log for user joining
    log_action(
        db=db,
        org_id=invite.organization_id,
        user_id=new_user.id,
        user_email=new_user.email,
        action="user_joined",
        target_type="user",
        target_id=new_user.id,
        details={
            "email": new_user.email,
            "role": new_user.role,
            "invite_id": invite.id
        },
        request=request
    )

    # Create access token for the new user
    access_token = create_access_token({
        "user_id": new_user.id,
        "organization_id": new_user.organization_id,
        "role": new_user.role
    })

    return AcceptInviteResponse(
        user=AcceptedUserResponse(
            id=new_user.id,
            email=new_user.email,
            role=new_user.role
        ),
        access_token=access_token
    )
