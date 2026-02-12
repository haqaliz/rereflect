"""
Notification & Alert Preference API routes.

All endpoints require authentication and are scoped to the current user.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from src.database.session import get_db
from src.models.user import User
from src.models.notification import Notification
from src.models.user_alert_preference import UserAlertPreference
from src.api.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    message: Optional[str]
    link: Optional[str]
    is_read: bool
    is_dismissed: bool
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_model(cls, n: "Notification") -> "NotificationOut":
        return cls(
            id=n.id,
            type=n.type,
            title=n.title,
            message=n.message,
            link=n.link,
            is_read=n.is_read,
            is_dismissed=n.is_dismissed,
            metadata=n.metadata_,
            created_at=n.created_at,
        )


class NotificationListResponse(BaseModel):
    items: List[NotificationOut]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    updated: int


class AlertPreferenceItem(BaseModel):
    alert_type: str
    is_enabled: bool
    channel_email: bool
    channel_slack: bool
    channel_inapp: bool
    channel_intercom: bool = False
    threshold_value: Optional[float]
    retention_days: int = 30


class AlertPreferencesResponse(BaseModel):
    preferences: List[AlertPreferenceItem]


class AlertPreferenceUpdate(BaseModel):
    alert_type: str
    is_enabled: bool
    channel_email: bool
    channel_slack: bool
    channel_inapp: bool
    channel_intercom: bool = False
    threshold_value: Optional[float]
    retention_days: int = Field(30, ge=30, le=365)

    @validator("threshold_value")
    def validate_threshold(cls, v, values):
        if v is None:
            return v
        alert_type = values.get("alert_type")
        if alert_type == "sentiment_spike":
            if v < 0 or v > 100:
                raise ValueError("Sentiment threshold must be between 0 and 100")
        elif alert_type == "volume_spike":
            if v < 1.0 or v > 10.0:
                raise ValueError("Volume threshold must be between 1.0 and 10.0")
        return v


class UpdatePreferencesRequest(BaseModel):
    preferences: List[AlertPreferenceUpdate]


class RetentionTypeItem(BaseModel):
    alert_type: str
    retention_days: int
    extra_days: int
    monthly_cost: float


class RetentionResponse(BaseModel):
    types: List[RetentionTypeItem]
    total_extra_days: int
    total_monthly_cost: float
    min_days: int = 30
    max_days: int = 365
    price_per_day: float = 0.10


class RetentionItem(BaseModel):
    alert_type: str
    days: int = Field(..., ge=30, le=365)


class UpdateRetentionRequest(BaseModel):
    retentions: List[RetentionItem]


# ── List Notifications ───────────────────────────────────────────────────────

@router.get("", response_model=NotificationListResponse)
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None),
    dismissed: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List current user's notifications. Set dismissed=true to see only dismissed."""
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_dismissed == dismissed,
    )

    if type:
        query = query.filter(Notification.type == type)

    total = query.count()

    unread_count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_dismissed == False,
    ).count()

    items = (
        query
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return NotificationListResponse(
        items=[NotificationOut.from_model(n) for n in items],
        total=total,
        unread_count=unread_count,
    )


# ── Unread Count ─────────────────────────────────────────────────────────────

@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the count of unread, non-dismissed notifications."""
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_dismissed == False,
    ).count()

    return UnreadCountResponse(count=count)


# ── Mark Read ────────────────────────────────────────────────────────────────

@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as read."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()
    return {"ok": True}


# ── Mark All Read ────────────────────────────────────────────────────────────

@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all of the user's unread notifications as read."""
    updated = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_dismissed == False,
    ).update({"is_read": True})

    db.commit()
    return MarkAllReadResponse(updated=updated)


# ── Dismiss ──────────────────────────────────────────────────────────────────

