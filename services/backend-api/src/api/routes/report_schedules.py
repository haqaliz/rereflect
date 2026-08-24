"""
Scheduled AI Reports — ReportSchedule CRUD + toggle API (backend-schedule-crud).

Endpoints:
  GET    /api/v1/report-schedules             List org's schedules (newest first)
  GET    /api/v1/report-schedules/{id}        Get one schedule
  POST   /api/v1/report-schedules             Create a schedule (admin/owner)
  PATCH  /api/v1/report-schedules/{id}        Update a schedule (admin/owner)
  DELETE /api/v1/report-schedules/{id}        Delete a schedule (admin/owner)
  POST   /api/v1/report-schedules/{id}/toggle Flip enabled (admin/owner)

All org-scoped (cross-org -> 404). Unknown fields -> 422 (extra="forbid").
`last_run_at` is worker-owned and never client-settable.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
    require_feature,
)
from src.database.session import get_db
from src.models.organization import Organization
from src.models.report_schedule import ReportSchedule
from src.models.user import User

router = APIRouter(prefix="/api/v1/report-schedules", tags=["report-schedules"])

REPORT_TYPES = Literal[
    "executive_summary", "customer_health", "feature_prioritization", "churn_risk"
]
CADENCES = Literal["daily", "weekly", "monthly"]
DATE_RANGE_DAYS = Literal[7, 30, 90]
MAX_RECIPIENTS = 20


# ── Schemas ───────────────────────────────────────────────────────────────────


class _RecipientsMixin:
    """Trim, lowercase, dedupe and cap the recipients list."""

    @field_validator("recipients", mode="before")
    @classmethod
    def _clean_recipients(cls, v):
        if v is None:
            return v
        cleaned: List[str] = []
        for email in v:
            normalized = email.strip().lower()
            if normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    @field_validator("recipients")
    @classmethod
    def _cap_recipients(cls, v):
        if v is not None and len(v) > MAX_RECIPIENTS:
            raise ValueError(
                f"recipients must contain at most {MAX_RECIPIENTS} emails"
            )
        return v

    @model_validator(mode="after")
    def _validate_cadence_conditionals(self):
        if self.cadence == "weekly" and self.day_of_week is None:
            raise ValueError("day_of_week is required when cadence is 'weekly'")
        if self.cadence == "monthly" and self.day_of_month is None:
            raise ValueError("day_of_month is required when cadence is 'monthly'")
        return self


class ReportScheduleCreate(_RecipientsMixin, BaseModel):
    report_type: REPORT_TYPES
    date_range_days: DATE_RANGE_DAYS = 30
    cadence: CADENCES
    hour_utc: int = Field(ge=0, le=23)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    day_of_month: Optional[int] = Field(default=None, ge=1, le=31)
    recipients: Optional[List[EmailStr]] = None

    model_config = {"extra": "forbid"}


class ReportScheduleUpdate(_RecipientsMixin, BaseModel):
    report_type: Optional[REPORT_TYPES] = None
    date_range_days: Optional[DATE_RANGE_DAYS] = None
    cadence: Optional[CADENCES] = None
    hour_utc: Optional[int] = Field(default=None, ge=0, le=23)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    day_of_month: Optional[int] = Field(default=None, ge=1, le=31)
    recipients: Optional[List[EmailStr]] = None

    model_config = {"extra": "forbid"}


class ReportScheduleResponse(BaseModel):
    id: int
    report_type: str
    date_range_days: int
    cadence: str
    hour_utc: int
    day_of_week: Optional[int]
    day_of_month: Optional[int]
    recipients: List[str]
    enabled: bool
    last_run_at: Optional[datetime]
    created_by_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_org_schedule(db: Session, org_id: int, schedule_id: int) -> ReportSchedule:
    schedule = (
        db.query(ReportSchedule)
        .filter(
            ReportSchedule.id == schedule_id,
            ReportSchedule.organization_id == org_id,
        )
        .first()
    )
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report schedule not found"
        )
    return schedule


def _validate_merged_cadence(schedule: ReportSchedule) -> None:
    """Re-check cadence-conditional day fields against the merged row state."""
    if schedule.cadence == "weekly" and schedule.day_of_week is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="day_of_week is required when cadence is 'weekly'",
        )
    if schedule.cadence == "monthly" and schedule.day_of_month is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="day_of_month is required when cadence is 'monthly'",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=List[ReportScheduleResponse],
    dependencies=[Depends(require_feature("ai_reports"))],
)
def list_schedules(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> List[ReportSchedule]:
    """List all report schedules for the current organization, newest first."""
    return (
        db.query(ReportSchedule)
        .filter(ReportSchedule.organization_id == current_org.id)
        .order_by(ReportSchedule.created_at.desc())
        .all()
    )


@router.get(
    "/{schedule_id}",
    response_model=ReportScheduleResponse,
    dependencies=[Depends(require_feature("ai_reports"))],
)
def get_schedule(
    schedule_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ReportSchedule:
    """Get a single report schedule."""
    return _get_org_schedule(db, current_org.id, schedule_id)


@router.post(
    "",
    response_model=ReportScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_feature("ai_reports")),
        Depends(require_admin_or_owner),
    ],
)
def create_schedule(
    payload: ReportScheduleCreate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ReportSchedule:
    """Create a report schedule. Recipients default to the creator's email."""
    recipients = payload.recipients if payload.recipients is not None else [current_user.email]
    schedule = ReportSchedule(
        organization_id=current_org.id,
        created_by_user_id=current_user.id,
        report_type=payload.report_type,
        date_range_days=payload.date_range_days,
        cadence=payload.cadence,
        hour_utc=payload.hour_utc,
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
        recipients=recipients,
        enabled=True,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.patch(
    "/{schedule_id}",
    response_model=ReportScheduleResponse,
    dependencies=[
        Depends(require_feature("ai_reports")),
        Depends(require_admin_or_owner),
    ],
)
def patch_schedule(
    schedule_id: int,
    payload: ReportScheduleUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ReportSchedule:
    """Partially update a report schedule."""
    schedule = _get_org_schedule(db, current_org.id, schedule_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    _validate_merged_cadence(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[
        Depends(require_feature("ai_reports")),
        Depends(require_admin_or_owner),
    ],
)
def delete_schedule(
    schedule_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> None:
    """Delete a report schedule. Requires Admin or Owner role."""
    schedule = _get_org_schedule(db, current_org.id, schedule_id)
    db.delete(schedule)
    db.commit()


@router.post(
    "/{schedule_id}/toggle",
    response_model=ReportScheduleResponse,
    dependencies=[
        Depends(require_feature("ai_reports")),
        Depends(require_admin_or_owner),
    ],
)
def toggle_schedule(
    schedule_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ReportSchedule:
    """Flip the enabled flag on a report schedule."""
    schedule = _get_org_schedule(db, current_org.id, schedule_id)
    schedule.enabled = not schedule.enabled
    db.commit()
    db.refresh(schedule)
    return schedule