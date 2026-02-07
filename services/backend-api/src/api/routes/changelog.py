"""
Changelog API endpoints.
Public endpoint for listing changelog entries + admin endpoints for management.
"""

from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.changelog_entry import ChangelogEntry
from src.api.dependencies import require_system_admin

router = APIRouter(prefix="/api/v1/changelog", tags=["changelog"])


# Schemas
class ChangelogEntryPublic(BaseModel):
    id: int
    title: str
    description: Optional[str]
    entry_type: str
    is_breaking: bool
    committed_at: datetime

    class Config:
        from_attributes = True


class ChangelogEntryAdmin(ChangelogEntryPublic):
    commit_hash: str
    is_hidden: bool
    created_at: datetime
    updated_at: Optional[datetime]


class ChangelogListResponse(BaseModel):
    items: List[ChangelogEntryPublic]
    total: int
    has_more: bool


class ChangelogAdminListResponse(BaseModel):
    items: List[ChangelogEntryAdmin]
    total: int
    has_more: bool


class ChangelogEntryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    entry_type: Optional[str] = None
    is_breaking: Optional[bool] = None
    is_hidden: Optional[bool] = None


# Public endpoint (no auth)
@router.get("", response_model=ChangelogListResponse)
def list_changelog(
    entry_type: Optional[str] = Query(None),
    days: Optional[int] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List public changelog entries (visible only)."""
    query = db.query(ChangelogEntry).filter(ChangelogEntry.is_hidden == False)

    if entry_type:
        query = query.filter(ChangelogEntry.entry_type == entry_type)

    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(ChangelogEntry.committed_at >= cutoff)

    total = query.count()
    items = query.order_by(ChangelogEntry.committed_at.desc()).offset(offset).limit(limit).all()
    has_more = offset + limit < total

    return ChangelogListResponse(
        items=[ChangelogEntryPublic.model_validate(item) for item in items],
        total=total,
        has_more=has_more,
    )


# Admin endpoints
@router.get("/admin", response_model=ChangelogAdminListResponse, dependencies=[Depends(require_system_admin)])
def admin_list_changelog(
    entry_type: Optional[str] = Query(None),
    days: Optional[int] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List all changelog entries including hidden (system admin only)."""
    query = db.query(ChangelogEntry)

    if entry_type:
        query = query.filter(ChangelogEntry.entry_type == entry_type)

    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(ChangelogEntry.committed_at >= cutoff)

    total = query.count()
    items = query.order_by(ChangelogEntry.committed_at.desc()).offset(offset).limit(limit).all()
    has_more = offset + limit < total

    return ChangelogAdminListResponse(
        items=[ChangelogEntryAdmin.model_validate(item) for item in items],
        total=total,
        has_more=has_more,
    )


@router.patch("/admin/{entry_id}", response_model=ChangelogEntryAdmin, dependencies=[Depends(require_system_admin)])
def update_changelog_entry(
    entry_id: int,
    update: ChangelogEntryUpdate,
    db: Session = Depends(get_db),
):
    """Update a changelog entry (system admin only)."""
    entry = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    db.commit()
    db.refresh(entry)
    return ChangelogEntryAdmin.model_validate(entry)


@router.delete("/admin/{entry_id}", dependencies=[Depends(require_system_admin)])
def delete_changelog_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    """Delete a changelog entry (system admin only)."""
    entry = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    db.delete(entry)
    db.commit()
    return {"status": "deleted"}
