"""
Saved views CRUD endpoints.
Allows users to save and restore analytics page state configurations.
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from src.database.session import get_db
from src.models.saved_view import SavedView
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org, require_feature
from src.config.plans import get_saved_views_limit

router = APIRouter(prefix="/api/v1/saved-views", tags=["saved-views"])


# ─── Schemas ────────────────────────────────────────────────────

class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    page: str = Field(min_length=1, max_length=50)
    config: dict


class SavedViewUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[dict] = None


class ReorderItem(BaseModel):
    id: int
    position: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem]


class SavedViewResponse(BaseModel):
    id: int
    name: str
    page: str
    config: dict
    created_by_id: int
    position: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Endpoints ──────────────────────────────────────────────────

@router.get("/", response_model=List[SavedViewResponse])
def list_saved_views(
    page: str = "analytics",
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List saved views for a page within the organization."""
    views = (
        db.query(SavedView)
        .filter(
            SavedView.organization_id == current_org.id,
            SavedView.page == page,
        )
        .order_by(SavedView.position)
        .all()
    )
    return views


@router.post(
    "/",
    response_model=SavedViewResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("saved_views"))],
)
def create_saved_view(
    data: SavedViewCreate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new saved view. Enforces plan-based limit."""
    plan = current_org.plan or "free"
    limit = get_saved_views_limit(plan)

    if limit is not None:
        current_count = (
            db.query(SavedView)
            .filter(
                SavedView.organization_id == current_org.id,
                SavedView.page == data.page,
            )
            .count()
        )
        if current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "saved_views_limit_exceeded",
                    "limit": limit,
                    "used": current_count,
                    "message": f"You've reached your limit of {limit} saved views. Upgrade to save more.",
                    "upgrade_url": "/settings/billing",
                },
            )

    # Get next position
    max_pos = (
        db.query(SavedView.position)
        .filter(
            SavedView.organization_id == current_org.id,
            SavedView.page == data.page,
        )
        .order_by(SavedView.position.desc())
        .first()
    )
    next_position = (max_pos[0] + 1) if max_pos else 0

    view = SavedView(
        organization_id=current_org.id,
        name=data.name,
        page=data.page,
        config=data.config,
        created_by_id=current_user.id,
        position=next_position,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.patch("/{view_id}", response_model=SavedViewResponse)
def update_saved_view(
    view_id: int,
    data: SavedViewUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update a saved view's name or config."""
    view = (
        db.query(SavedView)
        .filter(SavedView.id == view_id, SavedView.organization_id == current_org.id)
        .first()
    )
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")

    if data.name is not None:
        view.name = data.name
    if data.config is not None:
        view.config = data.config
    view.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(view)
    return view


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(
    view_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a saved view."""
    view = (
        db.query(SavedView)
        .filter(SavedView.id == view_id, SavedView.organization_id == current_org.id)
        .first()
    )
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")

    db.delete(view)
    db.commit()


@router.patch("/reorder", response_model=List[SavedViewResponse])
def reorder_saved_views(
    data: ReorderRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Reorder saved views by updating positions."""
    for item in data.items:
        view = (
            db.query(SavedView)
            .filter(SavedView.id == item.id, SavedView.organization_id == current_org.id)
            .first()
        )
        if view:
            view.position = item.position

    db.commit()

    # Return updated list
    views = (
        db.query(SavedView)
        .filter(SavedView.organization_id == current_org.id)
        .order_by(SavedView.position)
        .all()
    )
    return views
