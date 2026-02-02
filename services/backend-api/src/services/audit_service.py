"""Audit logging service for tracking team management actions."""
from typing import Optional, Any
from fastapi import Request
from sqlalchemy.orm import Session
from src.models.audit_log import AuditLog


def log_action(
    db: Session,
    org_id: int,
    user_id: int,
    user_email: str,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """Create an audit log entry.

    Args:
        db: Database session
        org_id: Organization ID
        user_id: ID of user performing the action
        user_email: Email of user performing the action
        action: The action type (user_invited, user_joined, user_removed, role_changed, ownership_transferred)
        target_type: Type of entity affected (user, invite, etc.)
        target_id: ID of the affected entity
        details: Additional context as JSON
        request: FastAPI request object for extracting IP and user agent

    Returns:
        The created AuditLog entry
    """
    ip_address = None
    user_agent = None

    if request:
        # Get IP address from request
        ip_address = request.client.host if request.client else None
        # Get user agent from headers
        user_agent = request.headers.get("user-agent")

    log = AuditLog(
        organization_id=org_id,
        user_id=user_id,
        user_email=user_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
