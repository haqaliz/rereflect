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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_org, require_admin_or_owner, require_feature
from src.database.session import get_db
from src.models.churn_label_suggestion import (
    CHURN_SUGGESTION_STATUSES,
    ChurnLabelSuggestion,
)
from src.models.organization import Organization
from src.schemas.churn_suggestion import (
    ChurnSuggestionListResponse,
    ChurnSuggestionResponse,
)

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["churn-suggestions"],
    dependencies=[
        Depends(require_admin_or_owner),
        Depends(require_feature("advanced_churn_prediction")),
    ],
)


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
