"""
AI Human-in-the-Loop corrections API (Track B, M3.8).

Endpoints:
  POST  /api/v1/ai-corrections          Submit a correction/rating (any authenticated user)
  GET   /api/v1/ai-corrections/stats    Correction stats for AI Settings page (any auth user)
  GET   /api/v1/ai-corrections          List corrections, paginated (admin/owner only)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.session import get_db
from src.models.ai_correction import AICorrection
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import (
    get_current_user,
    get_current_org,
    require_admin_or_owner,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai-corrections", tags=["ai-corrections"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class CorrectionCreate(BaseModel):
    correction_type: str = Field(..., max_length=50)
    entity_type: str = Field(..., max_length=50)
    entity_id: Optional[int] = None
    signal: str = Field(..., max_length=20)
    original_value: Optional[str] = None
    corrected_value: Optional[str] = None
    feedback_text: Optional[str] = None


class CorrectionResponse(BaseModel):
    id: int
    correction_type: str
    entity_type: str
    entity_id: Optional[int]
    signal: str
    original_value: Optional[str]
    corrected_value: Optional[str]
    feedback_text: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class MostCorrectedItem(BaseModel):
    category: str
    count: int


class CorrectionStats(BaseModel):
    total: int
    this_month: int
    by_type: Dict[str, int]
    most_corrected: List[MostCorrectedItem]


class PaginatedCorrections(BaseModel):
    items: List[CorrectionResponse]
    total: int
    page: int
    page_size: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _serialize(correction: AICorrection) -> dict:
    return {
        "id": correction.id,
        "correction_type": correction.correction_type,
        "entity_type": correction.entity_type,
        "entity_id": correction.entity_id,
        "signal": correction.signal,
        "original_value": correction.original_value,
        "corrected_value": correction.corrected_value,
        "feedback_text": correction.feedback_text,
        "created_at": correction.created_at.isoformat() if correction.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CorrectionResponse)
def submit_correction(
    body: CorrectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
):
    """Submit a correction or rating signal for an AI output.

    Available to all authenticated users (no plan gating).
    """
    correction = AICorrection(
        organization_id=current_org.id,
        user_id=current_user.id,
        correction_type=body.correction_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        signal=body.signal,
        original_value=body.original_value,
        corrected_value=body.corrected_value,
        feedback_text=body.feedback_text,
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    logger.info(
        "AI correction submitted org=%s user=%s type=%s signal=%s",
        current_org.id,
        current_user.id,
        body.correction_type,
        body.signal,
    )
    return _serialize(correction)


@router.get("/stats", response_model=CorrectionStats)
def get_correction_stats(
    db: Session = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
):
    """Return correction counts and breakdown for the AI Settings accuracy section."""
    org_id = current_org.id

    # Total all-time
    total = (
        db.query(func.count(AICorrection.id))
        .filter(AICorrection.organization_id == org_id)
        .scalar()
        or 0
    )

    # This calendar month
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = (
        db.query(func.count(AICorrection.id))
        .filter(
            AICorrection.organization_id == org_id,
            AICorrection.created_at >= month_start,
        )
        .scalar()
        or 0
    )

    # Breakdown by correction_type
    rows = (
        db.query(AICorrection.correction_type, func.count(AICorrection.id))
        .filter(AICorrection.organization_id == org_id)
        .group_by(AICorrection.correction_type)
        .all()
    )
    by_type: Dict[str, int] = {ct: cnt for ct, cnt in rows}

    # Most corrected original_value labels (top 5)
    top_rows = (
        db.query(AICorrection.original_value, func.count(AICorrection.id).label("cnt"))
        .filter(
            AICorrection.organization_id == org_id,
            AICorrection.original_value.isnot(None),
            AICorrection.signal == "correction",
        )
        .group_by(AICorrection.original_value)
        .order_by(func.count(AICorrection.id).desc())
        .limit(5)
        .all()
    )
    most_corrected = [
        MostCorrectedItem(category=label, count=cnt) for label, cnt in top_rows
    ]

    return CorrectionStats(
        total=total,
        this_month=this_month,
        by_type=by_type,
        most_corrected=most_corrected,
    )


@router.get("", response_model=PaginatedCorrections)
def list_corrections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    _: bool = Depends(require_admin_or_owner),
):
    """List all corrections for the organisation (admin/owner only), paginated."""
    org_id = current_org.id
    offset = (page - 1) * page_size

    total = (
        db.query(func.count(AICorrection.id))
        .filter(AICorrection.organization_id == org_id)
        .scalar()
        or 0
    )
    items = (
        db.query(AICorrection)
        .filter(AICorrection.organization_id == org_id)
        .order_by(AICorrection.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return PaginatedCorrections(
        items=[_serialize(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )
