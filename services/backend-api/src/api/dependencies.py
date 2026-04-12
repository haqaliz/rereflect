from typing import Callable
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.models.usage import UsageRecord
from src.api.auth import decode_access_token
from src.config.plans import get_plan, get_plan_for_feature, has_feature, get_feedback_limit, get_seat_limit

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token.

    Also updates user.last_active_at on each authenticated request.
    """

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Block deactivated accounts (GDPR deletion grace period)
    if user.is_deactivated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Log in to cancel scheduled deletion."
        )

    # Update last_active_at on each authenticated request
    user.last_active_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    return user


def get_current_user_allow_deactivated(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Like get_current_user but does NOT block deactivated accounts.

    Used exclusively by the cancel-deletion endpoint so users can recover
    their account during the 30-day grace period.
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


def get_current_org(current_user: User = Depends(get_current_user)) -> Organization:
    """Get current user's organization (for multi-tenant isolation)."""
    return current_user.organization


def get_current_usage(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
) -> UsageRecord:
    """Get or create current usage record for the billing period."""
    from src.models.subscription import Subscription

    # Get subscription to determine billing period
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == current_org.id
    ).first()

    # Determine billing period
    if subscription and subscription.current_period_start:
        period_start = subscription.current_period_start
        period_end = subscription.current_period_end
    else:
        # Default to current month for free plans
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)

    # Get or create usage record
    usage = db.query(UsageRecord).filter(
        UsageRecord.organization_id == current_org.id,
        UsageRecord.period_start == period_start,
    ).first()

    if not usage:
        usage = UsageRecord(
            organization_id=current_org.id,
            period_start=period_start,
            period_end=period_end,
            feedback_count=0,
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)

    return usage


def check_feedback_limit(
    current_org: Organization = Depends(get_current_org),
    usage: UsageRecord = Depends(get_current_usage),
    db: Session = Depends(get_db)
) -> bool:
    """
    Check if organization can create more feedback.
    Raises HTTPException if limit exceeded and overage not enabled.
    """
    plan = current_org.plan or "free"
    plan_config = get_plan(plan)
    limit = get_feedback_limit(plan)

    # Unlimited
    if limit is None:
        return True

    total_used = usage.feedback_count + usage.overage_feedback

    if total_used >= limit:
        if plan_config.get("overage_enabled"):
            # Allow overage - will be tracked and charged
            return True
        else:
            # Hard limit for free plan
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "feedback_limit_exceeded",
                    "limit": limit,
                    "used": total_used,
                    "message": f"You've reached your monthly limit of {limit} feedback items. Upgrade to continue.",
                    "upgrade_url": "/settings/billing"
                }
            )

    return True


def track_feedback_usage(
    current_org: Organization = Depends(get_current_org),
    usage: UsageRecord = Depends(get_current_usage),
    db: Session = Depends(get_db)
) -> UsageRecord:
    """
    Track feedback usage - call this after successfully creating feedback.
    Increments counter and tracks overage if applicable.
    """
    plan = current_org.plan or "free"
    limit = get_feedback_limit(plan)

    if limit is None:
        # Unlimited - just increment counter
        usage.feedback_count += 1
    elif usage.feedback_count < limit:
        # Within limit
        usage.feedback_count += 1
    else:
        # Overage
        usage.overage_feedback += 1

    db.commit()
    db.refresh(usage)
    return usage


def check_seat_limit(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
) -> bool:
    """
    Check if organization can add more users.
    Raises HTTPException if seat limit exceeded.
    """
    plan = current_org.plan or "free"
    limit = get_seat_limit(plan)

    # Unlimited
    if limit is None:
        return True

    current_seats = db.query(User).filter(
        User.organization_id == current_org.id
    ).count()

    if current_seats >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "seat_limit_exceeded",
                "limit": limit,
                "used": current_seats,
                "message": f"You've reached your limit of {limit} team members. Upgrade to add more.",
                "upgrade_url": "/settings/billing"
            }
        )

    return True


def require_feature(feature: str) -> Callable:
    """
    Dependency factory for feature gating.

    Usage:
        @router.get("/export", dependencies=[Depends(require_feature("data_export"))])
        def export_data():
            ...
    """
    def dependency(current_org: Organization = Depends(get_current_org)):
        plan = current_org.plan or "free"

        if not has_feature(plan, feature):
            required_plan = get_plan_for_feature(feature)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_not_available",
                    "feature": feature,
                    "current_plan": plan,
                    "required_plan": required_plan,
                    "message": f"This feature requires the {required_plan.title()} plan or higher.",
                    "upgrade_url": "/settings/billing"
                }
            )
        return True

    return dependency


def require_admin_or_owner(current_user: User = Depends(get_current_user)) -> bool:
    """
    Dependency to check if user is admin or owner.
    Raises 403 if user.role == 'member'.

    Usage:
        @router.post("/invite", dependencies=[Depends(require_admin_or_owner)])
        def invite_member():
            ...
    """
    if current_user.role == 'member':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires admin or owner privileges"
        )
    return True


def require_owner(current_user: User = Depends(get_current_user)) -> bool:
    """
    Dependency to check if user is owner.
    Raises 403 if user.role != 'owner'.

    Usage:
        @router.post("/transfer-ownership", dependencies=[Depends(require_owner)])
        def transfer_ownership():
            ...
    """
    if current_user.role != 'owner':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires owner privileges"
        )
    return True


def require_system_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to check if user is a system admin.
    Raises 403 if user.is_system_admin is False.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_system_admin)])
        def admin_only():
            ...
    """
    if not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System admin access required"
        )
    return current_user
