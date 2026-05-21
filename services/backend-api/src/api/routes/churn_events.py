"""
Churn Events API routes (M4.1 Phase 2.1).

All endpoints live under /api/v1/customers and are plan-gated to Business+
via require_feature("advanced_churn_prediction"), except CSV import which
requires "churn_event_csv_import".
"""

import csv
import io
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_feature,
)
from src.database.session import get_db
from src.models.churn_event import CustomerChurnEvent, CHURN_REASON_CODES
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.schemas.churn_event import (
    ChurnEventBulkCreate,
    ChurnEventCreate,
    ChurnEventCsvRow,
    ChurnEventResponse,
)

router = APIRouter(prefix="/api/v1/customers", tags=["churn-events"])


# ---------------------------------------------------------------------------
# Internal schemas
# ---------------------------------------------------------------------------


class RecoverRequest(BaseModel):
    """Body for the /recover endpoint."""

    recovered_at: Optional[datetime] = None
    note: Optional[str] = None


class BulkSummary(BaseModel):
    """Summary returned from bulk and import endpoints."""

    created: int
    skipped: int
    errors: List[str]


class ChurnEventListResponse(BaseModel):
    """Paginated list of churn events."""

    items: List[ChurnEventResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_active_churn_event(
    db: Session, org_id: int, customer_email: str
) -> Optional[CustomerChurnEvent]:
    """Return the latest active (not recovered) churn event for a customer."""
    return (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.customer_email == customer_email,
            CustomerChurnEvent.recovered_at.is_(None),
        )
        .order_by(CustomerChurnEvent.churned_at.desc())
        .first()
    )


def _invalidate_probability(db: Session, org_id: int, customer_email: str) -> None:
    """Set probability_computed_at = NULL on the matching CustomerHealth row."""
    health = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.customer_email == customer_email,
        )
        .first()
    )
    if health:
        health.probability_computed_at = None
        db.commit()


def _parse_csv_rows(content: bytes) -> tuple[List[ChurnEventCsvRow], List[str]]:
    """Parse CSV bytes into validated ChurnEventCsvRow objects.

    Returns (valid_rows, errors) where errors are per-row human-readable strings.
    """
    valid_rows: List[ChurnEventCsvRow] = []
    errors: List[str] = []

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    for line_num, row in enumerate(reader, start=2):  # row 1 = header
        # Normalise keys — strip whitespace from keys and values
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}

        try:
            validated = ChurnEventCsvRow(
                email=row.get("email", ""),
                churned_at=row.get("churned_at", ""),
                reason_code=row.get("reason_code") or "other",
                reason_text=row.get("reason_text") or None,
            )
            valid_rows.append(validated)
        except Exception as exc:
            errors.append(f"Row {line_num}: {exc}")

    return valid_rows, errors


