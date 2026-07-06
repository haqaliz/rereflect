"""
Workflow API routes — status tracking, assignment, notes, timeline, assignment rules.
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from pydantic import BaseModel

from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.feedback_note import FeedbackNote
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.assignment_rule import AssignmentRule
from src.models.user import User
from src.models.organization import Organization
from src.api.dependencies import get_current_user, get_current_org
from src.services.workflow_service import (
    create_workflow_event,
    apply_status_change,
    dispatch_status_webhooks,
)
from src.services.event_emitter import emit_event

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])

VALID_STATUSES = ["new", "in_review", "resolved", "closed"]


# ── Schemas ──────────────────────────────────────────────────

class StatusChangeRequest(BaseModel):
    feedback_ids: List[int]
    new_status: str
    resolution_note: Optional[str] = None


class AssignRequest(BaseModel):
    feedback_ids: List[int]
    assign_to_user_id: Optional[int] = None  # None = unassign


class NoteCreateRequest(BaseModel):
    content: str


class NoteUpdateRequest(BaseModel):
    content: str


class AssignmentRuleCreateRequest(BaseModel):
    match_field: str
    match_value: str
    assign_to_user_id: int
    priority: int = 0
    is_active: bool = True


class AssignmentRuleUpdateRequest(BaseModel):
    match_field: Optional[str] = None
    match_value: Optional[str] = None
    assign_to_user_id: Optional[int] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class NoteResponse(BaseModel):
    id: int
    feedback_id: int
    author_id: int
    author_email: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TimelineEventResponse(BaseModel):
    id: int
    feedback_id: int
    actor_id: int
    actor_email: str
    event_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowFeedbackItem(BaseModel):
    id: int
    text: str
    source: Optional[str] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    is_urgent: bool
    workflow_status: str
    assigned_to: Optional[int] = None
    assigned_to_email: Optional[str] = None
    created_at: datetime
    churn_risk_score: Optional[int] = None

    class Config:
        from_attributes = True


class WorkflowOverviewResponse(BaseModel):
    items: List[WorkflowFeedbackItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    status_counts: dict


class AssignmentRuleResponse(BaseModel):
    id: int
    organization_id: int
    rule_type: str
    match_field: str
    match_value: str
    assign_to_user_id: int
    assign_to_email: str
    priority: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Status + Assignment ──────────────────────────────────────

@router.post("/status")
async def change_status(
    data: StatusChangeRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Bulk status change for feedback items."""
    if data.new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    feedbacks = db.query(FeedbackItem).filter(
        FeedbackItem.id.in_(data.feedback_ids),
        FeedbackItem.organization_id == current_org.id,
    ).all()

    if not feedbacks:
        raise HTTPException(status_code=404, detail="No matching feedback found")

    status_changes = apply_status_change(
        db, feedbacks, data.new_status,
        organization_id=current_org.id,
        actor_id=current_user.id,
        actor_label=current_user.email,
        resolution_note=data.resolution_note,
    )
    updated = len(status_changes)

    db.commit()

    # Invalidate dashboard/analytics cache for this org
    from src.services.cache_service import cache_invalidate
    cache_invalidate(f"dashboard:{current_org.id}:*")
    cache_invalidate(f"analytics:{current_org.id}:*")

    # Dispatch notifications (fire-and-forget)
    try:
        from src.notification_dispatch_helpers import dispatch_status_changed
        dispatch_status_changed(current_org.id, current_user, feedbacks, data.new_status)
    except Exception:
        pass

    # Dispatch webhook events for status changes (fire-and-forget)
    try:
        dispatch_status_webhooks(
            db, current_org.id, status_changes, data.new_status,
            changed_by_label=current_user.email,
        )
    except Exception:
        pass

    if updated > 0:
        await emit_event(
            org_id=current_org.id,
            event_type="workflow:status_changed",
            data={"feedback_ids": data.feedback_ids, "new_status": data.new_status},
        )

    return {"updated": updated}


@router.post("/assign")
async def assign_feedback(
    data: AssignRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Bulk assign/unassign feedback items."""
    # Validate assignee if provided
    assignee = None
    if data.assign_to_user_id is not None:
        assignee = db.query(User).filter(
            User.id == data.assign_to_user_id,
            User.organization_id == current_org.id,
        ).first()
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found in organization")

    feedbacks = db.query(FeedbackItem).filter(
        FeedbackItem.id.in_(data.feedback_ids),
        FeedbackItem.organization_id == current_org.id,
    ).all()

    if not feedbacks:
        raise HTTPException(status_code=404, detail="No matching feedback found")

    updated = 0
    for fb in feedbacks:
        old_assignee_id = fb.assigned_to
        new_assignee_id = data.assign_to_user_id

        if old_assignee_id == new_assignee_id:
            continue

        fb.assigned_to = new_assignee_id

        # Get emails for timeline event
        old_email = None
        if old_assignee_id:
            old_user = db.query(User).filter(User.id == old_assignee_id).first()
            old_email = old_user.email if old_user else None

        new_email = assignee.email if assignee else None

        event_type = "assigned" if new_assignee_id else "unassigned"
        create_workflow_event(
            db, fb.id, current_org.id, current_user.id,
            event_type, old_value=old_email, new_value=new_email,
        )
        updated += 1

    db.commit()

    # Dispatch notifications
    try:
        from src.notification_dispatch_helpers import dispatch_feedback_assigned
        if assignee:
            dispatch_feedback_assigned(current_org.id, current_user, assignee, feedbacks)
    except Exception:
        pass

    if updated > 0:
        await emit_event(
            org_id=current_org.id,
            event_type="workflow:assigned",
            data={"feedback_ids": data.feedback_ids, "assignee_id": data.assign_to_user_id},
        )

    return {"updated": updated}


# ── Overview ─────────────────────────────────────────────────

@router.get("/overview", response_model=WorkflowOverviewResponse)
def get_overview(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workflow_status: Optional[str] = Query(None),
    assigned_to: Optional[int] = Query(None),
    sentiment: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("desc"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Paginated workflow overview with status counts."""
    query = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id,
    )

    if workflow_status:
        query = query.filter(FeedbackItem.workflow_status == workflow_status)
    if assigned_to is not None:
        query = query.filter(FeedbackItem.assigned_to == assigned_to)
    if sentiment:
        query = query.filter(FeedbackItem.sentiment_label == sentiment)
    if search:
        query = query.filter(FeedbackItem.text.ilike(f"%{search}%"))

    total = query.count()
    total_pages = (total + page_size - 1) // page_size

    sort_map = {
        "created_at": FeedbackItem.created_at,
        "workflow_status": FeedbackItem.workflow_status,
        "sentiment_score": FeedbackItem.sentiment_score,
    }
    sort_col = sort_map.get(sort_by, FeedbackItem.created_at)
    order_fn = asc if sort_order == "asc" else desc

    items = query.order_by(order_fn(sort_col)).offset((page - 1) * page_size).limit(page_size).all()

    # Get assignee emails
    assignee_ids = [i.assigned_to for i in items if i.assigned_to]
    assignee_map = {}
    if assignee_ids:
        users = db.query(User).filter(User.id.in_(assignee_ids)).all()
        assignee_map = {u.id: u.email for u in users}

    response_items = []
    for item in items:
        response_items.append(WorkflowFeedbackItem(
            id=item.id,
            text=item.text,
            source=item.source,
            sentiment_label=item.sentiment_label,
            sentiment_score=item.sentiment_score,
            is_urgent=item.is_urgent,
            workflow_status=item.workflow_status,
            assigned_to=item.assigned_to,
            assigned_to_email=assignee_map.get(item.assigned_to),
            created_at=item.created_at,
            churn_risk_score=item.churn_risk_score,
        ))

    # Status counts (unfiltered for the org)
    counts_query = db.query(
        FeedbackItem.workflow_status,
        func.count(FeedbackItem.id),
    ).filter(
        FeedbackItem.organization_id == current_org.id,
    ).group_by(FeedbackItem.workflow_status).all()

    status_counts = {s: 0 for s in VALID_STATUSES}
    for s, c in counts_query:
        status_counts[s] = c

    return WorkflowOverviewResponse(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        status_counts=status_counts,
    )


