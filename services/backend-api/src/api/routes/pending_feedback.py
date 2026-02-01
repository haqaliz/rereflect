"""
Pending Feedback API - Endpoints for reviewing and approving/rejecting pending feedback items.
"""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.api.dependencies import get_current_org, get_current_user
from src.models import Organization, User, PendingFeedback, FeedbackSource, FeedbackSourceEvent, FeedbackItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pending-feedback", tags=["pending-feedback"])


# ============ Pydantic Schemas ============

class PendingFeedbackResponse(BaseModel):
    """Response model for a pending feedback item."""
    id: int
    source_id: int
    source_type: str
    source_name: Optional[str]
    organization_id: int
    event_id: int
    text: str
    source_metadata: Optional[dict]
    trigger_type: Optional[str]
    status: str
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class PendingFeedbackListResponse(BaseModel):
    """Response model for listing pending feedback."""
    items: List[PendingFeedbackResponse]
    total: int
    page: int
    page_size: int


class BulkActionRequest(BaseModel):
    """Request body for bulk actions."""
    ids: List[int]


class BulkActionResponse(BaseModel):
    """Response model for bulk actions."""
    processed: int
    failed: int
    errors: List[str]


class FeedbackResponse(BaseModel):
    """Response model for created feedback."""
    id: int
    organization_id: int
    text: str
    source: Optional[str]
    source_id: Optional[int]
    source_external_id: Optional[str]
    source_metadata: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Helper Functions ============

def _get_pending_or_404(db: Session, pending_id: int, org_id: int) -> PendingFeedback:
    """Get a pending feedback item or raise 404."""
    pending = db.query(PendingFeedback).filter(
        PendingFeedback.id == pending_id,
        PendingFeedback.organization_id == org_id,
    ).first()

    if not pending:
        raise HTTPException(status_code=404, detail="Pending feedback not found")

    return pending


def _create_feedback_from_pending(
    db: Session,
    pending: PendingFeedback,
    user: User,
) -> FeedbackItem:
    """Create a FeedbackItem from a pending item."""
    from src.background import queue_analyze_feedback

    # Get the source for metadata
    source = db.query(FeedbackSource).filter(
        FeedbackSource.id == pending.source_id
    ).first()

    # Get the event for external ID
    event = db.query(FeedbackSourceEvent).filter(
        FeedbackSourceEvent.id == pending.event_id
    ).first()

    # Create the feedback item
    feedback = FeedbackItem(
        organization_id=pending.organization_id,
        text=pending.text,
        source=source.source_type if source else "unknown",
        source_id=pending.source_id,
        source_external_id=event.external_message_id if event else None,
        source_metadata=pending.source_metadata,
    )

    db.add(feedback)

    # Update pending status
    pending.status = "approved"
    pending.reviewed_at = datetime.utcnow()
    pending.reviewed_by = user.id

    # Update event with feedback_id
    if event:
        event.status = "processed"
        event.feedback_id = feedback.id
        event.pending_feedback_id = None
        event.processed_at = datetime.utcnow()

    db.flush()  # Get feedback.id

    # Update source stats
    if source:
        source.events_processed = (source.events_processed or 0) + 1

    db.commit()
    db.refresh(feedback)

    # Queue for analysis
    try:
        queue_analyze_feedback(feedback.id)
    except Exception as e:
        logger.error(f"Failed to queue analysis for feedback {feedback.id}: {e}")

    return feedback


# ============ Endpoints ============

