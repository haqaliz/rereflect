"""
Churn Playbook API (M4.1 Phase 5.1).

All endpoints gated by require_feature("churn_playbooks") (Business+).

Endpoints:
  GET    /api/v1/playbooks                          List org playbooks + system templates
  POST   /api/v1/playbooks                          Create / clone from template
  GET    /api/v1/playbooks/executions               Execution history (paginated, filtered)
  GET    /api/v1/playbooks/{id}                     Detail + recent executions
  PUT    /api/v1/playbooks/{id}                     Update org playbook
  DELETE /api/v1/playbooks/{id}                     Delete org playbook
  POST   /api/v1/playbooks/{id}/run                 Run on single customer
  POST   /api/v1/playbooks/{id}/run-batch           Run on matching customers
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_feature,
)
from src.database.session import get_db
from src.models.churn_playbook import ChurnPlaybook, ChurnPlaybookExecution
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.schemas.churn_playbook import (
    PlaybookCreate,
    PlaybookExecutionResponse,
    PlaybookResponse,
    PlaybookRunRequest,
    PlaybookUpdate,
)
from src.services.segment_service import SEGMENT_SLUGS

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/playbooks",
    tags=["playbooks"],
    dependencies=[Depends(require_feature("churn_playbooks"))],
)

# ---------------------------------------------------------------------------
# Plan limits
# ---------------------------------------------------------------------------

_PLAYBOOK_LIMITS: Dict[str, Optional[int]] = {
    "free": 0,
    "pro": 0,
    "business": 20,
    "enterprise": None,  # unlimited
}

_BATCH_RUN_DAILY_LIMITS: Dict[str, Optional[int]] = {
    "free": 0,
    "pro": 0,
    "business": 50,
    "enterprise": None,  # unlimited
}

# Queue-safety cap for run-batch (matches CRM-writeback backfill cap). A
# resolved cohort larger than this is rejected outright (422) rather than
# silently truncated — see playbook-cohort-run spec.
RUN_BATCH_MAX_CUSTOMERS = 500


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_playbook_limit(plan: str) -> Optional[int]:
    """Max active playbooks per org. None = unlimited."""
    return _PLAYBOOK_LIMITS.get(plan, 0)


def _get_batch_run_daily_limit(plan: str) -> Optional[int]:
    """Max run-batch executions per day per org. None = unlimited."""
    return _BATCH_RUN_DAILY_LIMITS.get(plan, 0)


def _count_active_playbooks(org_id: int, db: Session) -> int:
    """Count active (non-template) playbooks for an org."""
    return (
        db.query(ChurnPlaybook)
        .filter(
            ChurnPlaybook.organization_id == org_id,
            ChurnPlaybook.is_active.is_(True),
        )
        .count()
    )


def _count_executions_today(org_id: int, db: Session) -> int:
    """Count playbook executions created today (UTC) for an org."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(ChurnPlaybookExecution)
        .filter(
            ChurnPlaybookExecution.organization_id == org_id,
            ChurnPlaybookExecution.created_at >= today_start,
        )
        .count()
    )


def _get_org_playbook_or_404(pb_id: int, org_id: int, db: Session) -> ChurnPlaybook:
    """Return an org-owned (non-template) playbook or raise 404."""
    pb = db.query(ChurnPlaybook).filter(ChurnPlaybook.id == pb_id).first()
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if pb.is_template:
        raise HTTPException(
            status_code=403, detail="System templates are immutable. Clone to edit."
        )
    if pb.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return pb