@router.get("/status-counts")
def get_status_counts(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get status counts for the org."""
    counts = db.query(
        FeedbackItem.workflow_status,
        func.count(FeedbackItem.id),
    ).filter(
        FeedbackItem.organization_id == current_org.id,
    ).group_by(FeedbackItem.workflow_status).all()

    result = {s: 0 for s in VALID_STATUSES}
    for s, c in counts:
        result[s] = c
    return result


# ── Timeline ─────────────────────────────────────────────────

@router.get("/{feedback_id}/timeline", response_model=List[TimelineEventResponse])
def get_timeline(
    feedback_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get timeline events for a feedback item."""
    # Verify feedback belongs to org
    fb = db.query(FeedbackItem).filter(
        FeedbackItem.id == feedback_id,
        FeedbackItem.organization_id == current_org.id,
    ).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    events = db.query(FeedbackWorkflowEvent).filter(
        FeedbackWorkflowEvent.feedback_id == feedback_id,
        FeedbackWorkflowEvent.organization_id == current_org.id,
    ).order_by(FeedbackWorkflowEvent.created_at.desc()).all()

    # Get actor emails
    actor_ids = list(set(e.actor_id for e in events))
    actor_map = {}
    if actor_ids:
        users = db.query(User).filter(User.id.in_(actor_ids)).all()
        actor_map = {u.id: u.email for u in users}

    return [
        TimelineEventResponse(
            id=e.id,
            feedback_id=e.feedback_id,
            actor_id=e.actor_id,
            actor_email=actor_map.get(e.actor_id, "unknown"),
            event_type=e.event_type,
            old_value=e.old_value,
            new_value=e.new_value,
            metadata=e.metadata_,
            created_at=e.created_at,
        )
        for e in events
    ]


# ── Notes ────────────────────────────────────────────────────

@router.get("/{feedback_id}/notes", response_model=List[NoteResponse])
def list_notes(
    feedback_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List notes for a feedback item."""
    fb = db.query(FeedbackItem).filter(
        FeedbackItem.id == feedback_id,
        FeedbackItem.organization_id == current_org.id,
    ).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    notes = db.query(FeedbackNote).filter(
        FeedbackNote.feedback_id == feedback_id,
        FeedbackNote.organization_id == current_org.id,
    ).order_by(FeedbackNote.created_at.desc()).all()

    author_ids = list(set(n.author_id for n in notes))
    author_map = {}
    if author_ids:
        users = db.query(User).filter(User.id.in_(author_ids)).all()
        author_map = {u.id: u.email for u in users}

    return [
        NoteResponse(
            id=n.id,
            feedback_id=n.feedback_id,
            author_id=n.author_id,
            author_email=author_map.get(n.author_id, "unknown"),
            content=n.content,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )
        for n in notes
    ]


@router.post("/{feedback_id}/notes", response_model=NoteResponse, status_code=201)
async def create_note(
    feedback_id: int,
    data: NoteCreateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a note on a feedback item."""
    fb = db.query(FeedbackItem).filter(
        FeedbackItem.id == feedback_id,
        FeedbackItem.organization_id == current_org.id,
    ).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Note content cannot be empty")

    note = FeedbackNote(
        feedback_id=feedback_id,
        organization_id=current_org.id,
        author_id=current_user.id,
        content=data.content.strip(),
        created_at=datetime.utcnow(),
    )
    db.add(note)

    create_workflow_event(
        db, feedback_id, current_org.id, current_user.id,
        "note_added", new_value=data.content[:100],
        metadata={"note_id": None},  # Will be set after flush
    )

    db.flush()
    # Update the event metadata with the actual note ID
    last_event = db.query(FeedbackWorkflowEvent).filter(
        FeedbackWorkflowEvent.feedback_id == feedback_id,
        FeedbackWorkflowEvent.event_type == "note_added",
    ).order_by(FeedbackWorkflowEvent.created_at.desc()).first()
    if last_event:
        last_event.metadata_ = {"note_id": note.id}

    db.commit()
    db.refresh(note)

    # Dispatch notifications
    try:
        from src.notification_dispatch_helpers import dispatch_note_added
        dispatch_note_added(current_org.id, current_user, fb, note)
    except Exception:
        pass

    await emit_event(
        org_id=current_org.id,
        event_type="workflow:note_added",
        data={"feedback_id": feedback_id, "note_id": note.id},
    )

    return NoteResponse(
        id=note.id,
        feedback_id=note.feedback_id,
        author_id=note.author_id,
        author_email=current_user.email,
        content=note.content,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.patch("/notes/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    data: NoteUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update a note (author only)."""
    note = db.query(FeedbackNote).filter(
        FeedbackNote.id == note_id,
        FeedbackNote.organization_id == current_org.id,
    ).first()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can edit this note")
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Note content cannot be empty")

    old_content = note.content[:100]
    note.content = data.content.strip()
    note.updated_at = datetime.utcnow()

    create_workflow_event(
        db, note.feedback_id, current_org.id, current_user.id,
        "note_edited", old_value=old_content, new_value=data.content[:100],
        metadata={"note_id": note.id},
    )

    db.commit()
    db.refresh(note)

    return NoteResponse(
        id=note.id,
        feedback_id=note.feedback_id,
        author_id=note.author_id,
        author_email=current_user.email,
        content=note.content,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a note (author only)."""
    note = db.query(FeedbackNote).filter(
        FeedbackNote.id == note_id,
        FeedbackNote.organization_id == current_org.id,
    ).first()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can delete this note")

    create_workflow_event(
        db, note.feedback_id, current_org.id, current_user.id,
        "note_deleted", old_value=note.content[:100],
        metadata={"note_id": note.id},
    )

    db.delete(note)
    db.commit()
    return None


# ── Assignment Rules ─────────────────────────────────────────

@router.get("/assignment-rules", response_model=List[AssignmentRuleResponse])
def list_assignment_rules(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List assignment rules for the org."""
    rules = db.query(AssignmentRule).filter(
        AssignmentRule.organization_id == current_org.id,
    ).order_by(AssignmentRule.priority.desc()).all()

    user_ids = list(set(r.assign_to_user_id for r in rules))
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.email for u in users}

    return [
        AssignmentRuleResponse(
            id=r.id,
            organization_id=r.organization_id,
            rule_type=r.rule_type,
            match_field=r.match_field,
            match_value=r.match_value,
            assign_to_user_id=r.assign_to_user_id,
            assign_to_email=user_map.get(r.assign_to_user_id, "unknown"),
            priority=r.priority,
            is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in rules
    ]


@router.post("/assignment-rules", response_model=AssignmentRuleResponse, status_code=201)
def create_assignment_rule(
    data: AssignmentRuleCreateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create an assignment rule."""
    # Validate assignee
    assignee = db.query(User).filter(
        User.id == data.assign_to_user_id,
        User.organization_id == current_org.id,
    ).first()
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee not found in organization")

    rule = AssignmentRule(
        organization_id=current_org.id,
        rule_type="category",
        match_field=data.match_field,
        match_value=data.match_value,
        assign_to_user_id=data.assign_to_user_id,
        priority=data.priority,
        is_active=data.is_active,
        created_at=datetime.utcnow(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    return AssignmentRuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        rule_type=rule.rule_type,
        match_field=rule.match_field,
        match_value=rule.match_value,
        assign_to_user_id=rule.assign_to_user_id,
        assign_to_email=assignee.email,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.patch("/assignment-rules/{rule_id}", response_model=AssignmentRuleResponse)
def update_assignment_rule(
    rule_id: int,
    data: AssignmentRuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update an assignment rule."""
    rule = db.query(AssignmentRule).filter(
        AssignmentRule.id == rule_id,
        AssignmentRule.organization_id == current_org.id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if data.match_field is not None:
        rule.match_field = data.match_field
    if data.match_value is not None:
        rule.match_value = data.match_value
    if data.assign_to_user_id is not None:
        assignee = db.query(User).filter(
            User.id == data.assign_to_user_id,
            User.organization_id == current_org.id,
        ).first()
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found in organization")
        rule.assign_to_user_id = data.assign_to_user_id
    if data.priority is not None:
        rule.priority = data.priority
    if data.is_active is not None:
        rule.is_active = data.is_active

    db.commit()
    db.refresh(rule)

    assignee = db.query(User).filter(User.id == rule.assign_to_user_id).first()

    return AssignmentRuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        rule_type=rule.rule_type,
        match_field=rule.match_field,
        match_value=rule.match_value,
        assign_to_user_id=rule.assign_to_user_id,
        assign_to_email=assignee.email if assignee else "unknown",
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.delete("/assignment-rules/{rule_id}", status_code=204)
def delete_assignment_rule(
    rule_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete an assignment rule."""
    rule = db.query(AssignmentRule).filter(
        AssignmentRule.id == rule_id,
        AssignmentRule.organization_id == current_org.id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return None


# ── Auto-Assignment Settings ─────────────────────────────────

@router.get("/auto-assignment-settings")
def get_auto_assignment_settings(
    current_org: Organization = Depends(get_current_org),
):
    """Get auto-assignment settings for the org."""
    return {"auto_assignment_enabled": current_org.auto_assignment_enabled}


@router.patch("/auto-assignment-settings")
def update_auto_assignment_settings(
    data: dict,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update auto-assignment settings."""
    if "auto_assignment_enabled" in data:
        current_org.auto_assignment_enabled = bool(data["auto_assignment_enabled"])
        db.commit()
    return {"auto_assignment_enabled": current_org.auto_assignment_enabled}