@router.patch("/{notification_id}/dismiss")
def dismiss(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss a single notification."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_dismissed = True
    db.commit()
    return {"ok": True}


# ── Restore (un-dismiss) ────────────────────────────────────────────────────

@router.patch("/{notification_id}/restore")
def restore(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restore a dismissed notification."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_dismissed = False
    db.commit()
    return {"ok": True}


# ── Alert Preferences ────────────────────────────────────────────────────────

@router.get("/preferences", response_model=AlertPreferencesResponse)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's alert preferences (all types)."""
    prefs = db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id == current_user.id,
    ).all()

    return AlertPreferencesResponse(
        preferences=[
            AlertPreferenceItem(
                alert_type=p.alert_type,
                is_enabled=p.is_enabled,
                channel_email=p.channel_email,
                channel_slack=p.channel_slack,
                channel_inapp=p.channel_inapp,
                channel_intercom=p.channel_intercom,
                threshold_value=p.threshold_value,
                retention_days=p.retention_days,
            )
            for p in prefs
        ]
    )


@router.put("/preferences", response_model=AlertPreferencesResponse)
def update_preferences(
    body: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update alert preferences (bulk update)."""
    for item in body.preferences:
        pref = db.query(UserAlertPreference).filter(
            UserAlertPreference.user_id == current_user.id,
            UserAlertPreference.alert_type == item.alert_type,
        ).first()

        if pref:
            pref.is_enabled = item.is_enabled
            pref.channel_email = item.channel_email
            pref.channel_slack = item.channel_slack
            pref.channel_inapp = item.channel_inapp
            pref.channel_intercom = item.channel_intercom
            pref.threshold_value = item.threshold_value
            pref.retention_days = item.retention_days
        else:
            pref = UserAlertPreference(
                user_id=current_user.id,
                alert_type=item.alert_type,
                is_enabled=item.is_enabled,
                channel_email=item.channel_email,
                channel_slack=item.channel_slack,
                channel_inapp=item.channel_inapp,
                channel_intercom=item.channel_intercom,
                threshold_value=item.threshold_value,
                retention_days=item.retention_days,
            )
            db.add(pref)

    db.commit()

    # Return updated preferences
    return get_preferences(current_user=current_user, db=db)


# ── Retention ────────────────────────────────────────────────────────────────

def _build_retention_response(user: User, db: Session) -> RetentionResponse:
    """Build per-type retention response from UserAlertPreference rows."""
    prefs = db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id == user.id,
    ).all()

    type_items = []
    total_extra = 0
    for p in prefs:
        days = p.retention_days or 30
        extra = max(0, days - 30)
        total_extra += extra
        type_items.append(RetentionTypeItem(
            alert_type=p.alert_type,
            retention_days=days,
            extra_days=extra,
            monthly_cost=round(extra * 0.10, 2),
        ))

    return RetentionResponse(
        types=type_items,
        total_extra_days=total_extra,
        total_monthly_cost=round(total_extra * 0.10, 2),
    )


@router.get("/retention", response_model=RetentionResponse)
def get_retention(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current per-type retention settings and pricing info."""
    return _build_retention_response(current_user, db)


@router.put("/retention", response_model=RetentionResponse)
def update_retention(
    body: UpdateRetentionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update per-type notification retention days. Triggers Stripe billing for extra days beyond 30."""
    from src.models.subscription import Subscription
    from src.services.stripe_service import get_stripe_service

    for item in body.retentions:
        pref = db.query(UserAlertPreference).filter(
            UserAlertPreference.user_id == current_user.id,
            UserAlertPreference.alert_type == item.alert_type,
        ).first()

        if pref:
            pref.retention_days = item.days
        else:
            pref = UserAlertPreference(
                user_id=current_user.id,
                alert_type=item.alert_type,
                retention_days=item.days,
            )
            db.add(pref)

    db.commit()

    # Compute total extra days across all types for Stripe billing
    all_prefs = db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id == current_user.id,
    ).all()
    total_extra = sum(max(0, (p.retention_days or 30) - 30) for p in all_prefs)

    # Manage Stripe add-on if org has an active subscription
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == current_user.organization_id,
        Subscription.status.in_(["active", "trialing"]),
    ).first()

    if subscription and subscription.stripe_subscription_id:
        stripe_service = get_stripe_service()
        stripe_service.manage_retention_addon(
            subscription_id=subscription.stripe_subscription_id,
            extra_days=total_extra,
        )

    return _build_retention_response(current_user, db)


# ── Get Single Notification ─────────────────────────────────────────────────

@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single notification by ID. Also marks it as read."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notification.is_read:
        notification.is_read = True
        db.commit()

    return NotificationOut.from_model(notification)
