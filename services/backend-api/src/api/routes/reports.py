"""
On-Demand AI Reports — CRUD API (M2.4).

Endpoints:
  GET    /api/v1/reports          List org's saved reports (Business+)
  GET    /api/v1/reports/{id}     Get report with full sections (Business+)
  DELETE /api/v1/reports/{id}     Delete a report (Admin+, Business+)

Report generation itself happens via the Copilot WebSocket.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
    require_feature,
)
from src.database.session import get_db
from src.models.organization import Organization
from src.models.report import Report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

# ── Response schemas ──────────────────────────────────────────────────────────


class ReportListItem(BaseModel):
    id: int
    report_type: str
    date_range_days: int
    title: Optional[str]
    pdf_generated: bool
    created_at: str

    model_config = {"from_attributes": True}


class ReportDetail(BaseModel):
    id: int
    report_type: str
    date_range_days: int
    title: Optional[str]
    sections: Optional[Any]
    metadata: Optional[Any]
    pdf_generated: bool
    created_at: str

    model_config = {"from_attributes": True}


def _serialize_report_list(report: Report) -> dict:
    return {
        "id": report.id,
        "report_type": report.report_type,
        "date_range_days": report.date_range_days,
        "title": report.title,
        "pdf_generated": report.pdf_generated,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def _serialize_report_detail(report: Report) -> dict:
    return {
        "id": report.id,
        "report_type": report.report_type,
        "date_range_days": report.date_range_days,
        "title": report.title,
        "sections": report.sections,
        "metadata": report.report_metadata,
        "pdf_generated": report.pdf_generated,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    dependencies=[Depends(require_feature("ai_reports"))],
)
def list_reports(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> List[dict]:
    """List all saved reports for the current organization, newest first."""
    reports = (
        db.query(Report)
        .filter(Report.organization_id == current_org.id)
        .order_by(Report.created_at.desc())
        .all()
    )
    return [_serialize_report_list(r) for r in reports]


@router.get(
    "/{report_id}",
    dependencies=[Depends(require_feature("ai_reports"))],
)
def get_report(
    report_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> dict:
    """Get a single report with full section data."""
    report = (
        db.query(Report)
        .filter(
            Report.id == report_id,
            Report.organization_id == current_org.id,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return _serialize_report_detail(report)


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[
        Depends(require_feature("ai_reports")),
        Depends(require_admin_or_owner),
    ],
)
def delete_report(
    report_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> None:
    """Delete a report. Requires Admin or Owner role."""
    report = (
        db.query(Report)
        .filter(
            Report.id == report_id,
            Report.organization_id == current_org.id,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    db.delete(report)
    db.commit()