def _apply_run_batch_filters(
    query,
    org: Organization,
    playbook: ChurnPlaybook,
    filters: Optional[Dict[str, Any]],
):
    """Apply customer health filters for run-batch; always scoped to org.

    Two selection modes:

    - **Cohort mode** (``emails`` and/or ``segment`` present in ``filters``):
      resolves customers via the shared ``_apply_customer_filters`` (segment)
      / email-list matching used by ``resolve_cohort`` (bulk-actions-api), so
      cohort selection never drifts from ``GET /api/v1/customers/``. Unknown
      emails are simply not matched (skipped). When probability fields are
      *also* given, they are ANDed on top of the cohort (segment/emails AND
      probability band). ``time_to_churn_bucket`` is always ANDed if given.
    - **Probability-only mode** (no ``emails``/``segment``): unchanged
      behavior — probability band defaults to the playbook's own
      ``probability_min``/``probability_max``, optionally overridden by
      explicit filter values.
    """
    query = query.filter(CustomerHealth.organization_id == org.id)

    cohort_emails = filters.get("emails") if filters else None
    cohort_segment = filters.get("segment") if filters else None
    has_cohort = cohort_emails is not None or cohort_segment is not None

    if has_cohort:
        if cohort_emails is not None:
            normalized = [e.strip().lower() for e in cohort_emails]
            unique_emails = list(dict.fromkeys(normalized))
            # Empty list (or all-unknown, handled by the `.in_()` itself)
            # simply resolves to zero rows — not an error.
            query = query.filter(CustomerHealth.customer_email.in_(unique_emails))
        else:
            # Deferred import: avoids a circular import between
            # src.api.routes.customers <-> src.api.routes.playbooks.
            from src.api.routes.customers import _apply_customer_filters

            query = _apply_customer_filters(query, org, segment=cohort_segment)

        # AND with the probability band ONLY when probability fields are
        # explicitly given alongside the cohort — segment/emails alone do
        # not implicitly constrain by probability.
        if filters and (
            filters.get("probability_min") is not None
            or filters.get("probability_max") is not None
        ):
            prob_min = (
                float(filters["probability_min"])
                if filters.get("probability_min") is not None
                else 0.0
            )
            prob_max = (
                float(filters["probability_max"])
                if filters.get("probability_max") is not None
                else 1.0
            )
            query = query.filter(
                CustomerHealth.churn_probability >= prob_min,
                CustomerHealth.churn_probability <= prob_max,
            )
    else:
        prob_min = float(playbook.probability_min)
        prob_max = float(playbook.probability_max)

        # Override with explicit filter if provided
        if filters:
            if filters.get("probability_min") is not None:
                prob_min = float(filters["probability_min"])
            if filters.get("probability_max") is not None:
                prob_max = float(filters["probability_max"])

        query = query.filter(
            CustomerHealth.churn_probability >= prob_min,
            CustomerHealth.churn_probability <= prob_max,
        )

    if filters and filters.get("time_to_churn_bucket"):
        query = query.filter(
            CustomerHealth.time_to_churn_bucket == filters["time_to_churn_bucket"]
        )

    return query


def _dispatch_celery(execution_id: int) -> None:
    """Dispatch a Celery task without importing any worker module."""
    from src.background.celery_client import get_celery_app

    app = get_celery_app()
    app.send_task("tasks.churn_playbooks.run_playbook", args=[execution_id])


# ---------------------------------------------------------------------------
# Schemas (local — not in shared schemas file)
# ---------------------------------------------------------------------------


class PlaybookDetailResponse(PlaybookResponse):
    """Extended response including recent executions."""

    recent_executions: List[PlaybookExecutionResponse] = []


