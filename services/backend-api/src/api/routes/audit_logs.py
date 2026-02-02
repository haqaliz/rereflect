"""
Audit Log API routes for viewing organization audit logs.
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.organization import Organization
from src.models.user import User
from src.models.audit_log import AuditLog
from src.api.dependencies import (
    get_current_user,
    get_current_org,
    require_admin_or_owner,
)


router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    user_email: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogsResponse(BaseModel):
    logs: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Audit Log Endpoints
# ============================================================================


@router.get("", response_model=AuditLogsResponse)
def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, description="Filter by action type"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    _admin_check: bool = Depends(require_admin_or_owner),
    db: Session = Depends(get_db)
):
    """
    Get audit logs for the organization.
    - Admin/Owner only
    - Business or Enterprise plan required
    - Returns logs sorted by created_at descending (most recent first)
    """
    # Check Business+ plan
    if current_org.plan not in ["business", "enterprise"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit logs require Business or Enterprise plan. Please upgrade to access this feature."
        )

    # Build query
    query = db.query(AuditLog).filter(
        AuditLog.organization_id == current_org.id
    )

    # Filter by action if provided
    if action:
        query = query.filter(AuditLog.action == action)

    # Get total count
    total = query.count()

    # Apply pagination and sorting
    logs = query.order_by(AuditLog.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return AuditLogsResponse(
        logs=[
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                user_email=log.user_email,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                details=log.details,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                created_at=log.created_at
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size
    )
