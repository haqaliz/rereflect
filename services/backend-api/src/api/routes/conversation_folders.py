"""
Conversation Folders REST API (M2.2 AI Copilot).

Covers:
- GET /api/v1/conversations/folders — List folders
- POST /api/v1/conversations/folders — Create folder (Pro+)
- PATCH /api/v1/conversations/folders/:id — Update folder
- DELETE /api/v1/conversations/folders/:id — Delete folder (moves conversations to null)
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.session import get_db
from src.models.organization import Organization
from src.models.conversation import Conversation
from src.models.conversation_folder import ConversationFolder
from src.api.dependencies import (
    get_current_org,
    require_feature,
)

router = APIRouter(prefix="/api/v1/conversations/folders", tags=["conversation-folders"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: Optional[int] = 0


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    sort_order: Optional[int] = None


class FolderResponse(BaseModel):
    id: int
    name: str
    sort_order: int
    conversation_count: int
    created_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_folder_or_404(folder_id: int, org_id: int, db: Session) -> ConversationFolder:
    folder = db.query(ConversationFolder).filter(
        ConversationFolder.id == folder_id,
        ConversationFolder.organization_id == org_id,
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def _conversation_count(folder_id: int, db: Session) -> int:
    return (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.folder_id == folder_id,
            Conversation.is_active == True,
        )
        .scalar()
        or 0
    )


# ── GET /api/v1/conversations/folders ────────────────────────────────────────


@router.get("", response_model=List[FolderResponse])
def list_folders(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all conversation folders for the organization."""
    folders = (
        db.query(ConversationFolder)
        .filter(ConversationFolder.organization_id == current_org.id)
        .order_by(ConversationFolder.sort_order, ConversationFolder.created_at)
        .all()
    )
    return [
        FolderResponse(
            id=f.id,
            name=f.name,
            sort_order=f.sort_order,
            conversation_count=_conversation_count(f.id, db),
            created_at=f.created_at,
        )
        for f in folders
    ]


# ── POST /api/v1/conversations/folders ───────────────────────────────────────


@router.post(
    "",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("conversation_folders"))],
)
def create_folder(
    data: FolderCreate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new conversation folder. Pro+ plan required."""
    folder = ConversationFolder(
        organization_id=current_org.id,
        name=data.name,
        sort_order=data.sort_order or 0,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)

    return FolderResponse(
        id=folder.id,
        name=folder.name,
        sort_order=folder.sort_order,
        conversation_count=0,
        created_at=folder.created_at,
    )


# ── PATCH /api/v1/conversations/folders/:id ──────────────────────────────────


@router.patch("/{folder_id}", response_model=FolderResponse)
def update_folder(
    folder_id: int,
    data: FolderUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Rename or reorder a folder."""
    folder = _get_folder_or_404(folder_id, current_org.id, db)

    if data.name is not None:
        folder.name = data.name
    if data.sort_order is not None:
        folder.sort_order = data.sort_order

    db.commit()
    db.refresh(folder)

    return FolderResponse(
        id=folder.id,
        name=folder.name,
        sort_order=folder.sort_order,
        conversation_count=_conversation_count(folder.id, db),
        created_at=folder.created_at,
    )


# ── DELETE /api/v1/conversations/folders/:id ─────────────────────────────────


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a folder. Moves its conversations to null folder_id."""
    folder = _get_folder_or_404(folder_id, current_org.id, db)

    # Move conversations to null folder (unfiled)
    db.query(Conversation).filter(
        Conversation.folder_id == folder_id,
        Conversation.organization_id == current_org.id,
    ).update({"folder_id": None})

    db.delete(folder)
    db.commit()
    return None