@router.get("/", response_model=PendingFeedbackListResponse)
def list_pending_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    source_id: Optional[int] = Query(None, description="Filter by source ID"),
    status: str = Query("pending", description="Filter by status"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List pending feedback items."""
    query = db.query(PendingFeedback).filter(
        PendingFeedback.organization_id == current_org.id,
    )

    if status:
        query = query.filter(PendingFeedback.status == status)

    if source_id:
        query = query.filter(PendingFeedback.source_id == source_id)

    if source_type:
        # Join with FeedbackSource to filter by type
        query = query.join(FeedbackSource).filter(
            FeedbackSource.source_type == source_type
        )

    total = query.count()

    items = query.order_by(PendingFeedback.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    # Build response with source info
    response_items = []
    for item in items:
        source = db.query(FeedbackSource).filter(
            FeedbackSource.id == item.source_id
        ).first()

        response_items.append(PendingFeedbackResponse(
            id=item.id,
            source_id=item.source_id,
            source_type=source.source_type if source else "unknown",
            source_name=source.name if source else None,
            organization_id=item.organization_id,
            event_id=item.event_id,
            text=item.text,
            source_metadata=item.source_metadata,
            trigger_type=item.trigger_type,
            status=item.status,
            reviewed_at=item.reviewed_at,
            reviewed_by=item.reviewed_by,
            created_at=item.created_at,
        ))

    return PendingFeedbackListResponse(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{pending_id}", response_model=PendingFeedbackResponse)
def get_pending_feedback(
    pending_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get a specific pending feedback item."""
    pending = _get_pending_or_404(db, pending_id, current_org.id)

    source = db.query(FeedbackSource).filter(
        FeedbackSource.id == pending.source_id
    ).first()

    return PendingFeedbackResponse(
        id=pending.id,
        source_id=pending.source_id,
        source_type=source.source_type if source else "unknown",
        source_name=source.name if source else None,
        organization_id=pending.organization_id,
        event_id=pending.event_id,
        text=pending.text,
        source_metadata=pending.source_metadata,
        trigger_type=pending.trigger_type,
        status=pending.status,
        reviewed_at=pending.reviewed_at,
        reviewed_by=pending.reviewed_by,
        created_at=pending.created_at,
    )


@router.post("/{pending_id}/approve", response_model=FeedbackResponse)
def approve_pending_feedback(
    pending_id: int,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a pending feedback item and create feedback."""
    pending = _get_pending_or_404(db, pending_id, current_org.id)

    if pending.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve item with status '{pending.status}'"
        )

    feedback = _create_feedback_from_pending(db, pending, current_user)

    return FeedbackResponse(
        id=feedback.id,
        organization_id=feedback.organization_id,
        text=feedback.text,
        source=feedback.source,
        source_id=feedback.source_id,
        source_external_id=feedback.source_external_id,
        source_metadata=feedback.source_metadata,
        created_at=feedback.created_at,
    )


@router.post("/{pending_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_pending_feedback(
    pending_id: int,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pending feedback item."""
    pending = _get_pending_or_404(db, pending_id, current_org.id)

    if pending.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject item with status '{pending.status}'"
        )

    pending.status = "rejected"
    pending.reviewed_at = datetime.utcnow()
    pending.reviewed_by = current_user.id

    # Update the event status
    event = db.query(FeedbackSourceEvent).filter(
        FeedbackSourceEvent.id == pending.event_id
    ).first()

    if event:
        event.status = "ignored"
        event.processed_at = datetime.utcnow()

    db.commit()


@router.post("/bulk-approve", response_model=BulkActionResponse)
def bulk_approve_pending_feedback(
    data: BulkActionRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve multiple pending feedback items."""
    processed = 0
    failed = 0
    errors = []

    for pending_id in data.ids:
        try:
            pending = db.query(PendingFeedback).filter(
                PendingFeedback.id == pending_id,
                PendingFeedback.organization_id == current_org.id,
                PendingFeedback.status == "pending",
            ).first()

            if not pending:
                failed += 1
                errors.append(f"Item {pending_id} not found or already processed")
                continue

            _create_feedback_from_pending(db, pending, current_user)
            processed += 1

        except Exception as e:
            failed += 1
            errors.append(f"Item {pending_id}: {str(e)}")
            logger.error(f"Failed to approve pending {pending_id}: {e}")

    return BulkActionResponse(processed=processed, failed=failed, errors=errors)


@router.post("/bulk-reject", response_model=BulkActionResponse)
def bulk_reject_pending_feedback(
    data: BulkActionRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject multiple pending feedback items."""
    processed = 0
    failed = 0
    errors = []

    for pending_id in data.ids:
        try:
            pending = db.query(PendingFeedback).filter(
                PendingFeedback.id == pending_id,
                PendingFeedback.organization_id == current_org.id,
                PendingFeedback.status == "pending",
            ).first()

            if not pending:
                failed += 1
                errors.append(f"Item {pending_id} not found or already processed")
                continue

            pending.status = "rejected"
            pending.reviewed_at = datetime.utcnow()
            pending.reviewed_by = current_user.id

            # Update the event status
            event = db.query(FeedbackSourceEvent).filter(
                FeedbackSourceEvent.id == pending.event_id
            ).first()

            if event:
                event.status = "ignored"
                event.processed_at = datetime.utcnow()

            processed += 1

        except Exception as e:
            failed += 1
            errors.append(f"Item {pending_id}: {str(e)}")
            logger.error(f"Failed to reject pending {pending_id}: {e}")

    db.commit()
    return BulkActionResponse(processed=processed, failed=failed, errors=errors)
