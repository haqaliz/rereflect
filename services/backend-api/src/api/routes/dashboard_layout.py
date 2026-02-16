"""Dashboard layout CRUD — per-user widget layout persistence."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.user import User
from src.models.dashboard_layout import UserDashboardLayout
from src.api.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/user/dashboard-layout", tags=["dashboard-layout"])


# Default layout returned when the user has no saved layout
DEFAULT_LAYOUT: dict = {
    "version": 1,
    "widgets": [
        {"id": "sentiment-overview", "x": 0, "y": 0, "w": 6, "h": 4},
        {"id": "feedback-volume", "x": 6, "y": 0, "w": 6, "h": 4},
        {"id": "pain-points", "x": 0, "y": 4, "w": 4, "h": 4},
        {"id": "feature-requests", "x": 4, "y": 4, "w": 4, "h": 4},
        {"id": "urgent-items", "x": 8, "y": 4, "w": 4, "h": 4},
        {"id": "activity-feed", "x": 0, "y": 8, "w": 6, "h": 4},
        {"id": "team-activity", "x": 6, "y": 8, "w": 6, "h": 4},
    ],
}


# Schemas
class LayoutResponse(BaseModel):
    layout_json: Any
    is_default: bool = False

    class Config:
        from_attributes = True


class LayoutUpdateRequest(BaseModel):
    layout_json: Any


@router.get("/", response_model=LayoutResponse)
def get_layout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's dashboard layout. Returns default if none saved."""
    row = db.query(UserDashboardLayout).filter(
        UserDashboardLayout.user_id == current_user.id,
    ).first()

    if row:
        return LayoutResponse(layout_json=row.layout_json, is_default=False)

    return LayoutResponse(layout_json=DEFAULT_LAYOUT, is_default=True)


@router.put("/", response_model=LayoutResponse)
def save_layout(
    body: LayoutUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save or update current user's dashboard layout (upsert)."""
    row = db.query(UserDashboardLayout).filter(
        UserDashboardLayout.user_id == current_user.id,
    ).first()

    if row:
        row.layout_json = body.layout_json
    else:
        row = UserDashboardLayout(
            user_id=current_user.id,
            layout_json=body.layout_json,
        )
        db.add(row)

    db.commit()
    db.refresh(row)

    return LayoutResponse(layout_json=row.layout_json, is_default=False)


@router.delete("/", response_model=LayoutResponse)
def reset_layout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete user's saved layout, reverting to default."""
    row = db.query(UserDashboardLayout).filter(
        UserDashboardLayout.user_id == current_user.id,
    ).first()

    if row:
        db.delete(row)
        db.commit()

    return LayoutResponse(layout_json=DEFAULT_LAYOUT, is_default=True)