class RunBatchFilters(BaseModel):
    """Optional filters for run-batch.

    Two independent selection axes that can be combined:

    - Probability band: ``probability_min``/``probability_max`` (defaults to
      the playbook's own band when omitted), plus ``time_to_churn_bucket``.
    - Cohort: ``emails`` (explicit list) OR ``segment`` (validated against
      ``SEGMENT_SLUGS``) — resolved via the same shared logic as
      ``GET /api/v1/customers/`` / bulk actions. When a cohort is combined
      with probability fields, they are ANDed (customer must match both).

    A request with none of ``emails``/``segment`` set behaves exactly as
    before this extension (back-compat).
    """

    probability_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    probability_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    time_to_churn_bucket: Optional[str] = None
    emails: Optional[List[str]] = None
    segment: Optional[str] = None

    @field_validator("segment")
    @classmethod
    def validate_segment(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SEGMENT_SLUGS:
            raise ValueError(
                f"Invalid segment '{v}'. Must be one of: {', '.join(SEGMENT_SLUGS)}"
            )
        return v


class RunBatchRequest(BaseModel):
    """Body for run-batch endpoint."""

    filters: Optional[RunBatchFilters] = None


class RunBatchResponse(BaseModel):
    """Response from run-batch.

    ``matched`` is the size of the resolved cohort/probability selection,
    computed up front (before the queue-safety cap and daily-limit checks).
    For a ``count_only=true`` dry-run, ``matched`` is populated and
    ``queued``/``execution_ids`` are empty — nothing is queued.
    """

    queued: int
    execution_ids: List[int]
    matched: int = 0


class ExecutionListResponse(BaseModel):
    """Paginated execution list."""

    items: List[PlaybookExecutionResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[PlaybookResponse])
def list_playbooks(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> List[PlaybookResponse]:
    """List org's active playbooks AND all system templates."""
    rows = (
        db.query(ChurnPlaybook)
        .filter(
            (ChurnPlaybook.organization_id == current_org.id)
            | (ChurnPlaybook.is_template.is_(True))
        )
        .all()
    )
    return rows


@router.post("", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
def create_playbook(
    body: PlaybookCreate,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlaybookResponse:
    """Create a new org playbook, optionally cloning from a system template."""
    plan = current_org.plan or "free"
    limit = _get_playbook_limit(plan)
    if limit is not None:
        active_count = _count_active_playbooks(current_org.id, db)
        if active_count >= limit:
            raise HTTPException(
                status_code=409,
                detail=f"Playbook limit reached. Plan '{plan}' allows {limit} active playbooks.",
            )

    action_sequence = body.action_sequence

    # If cloning from template, validate template exists and copy its actions
    if body.source_template_id is not None:
        tmpl = (
            db.query(ChurnPlaybook)
            .filter(
                ChurnPlaybook.id == body.source_template_id,
                ChurnPlaybook.is_template.is_(True),
            )
            .first()
        )
        if tmpl is None:
            raise HTTPException(status_code=404, detail="Source template not found")
        # Use provided action_sequence (which should mirror the template's)
        # but record the lineage
        action_sequence = body.action_sequence

    pb = ChurnPlaybook(
        organization_id=current_org.id,
        name=body.name,
        description=body.description,
        probability_min=body.probability_min,
        probability_max=body.probability_max,
        action_sequence=action_sequence,
        source_template_id=body.source_template_id,
        is_template=False,
        is_active=True,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


@router.get("/executions", response_model=ExecutionListResponse)
def list_executions(
    playbook_id: Optional[int] = Query(None),
    customer_email: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> ExecutionListResponse:
    """List execution history for this org's playbooks."""
    query = db.query(ChurnPlaybookExecution).filter(
        ChurnPlaybookExecution.organization_id == current_org.id
    )
    if playbook_id is not None:
        query = query.filter(ChurnPlaybookExecution.playbook_id == playbook_id)
    if customer_email is not None:
        query = query.filter(
            ChurnPlaybookExecution.customer_email == customer_email.lower()
        )
    if status is not None:
        query = query.filter(ChurnPlaybookExecution.status == status)

    total = query.count()
    items = (
        query.order_by(ChurnPlaybookExecution.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ExecutionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{playbook_id}", response_model=PlaybookDetailResponse)
def get_playbook(
    playbook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> PlaybookDetailResponse:
    """Return playbook detail including last 20 executions."""
    pb = (
        db.query(ChurnPlaybook)
        .filter(
            ChurnPlaybook.id == playbook_id,
            (ChurnPlaybook.organization_id == current_org.id)
            | (ChurnPlaybook.is_template.is_(True)),
        )
        .first()
    )
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")

    recent = (
        db.query(ChurnPlaybookExecution)
        .filter(ChurnPlaybookExecution.playbook_id == playbook_id)
        .order_by(ChurnPlaybookExecution.created_at.desc())
        .limit(20)
        .all()
    )

    # Build response manually to attach recent_executions
    pb_dict = {
        "id": pb.id,
        "organization_id": pb.organization_id,
        "name": pb.name,
        "description": pb.description,
        "probability_min": float(pb.probability_min),
        "probability_max": float(pb.probability_max),
        "action_sequence": pb.action_sequence,
        "is_template": pb.is_template,
        "is_active": pb.is_active,
        "source_template_id": pb.source_template_id,
        "created_at": pb.created_at,
        "updated_at": pb.updated_at,
        "recent_executions": recent,
    }
    return PlaybookDetailResponse(**pb_dict)


@router.put("/{playbook_id}", response_model=PlaybookResponse)
def update_playbook(
    playbook_id: int,
    body: PlaybookUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> PlaybookResponse:
    """Update a mutable org playbook."""
    pb = _get_org_playbook_or_404(playbook_id, current_org.id, db)

    if body.name is not None:
        pb.name = body.name
    if body.description is not None:
        pb.description = body.description
    if body.probability_min is not None:
        pb.probability_min = body.probability_min
    if body.probability_max is not None:
        pb.probability_max = body.probability_max
    if body.action_sequence is not None:
        pb.action_sequence = body.action_sequence
    if body.is_active is not None:
        pb.is_active = body.is_active

    pb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pb)
    return pb


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_playbook(
    playbook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete an org playbook."""
    pb = _get_org_playbook_or_404(playbook_id, current_org.id, db)
    db.delete(pb)
    db.commit()


@router.post(
    "/{playbook_id}/run",
    response_model=PlaybookExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_playbook(
    playbook_id: int,
    body: PlaybookRunRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlaybookExecutionResponse:
    """Run a playbook on a single customer."""
    pb = (
        db.query(ChurnPlaybook)
        .filter(
            ChurnPlaybook.id == playbook_id,
            (ChurnPlaybook.organization_id == current_org.id)
            | (ChurnPlaybook.is_template.is_(True)),
        )
        .first()
    )
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")

    execution = ChurnPlaybookExecution(
        playbook_id=pb.id,
        organization_id=current_org.id,
        customer_email=body.customer_email,
        triggered_by="manual",
        triggered_by_user_id=current_user.id,
        status="queued",
        action_log=[],
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    try:
        _dispatch_celery(execution.id)
    except Exception as exc:
        logger.warning(f"Celery dispatch failed for execution {execution.id}: {exc}")

    return execution


@router.post("/{playbook_id}/run-batch", response_model=RunBatchResponse)
def run_playbook_batch(
    playbook_id: int,
    body: RunBatchRequest,
    count_only: bool = Query(
        False,
        description=(
            "If true, resolve and return the matched-customer count only — "
            "no executions are queued. Use for the UI affected-count preview "
            "before confirming a run."
        ),
    ),
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RunBatchResponse:
    """Run a playbook on all customers matching the filters.

    Filters (``body.filters``, all optional) combine two axes:

    - Probability band (``probability_min``/``probability_max``,
      ``time_to_churn_bucket``) — defaults to the playbook's own band when
      omitted. Unchanged from the pre-cohort behavior.
    - Cohort (``emails`` OR ``segment``) — resolved via the same shared
      filter logic as ``GET /api/v1/customers/``, org-scoped. When combined
      with probability fields, both must match (AND). Invalid ``segment``
      values are rejected with 422 at the schema level.

    Query params:

    - ``count_only=true``: resolve and return ``{matched}`` without queuing
      anything. Does not apply the cap or daily-limit checks — it is a pure
      preview so the UI can show "N customers will be affected" before the
      operator confirms.

    Safety:

    - The resolved cohort size (``matched``) is computed up front. If it
      exceeds ``RUN_BATCH_MAX_CUSTOMERS`` (500), the request is rejected
      with 422 (``"cohort of N exceeds batch cap of 500; narrow the
      filter"``) and **nothing is queued** — atomic, no partial batches.
    - The daily execution limit is checked against ``today_count +
      matched`` (the full resolved cohort size), not incrementally inside
      the queuing loop, so a large cohort cannot partially queue before
      hitting the plan's daily allowance.
    """
    pb = (
        db.query(ChurnPlaybook)
        .filter(
            ChurnPlaybook.id == playbook_id,
            (ChurnPlaybook.organization_id == current_org.id)
            | (ChurnPlaybook.is_template.is_(True)),
        )
        .first()
    )
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")

    filters_dict = body.filters.model_dump() if body.filters else None

    customer_query = db.query(CustomerHealth)
    customer_query = _apply_run_batch_filters(
        customer_query, current_org, pb, filters_dict
    )
    matched_count = customer_query.count()

    if count_only:
        return RunBatchResponse(queued=0, execution_ids=[], matched=matched_count)

    if matched_count > RUN_BATCH_MAX_CUSTOMERS:
        logger.info(
            f"run-batch cap exceeded: org={current_org.id} playbook={pb.id} "
            f"matched={matched_count} cap={RUN_BATCH_MAX_CUSTOMERS}"
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"cohort of {matched_count} exceeds batch cap of "
                f"{RUN_BATCH_MAX_CUSTOMERS}; narrow the filter"
            ),
        )

    plan = current_org.plan or "free"
    daily_limit = _get_batch_run_daily_limit(plan)
    if daily_limit is not None:
        today_count = _count_executions_today(current_org.id, db)
        if today_count + matched_count > daily_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Daily batch run limit reached. Plan '{plan}' allows "
                    f"{daily_limit} executions per day."
                ),
            )

    customers = customer_query.all()

    execution_ids: List[int] = []
    for ch in customers:
        ex = ChurnPlaybookExecution(
            playbook_id=pb.id,
            organization_id=current_org.id,
            customer_email=ch.customer_email,
            triggered_by="manual",
            triggered_by_user_id=current_user.id,
            status="queued",
            action_log=[],
        )
        db.add(ex)
        db.flush()  # get ID without full commit
        execution_ids.append(ex.id)

    db.commit()

    for ex_id in execution_ids:
        try:
            _dispatch_celery(ex_id)
        except Exception as exc:
            logger.warning(f"Celery dispatch failed for execution {ex_id}: {exc}")

    return RunBatchResponse(
        queued=len(execution_ids), execution_ids=execution_ids, matched=matched_count
    )
