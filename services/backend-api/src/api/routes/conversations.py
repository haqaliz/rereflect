"""
Conversations REST API (M2.2 AI Copilot).

Covers:
- GET /api/v1/conversations — List conversations
- POST /api/v1/conversations — Create conversation
- GET /api/v1/conversations/:id — Get conversation with messages
- PATCH /api/v1/conversations/:id — Update conversation
- DELETE /api/v1/conversations/:id — Soft delete conversation
- GET /api/v1/conversations/templates — List template starters
"""

from datetime import datetime
from typing import Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.models.conversation import Conversation
from src.models.conversation_folder import ConversationFolder
from src.models.conversation_message import ConversationMessage
from src.api.dependencies import (
    get_current_user,
    get_current_org,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


VALID_CONTEXT_SCOPES = {
    "all_data",
    "feedbacks",
    "customers",
    "pain_points",
    "feature_requests",
    "dashboard",
}


# ── Static template starters ──────────────────────────────────────────────────

TEMPLATE_STARTERS = [
    {"category": "Feedback", "text": "This week's feedback summary"},
    {"category": "Feedback", "text": "Top pain points this month"},
    {"category": "Feedback", "text": "Most requested features"},
    {"category": "Feedback", "text": "Urgent feedback that needs attention"},
    {"category": "Customer", "text": "Top churn risks right now"},
    {"category": "Customer", "text": "Healthiest customers"},
    {"category": "Customer", "text": "Customers with declining health scores"},
    {"category": "Customer", "text": "Sentiment trends over the last 30 days"},
]


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    folder_id: Optional[int] = None
    context_scope: Optional[str] = "all_data"

    @field_validator("context_scope")
    @classmethod
    def validate_context_scope(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CONTEXT_SCOPES:
            raise ValueError(
                f"Invalid context_scope. Must be one of: {', '.join(sorted(VALID_CONTEXT_SCOPES))}"
            )
        return v


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    folder_id: Optional[int] = None
    context_scope: Optional[str] = None

    @field_validator("context_scope")
    @classmethod
    def validate_context_scope(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CONTEXT_SCOPES:
            raise ValueError(
                f"Invalid context_scope. Must be one of: {', '.join(sorted(VALID_CONTEXT_SCOPES))}"
            )
        return v


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    structured_data: Optional[Any] = None
    context_scope: Optional[str]
    query_type: Optional[str]
    llm_provider: Optional[str]
    llm_model: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    cost_cents: Optional[float]
    latency_ms: Optional[int]
    is_regenerated: bool
    created_at: datetime


class ConversationSummary(BaseModel):
    id: int
    public_id: str
    title: Optional[str]
    folder_id: Optional[int]
    context_scope: str
    is_active: bool
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    id: int
    public_id: str
    title: Optional[str]
    folder_id: Optional[int]
    context_scope: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]
    messages_total: int


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummary]
    total: int
    page: int
    page_size: int


class TemplateStarter(BaseModel):
    category: str
    text: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_conversation_or_404(
    conversation_id: str,
    org_id: int,
    db: Session,
) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.public_id == conversation_id,
            Conversation.organization_id == org_id,
            Conversation.is_active == True,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _message_count(conversation_id: int, db: Session) -> int:
    return (
        db.query(func.count(ConversationMessage.id))
        .filter(ConversationMessage.conversation_id == conversation_id)
        .scalar()
        or 0
    )


# ── GET /api/v1/conversations/templates ──────────────────────────────────────
# NOTE: This MUST be defined before /:id routes to avoid routing conflicts


@router.get("/templates", response_model=List[TemplateStarter])
def get_template_starters(
    current_org: Organization = Depends(get_current_org),
):
    """Return static template starter queries for the command bar."""
    return TEMPLATE_STARTERS


# ── GET /api/v1/conversations ─────────────────────────────────────────────────


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    folder_id: Optional[int] = Query(None),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List conversations for the org (paginated, optionally filtered by folder)."""
    query = db.query(Conversation).filter(
        Conversation.organization_id == current_org.id,
        Conversation.is_active == True,
    )

    if folder_id is not None:
        query = query.filter(Conversation.folder_id == folder_id)

    total = query.count()
    offset = (page - 1) * page_size
    conversations = (
        query.order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return ConversationListResponse(
        conversations=[
            ConversationSummary(
                id=conv.id,
                public_id=conv.public_id,
                title=conv.title,
                folder_id=conv.folder_id,
                context_scope=conv.context_scope,
                is_active=conv.is_active,
                message_count=_message_count(conv.id, db),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
            for conv in conversations
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── POST /api/v1/conversations ────────────────────────────────────────────────


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new conversation."""
    # Validate folder belongs to org
    if data.folder_id is not None:
        folder = db.query(ConversationFolder).filter(
            ConversationFolder.id == data.folder_id,
            ConversationFolder.organization_id == current_org.id,
        ).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    now = datetime.utcnow()
    conv = Conversation(
        organization_id=current_org.id,
        created_by_user_id=current_user.id,
        title=data.title or "New Conversation",
        folder_id=data.folder_id,
        context_scope=data.context_scope or "all_data",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return ConversationSummary(
        id=conv.id,
        public_id=conv.public_id,
        title=conv.title,
        folder_id=conv.folder_id,
        context_scope=conv.context_scope,
        is_active=conv.is_active,
        message_count=0,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


# ── GET /api/v1/conversations/:id ────────────────────────────────────────────


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get conversation detail with paginated messages."""
    conv = _get_conversation_or_404(conversation_id, current_org.id, db)

    messages_query = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conv.id)
        .order_by(ConversationMessage.created_at)
    )
    messages_total = messages_query.count()
    offset = (page - 1) * page_size
    messages = messages_query.offset(offset).limit(page_size).all()

    return ConversationDetail(
        id=conv.id,
        public_id=conv.public_id,
        title=conv.title,
        folder_id=conv.folder_id,
        context_scope=conv.context_scope,
        is_active=conv.is_active,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                structured_data=m.structured_data,
                context_scope=m.context_scope,
                query_type=m.query_type,
                llm_provider=m.llm_provider,
                llm_model=m.llm_model,
                tokens_in=m.tokens_in,
                tokens_out=m.tokens_out,
                cost_cents=float(m.cost_cents) if m.cost_cents is not None else None,
                latency_ms=m.latency_ms,
                is_regenerated=m.is_regenerated,
                created_at=m.created_at,
            )
            for m in messages
        ],
        messages_total=messages_total,
    )


# ── PATCH /api/v1/conversations/:id ──────────────────────────────────────────


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update conversation title, folder, or context_scope."""
    conv = _get_conversation_or_404(conversation_id, current_org.id, db)

    if data.title is not None:
        conv.title = data.title

    if data.context_scope is not None:
        conv.context_scope = data.context_scope

    if "folder_id" in data.model_fields_set:
        if data.folder_id is not None:
            folder = db.query(ConversationFolder).filter(
                ConversationFolder.id == data.folder_id,
                ConversationFolder.organization_id == current_org.id,
            ).first()
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")
        conv.folder_id = data.folder_id

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)

    return ConversationSummary(
        id=conv.id,
        public_id=conv.public_id,
        title=conv.title,
        folder_id=conv.folder_id,
        context_scope=conv.context_scope,
        is_active=conv.is_active,
        message_count=_message_count(conv.id, db),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


# ── DELETE /api/v1/conversations/:id ─────────────────────────────────────────


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Soft delete a conversation (sets is_active=False)."""
    conv = _get_conversation_or_404(conversation_id, current_org.id, db)
    conv.is_active = False
    conv.updated_at = datetime.utcnow()
    db.commit()
    return None
