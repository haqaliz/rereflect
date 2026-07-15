"""
CRM churn-suggestion review queue (review-queue aspect, M5).

This is the feature's whole trust boundary: a `ChurnLabelSuggestion` row is
a CRM's guess. Confirm is the ONLY code path that turns it into a real
CustomerChurnEvent(source='manual') the calibrator can fit on — no
auto-confirm exists. See docs/planning/crm-churn-labels/review-queue/spec.md.

All routes are org-scoped, require_admin_or_owner (deliberate divergence
from churn_events.py's role-less routes — not fixed here, see plan §7), and
require_feature("advanced_churn_prediction").
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
    require_feature,
)
from src.api.routes.churn_events import _get_active_churn_event, _invalidate_probability
from src.database.session import get_db
from src.models.churn_event import CustomerChurnEvent
from src.models.churn_label_suggestion import (
    CHURN_SUGGESTION_STATUSES,
    ChurnLabelSuggestion,
)
from src.models.organization import Organization
from src.models.user import User
from src.schemas.churn_suggestion import (
    ChurnSuggestionListResponse,
    ChurnSuggestionResponse,
    ConfirmRequest,
    RejectRequest,
    SuggestionActionResponse,
)

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["churn-suggestions"],
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("advanced_churn_prediction")),
    ],
)


class _Collision(Exception):
    """Raised by _confirm_one when the INSERT collides on the
    (org, email, churned_at) UNIQUE constraint. Callers resolve it."""


def _confirm_one(
    db: Session,
    org: Organization,
    user: User,
    suggestion: ChurnLabelSuggestion,
    reason_code: str,
    reason_text: Optional[str],
) -> tuple:
    """Confirm one suggestion — the single write path shared by the single
    and (later) bulk confirm routes. One write path, one collision policy.

    Never commits, never rolls back — the caller owns the transaction so
    that bulk can wrap this in a SAVEPOINT without the helper fighting the
    outer transaction.

    Collision handling (R-B, non-negotiable): if the customer already has
    an active churn event, this resolves the suggestion to the PRE-EXISTING
    event rather than leaving it `pending` forever (which would re-surface
    an unactionable row every day). This deliberately attributes an event
    this action did not create — the honesty lives in the wire
    (`reason: "already_marked"`) and the toast, not in the DB.

    Returns (status, reason, churn_event_id).
    """
    if suggestion.status != "pending":
        return ("skipped", "not_pending", suggestion.churn_event_id)

    # Defense 1 — pre-check (racy, hence defense 2 below).
    existing = _get_active_churn_event(db, org.id, suggestion.customer_email)
    if existing:
        suggestion.status = "confirmed"
        suggestion.churn_event_id = existing.id
        suggestion.reviewed_by_user_id = user.id
        suggestion.reviewed_at = datetime.utcnow()
        return ("skipped", "already_marked", existing.id)

    event = CustomerChurnEvent(
        organization_id=org.id,
        customer_email=suggestion.customer_email,
        churned_at=suggestion.suggested_churned_at,
        reason_code=reason_code,
        reason_text=reason_text,
        marked_by_user_id=user.id,
        source="manual",
    )
    try:
        db.add(event)
        db.flush()
    except IntegrityError:
        # Defense 2 — backstop for the race between the pre-check and this
        # flush. Caller owns rollback/SAVEPOINT release.
        raise _Collision()

    suggestion.status = "confirmed"
    suggestion.churn_event_id = event.id
    suggestion.reviewed_by_user_id = user.id
    suggestion.reviewed_at = datetime.utcnow()
    return ("confirmed", None, event.id)


def _reject_one(db: Session, user: User, suggestion: ChurnLabelSuggestion) -> tuple:
    """Reject one suggestion. No event written, churn_event_id stays NULL.

    Non-pending target is idempotent -> ("skipped", "not_pending", ...).
    Returns (status, reason, churn_event_id) — status is 'rejected' on a
    fresh reject, matching the persisted DB value (unlike confirm's
    collision case, reject has no wire/DB divergence).
    """
    if suggestion.status != "pending":
        return ("skipped", "not_pending", suggestion.churn_event_id)

    suggestion.status = "rejected"
    suggestion.reviewed_by_user_id = user.id
    suggestion.reviewed_at = datetime.utcnow()
    return ("rejected", None, None)


def _get_suggestion_or_404(
    db: Session, org: Organization, suggestion_id: int
) -> ChurnLabelSuggestion:
    row = (
        db.query(ChurnLabelSuggestion)
        .filter(
            ChurnLabelSuggestion.id == suggestion_id,
            ChurnLabelSuggestion.organization_id == org.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Churn suggestion {suggestion_id} not found.",
        )
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# NOTE: static paths (/churn-suggestions/bulk) MUST be registered before
# parametric paths (/churn-suggestions/{id}/...) — churn_events.py:157-159
# warns about exactly this FastAPI path-matching pitfall. (No parametric
# path exists yet in Phase 1.)


@router.get("/churn-suggestions", response_model=ChurnSuggestionListResponse)
def list_churn_suggestions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str = Query(
        CHURN_SUGGESTION_STATUSES[0], alias="status", description="pending|confirmed|rejected"
    ),
    provider: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ChurnSuggestionListResponse:
    """List this org's CRM churn suggestions, paginated."""
    if status_filter not in CHURN_SUGGESTION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(CHURN_SUGGESTION_STATUSES)}",
        )

    query = db.query(ChurnLabelSuggestion).filter(
        ChurnLabelSuggestion.organization_id == current_org.id,
        ChurnLabelSuggestion.status == status_filter,
    )

    if provider:
        query = query.filter(ChurnLabelSuggestion.provider == provider)
    if search:
        query = query.filter(ChurnLabelSuggestion.customer_email.ilike(f"%{search}%"))

    total = query.count()
    offset = (page - 1) * page_size
    records = (
        query.order_by(
            ChurnLabelSuggestion.suggested_churned_at.desc(), ChurnLabelSuggestion.id.desc()
        )
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return ChurnSuggestionListResponse(
        items=[ChurnSuggestionResponse.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/churn-suggestions/{suggestion_id}/confirm", response_model=SuggestionActionResponse
)
def confirm_churn_suggestion(
    suggestion_id: int,
    body: ConfirmRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestionActionResponse:
    """Confirm a suggestion — writes CustomerChurnEvent(source='manual').

    Never 500, never 409 (that is churn_events.py's contract, not ours) — a
    collision resolves the suggestion to `status='confirmed'` **in the DB**
    (R-B — it leaves the queue) but reports `status='skipped'` **on the
    wire**, so the operator knows their action didn't create the event (see
    _confirm_one's docstring and SuggestionActionResponse).
    """
    suggestion = _get_suggestion_or_404(db, current_org, suggestion_id)

    try:
        item_status, reason, ev_id = _confirm_one(
            db, current_org, current_user, suggestion, body.reason_code, body.reason_text
        )
        db.commit()
    except _Collision:
        db.rollback()
        # Re-fetch — the collision means an active event now exists.
        suggestion = _get_suggestion_or_404(db, current_org, suggestion_id)
        existing = _get_active_churn_event(db, current_org.id, suggestion.customer_email)
        suggestion.status = "confirmed"
        suggestion.churn_event_id = existing.id if existing else None
        suggestion.reviewed_by_user_id = current_user.id
        suggestion.reviewed_at = datetime.utcnow()
        db.commit()
        item_status, reason, ev_id = "skipped", "already_marked", suggestion.churn_event_id

    db.refresh(suggestion)

    # Confirm MUST call _invalidate_probability on every write path,
    # including the collision-resolved skip (a real event now exists for
    # this customer either way).
    _invalidate_probability(db, current_org.id, suggestion.customer_email)

    return SuggestionActionResponse(
        id=suggestion.id, status=item_status, churn_event_id=ev_id, reason=reason
    )


@router.post("/churn-suggestions/{suggestion_id}/reject", response_model=SuggestionActionResponse)
def reject_churn_suggestion(
    suggestion_id: int,
    body: RejectRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> SuggestionActionResponse:
    """Reject a suggestion. No event written; never re-suggested (the
    harvester's natural-key upsert already prevents rejected->pending
    resurrection — asserted, not built, here).

    `body.note` is accepted but persisted nowhere today (no column) — a
    documented gap, not a silent discard. TODO: add a `review_note` column.
    """
    suggestion = _get_suggestion_or_404(db, current_org, suggestion_id)
    item_status, reason, ev_id = _reject_one(db, current_user, suggestion)
    db.commit()
    db.refresh(suggestion)
    return SuggestionActionResponse(
        id=suggestion.id, status=item_status, churn_event_id=ev_id, reason=reason
    )
