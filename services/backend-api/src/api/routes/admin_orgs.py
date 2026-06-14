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
from src.models.feedback import FeedbackItem
from src.models.feedback_note import FeedbackNote
from src.models.feedback_source import FeedbackSource
from src.models.feedback_source_event import FeedbackSourceEvent
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.notification import Notification
from src.models.audit_log import AuditLog
from src.models.saved_view import SavedView
from src.models.shared_link import SharedLink
from src.models.team_invite import TeamInvite
from src.models.assignment_rule import AssignmentRule
from src.models.pending_feedback import PendingFeedback
from src.models.usage import UsageRecord
from src.models.subscription import Subscription
from src.models.integration import Integration
from src.models.customer_health import CustomerHealth
from src.models.custom_category import CustomCategory
from src.models.anomaly import SentimentAnomaly
from src.models.weekly_insight import WeeklyInsight

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
        promo_code_used=org.promo_code_used,
        created_at=org.created_at,
        seat_count=org.seat_count,
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


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_system_admin)])
def delete_organization(org_id: int, db: Session = Depends(get_db)):
    """Delete an organization that has no users. Removes all related data."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    user_count = db.query(func.count(User.id)).filter(User.organization_id == org_id).scalar()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete organization with {user_count} user(s). Remove all users first.",
        )

    # Clean up all related records
    db.query(FeedbackNote).filter(FeedbackNote.organization_id == org_id).delete()
    db.query(FeedbackWorkflowEvent).filter(FeedbackWorkflowEvent.organization_id == org_id).delete()
    db.query(FeedbackSourceEvent).filter(FeedbackSourceEvent.organization_id == org_id).delete()
    db.query(FeedbackItem).filter(FeedbackItem.organization_id == org_id).delete()
    db.query(FeedbackSource).filter(FeedbackSource.organization_id == org_id).delete()
    db.query(PendingFeedback).filter(PendingFeedback.organization_id == org_id).delete()
    db.query(Notification).filter(Notification.organization_id == org_id).delete()
    db.query(AuditLog).filter(AuditLog.organization_id == org_id).delete()
    db.query(SavedView).filter(SavedView.organization_id == org_id).delete()
    db.query(SharedLink).filter(SharedLink.organization_id == org_id).delete()
    db.query(TeamInvite).filter(TeamInvite.organization_id == org_id).delete()
    db.query(AssignmentRule).filter(AssignmentRule.organization_id == org_id).delete()
    db.query(CustomerHealth).filter(CustomerHealth.organization_id == org_id).delete()
    db.query(CustomCategory).filter(CustomCategory.organization_id == org_id).delete()
    db.query(SentimentAnomaly).filter(SentimentAnomaly.organization_id == org_id).delete()
    db.query(UsageRecord).filter(UsageRecord.organization_id == org_id).delete()
    db.query(Subscription).filter(Subscription.organization_id == org_id).delete()
    db.query(Integration).filter(Integration.organization_id == org_id).delete()
    db.query(WeeklyInsight).filter(WeeklyInsight.organization_id == org_id).delete()

    db.delete(org)
    db.commit()