def _churned_at_from_csv_row(row: ChurnEventCsvRow) -> datetime:
    """Parse the churned_at string from a CSV row into a datetime."""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(row.churned_at, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {row.churned_at!r}")


def _has_existing_active_event(db: Session, org_id: int, email: str) -> bool:
    """Return True if there's already an active (not recovered) churn event."""
    return _get_active_churn_event(db, org_id, email) is not None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# NOTE: Static paths (/churn-events/bulk, /churn-events/import, /churn-events)
# MUST be registered BEFORE parametric paths (/{email}/...) to avoid FastAPI
# matching "churn-events" as an email path segment.


@router.post(
    "/churn-events/bulk",
    response_model=BulkSummary,
    dependencies=[Depends(require_feature("advanced_churn_prediction"))],
)
def bulk_mark_churned(
    body: ChurnEventBulkCreate,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BulkSummary:
    """Bulk-create churn events for multiple customer emails."""
    created = 0
    skipped = 0
    errors: List[str] = []

    for email in body.emails:
        normalized = email.strip().lower()
        if _has_existing_active_event(db, current_org.id, normalized):
            skipped += 1
            continue
        event = CustomerChurnEvent(
            organization_id=current_org.id,
            customer_email=normalized,
            churned_at=body.churned_at,
            reason_code=body.reason_code,
            reason_text=body.reason_text,
            marked_by_user_id=current_user.id,
            source="manual",
        )
        try:
            db.add(event)
            db.commit()
            db.refresh(event)
            _invalidate_probability(db, current_org.id, normalized)
            created += 1
        except IntegrityError:
            db.rollback()
            skipped += 1
        except Exception as exc:
            db.rollback()
            errors.append(f"{normalized}: {exc}")

    return BulkSummary(created=created, skipped=skipped, errors=errors)


@router.post(
    "/churn-events/import",
    response_model=BulkSummary,
    dependencies=[Depends(require_feature("churn_event_csv_import"))],
)
async def import_churn_csv(
    file: UploadFile = File(...),
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BulkSummary:
    """Import churn events from a CSV file (email, churned_at, reason_code, reason_text)."""
    content = await file.read()
    valid_rows, parse_errors = _parse_csv_rows(content)

    created = 0
    skipped = 0
    errors: List[str] = list(parse_errors)

    for row in valid_rows:
        email = row.email  # already normalized by validator
        try:
            churned_at = _churned_at_from_csv_row(row)
        except ValueError as exc:
            errors.append(f"{email}: {exc}")
            continue

        # Dedupe: skip if an event with the same (org, email, churned_at) already exists
        existing = (
            db.query(CustomerChurnEvent)
            .filter(
                CustomerChurnEvent.organization_id == current_org.id,
                CustomerChurnEvent.customer_email == email,
                CustomerChurnEvent.churned_at == churned_at,
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        event = CustomerChurnEvent(
            organization_id=current_org.id,
            customer_email=email,
            churned_at=churned_at,
            reason_code=row.reason_code,
            reason_text=row.reason_text,
            marked_by_user_id=None,
            source="csv_import",
        )
        try:
            db.add(event)
            db.commit()
            db.refresh(event)
            _invalidate_probability(db, current_org.id, email)
            created += 1
        except IntegrityError:
            db.rollback()
            skipped += 1
        except Exception as exc:
            db.rollback()
            errors.append(f"{email}: {exc}")

    return BulkSummary(created=created, skipped=skipped, errors=errors)


@router.get(
    "/churn-events",
    response_model=ChurnEventListResponse,
    dependencies=[Depends(require_feature("advanced_churn_prediction"))],
)
def list_churn_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active: Optional[bool] = Query(None, description="true = recovered_at IS NULL"),
    reason_code: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-01-01"),
    to_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-12-31"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ChurnEventListResponse:
    """List churn events with pagination and optional filters."""
    query = db.query(CustomerChurnEvent).filter(
        CustomerChurnEvent.organization_id == current_org.id
    )

    if active is True:
        query = query.filter(CustomerChurnEvent.recovered_at.is_(None))
    elif active is False:
        query = query.filter(CustomerChurnEvent.recovered_at.isnot(None))

    if reason_code:
        query = query.filter(CustomerChurnEvent.reason_code == reason_code)

    if from_date:
        try:
            dt_from = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.filter(CustomerChurnEvent.churned_at >= dt_from)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid from_date: {from_date!r}")

    if to_date:
        try:
            dt_to = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(CustomerChurnEvent.churned_at < dt_to)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid to_date: {to_date!r}")

    total = query.count()
    offset = (page - 1) * page_size
    records = (
        query.order_by(CustomerChurnEvent.churned_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return ChurnEventListResponse(
        items=[ChurnEventResponse.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{email}/churn-event",
    response_model=ChurnEventResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("advanced_churn_prediction"))],
)
def create_churn_event(
    email: str,
    body: ChurnEventCreate,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChurnEventResponse:
    """Mark a customer as churned and invalidate their probability cache."""
    # Normalize email from path (URL-decoded by FastAPI)
    normalized_email = email.strip().lower()

    event = CustomerChurnEvent(
        organization_id=current_org.id,
        customer_email=normalized_email,
        churned_at=body.churned_at,
        reason_code=body.reason_code,
        reason_text=body.reason_text,
        marked_by_user_id=current_user.id,
        source="manual",
    )

    try:
        db.add(event)
        db.commit()
        db.refresh(event)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A churn event for this customer at this timestamp already exists.",
        )

    _invalidate_probability(db, current_org.id, normalized_email)

    return ChurnEventResponse.model_validate(event)


@router.post(
    "/{email}/recover",
    response_model=ChurnEventResponse,
    dependencies=[Depends(require_feature("advanced_churn_prediction"))],
)
def recover_customer(
    email: str,
    body: RecoverRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ChurnEventResponse:
    """Set recovered_at on the latest active churn event and clear winback flag."""
    normalized_email = email.strip().lower()

    event = _get_active_churn_event(db, current_org.id, normalized_email)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active churn event found for customer '{normalized_email}'.",
        )

    event.recovered_at = body.recovered_at or datetime.utcnow()
    db.commit()

    # Clear potential winback flag on health record if present
    health = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == current_org.id,
            CustomerHealth.customer_email == normalized_email,
        )
        .first()
    )
    if health:
        health.has_potential_winback = False
        db.commit()

    db.refresh(event)
    return ChurnEventResponse.model_validate(event)


@router.delete(
    "/{email}/churn-event/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_feature("advanced_churn_prediction"))],
)
def delete_churn_event(
    email: str,
    event_id: int,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft-undo a churn event. Allowed within 24h for the author; system admin always."""
    event = (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.id == event_id,
            CustomerChurnEvent.organization_id == current_org.id,
        )
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Churn event {event_id} not found.",
        )

    is_system_admin = getattr(current_user, "is_system_admin", False)
    is_author = event.marked_by_user_id == current_user.id
    within_24h = (datetime.utcnow() - event.created_at) <= timedelta(hours=24)

    if is_system_admin:
        # System admin can delete anytime
        pass
    elif is_author and within_24h:
        # Original author within 24h
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete a churn event you created within 24 hours, or be a system admin.",
        )

    db.delete(event)
    db.commit()
    return None
