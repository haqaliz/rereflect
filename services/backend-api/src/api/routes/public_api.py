"""
Public REST API — /api/public/v1 (Feature C, PRD §6).

All endpoints are authenticated via API-key (``rrf_...``) resolved by
``verify_api_key``.  Every query is hard-scoped to the organization that owns
the key — no cross-tenant data access is possible.

Scopes
------
  read   — GET endpoints (feedback, customers, analytics, webhooks)
  ingest — POST /feedback (create + enqueue analysis)
  write  — PATCH endpoints for mutating existing feedback

Prefix: /api/public/v1
Tag:    public
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from src.api.public.auth import ApiKeyAuth, require_scope, verify_api_key
from src.background import queue_analyze_feedback
from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.webhook_endpoint import WebhookEndpoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/v1", tags=["public"])


# ─── Shared schemas ───────────────────────────────────────────────────────────


class PublicFeedbackItem(BaseModel):
    """Feedback item exposed on the public surface."""

    id: int
    organization_id: int
    text: str
    source: Optional[str] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    is_urgent: bool
    pain_point_category: Optional[str] = None
    feature_request_category: Optional[str] = None
    churn_risk_score: Optional[int] = None
    customer_email: Optional[str] = None
    workflow_status: str = "new"
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicFeedbackListResponse(BaseModel):
    items: List[PublicFeedbackItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class PublicFeedbackCreate(BaseModel):
    text: str = Field(..., min_length=1)
    source: Optional[str] = Field(default="api")
    customer_email: Optional[str] = None


class PublicAnalyticsSummary(BaseModel):
    total_feedback: int
    positive_count: int
    neutral_count: int
    negative_count: int
    urgent_count: int
    avg_sentiment_score: Optional[float] = None


class PublicWebhookItem(BaseModel):
    id: int
    name: str
    url: str
    events: List[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicCustomer(BaseModel):
    """Customer summary exposed on the public surface."""

    customer_email: str
    customer_name: Optional[str] = None
    health_score: Optional[float] = None
    risk_level: Optional[str] = None
    churn_probability: Optional[float] = None
    time_to_churn_bucket: Optional[str] = None
    feedback_count: int = 0
    last_feedback_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PublicCustomerListResponse(BaseModel):
    items: List[PublicCustomer]
    total: int
    page: int
    page_size: int
    total_pages: int


class PublicCustomerHealth(BaseModel):
    """Full customer-health detail (public surface)."""

    customer_email: str
    customer_name: Optional[str] = None
    health_score: Optional[float] = None
    risk_level: Optional[str] = None
    churn_risk_component: Optional[float] = None
    sentiment_component: Optional[float] = None
    resolution_component: Optional[float] = None
    frequency_component: Optional[float] = None
    usage_component: Optional[int] = None           # additive — Phase 4
    churn_probability: Optional[float] = None
    churn_probability_low: Optional[float] = None
    churn_probability_high: Optional[float] = None
    time_to_churn_bucket: Optional[str] = None
    confidence_level: Optional[str] = None
    feedback_count: int = 0
    last_feedback_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PublicCustomerProfile360(BaseModel):
    """Full Customer 360 profile exposed on the public surface.

    Mirrors the v1 ``CustomerProfileResponse`` shape (via the shared serializer)
    and adds churn_probability / time_to_churn_bucket which the v1 profile schema
    doesn't currently expose.

    TODO: redact LLM free-text for the public surface?
    Default: NO (operator's own self-hosted data).  Revisit if a consumer objects.
    """

    customer_email: str
    customer_name: Optional[str] = None
    health_score: int
    risk_level: str
    confidence_level: str
    feedback_count: int
    last_feedback_at: Optional[datetime] = None
    churn_risk_component: int
    sentiment_component: int
    resolution_component: int
    frequency_component: int
    usage_component: Optional[int] = None
    churn_probability: Optional[float] = None
    churn_probability_low: Optional[float] = None
    churn_probability_high: Optional[float] = None
    time_to_churn_bucket: Optional[str] = None
    llm_analysis_summary: Optional[str] = None
    llm_recommended_actions: Optional[List[str]] = None
    llm_risk_drivers: Optional[List[str]] = None
    llm_urgency: Optional[str] = None
    llm_analysis_type: Optional[str] = None
    llm_analyzed_at: Optional[datetime] = None
    llm_analysis: Optional[str] = None
    is_archived: bool
    created_at: Optional[datetime] = None
    # CRM enrichment fields (HubSpot / Salesforce)
    crm_company_name: Optional[str] = None
    crm_lifecycle_stage: Optional[str] = None
    crm_arr: Optional[float] = None
    crm_renewal_date: Optional[datetime] = None
    crm_deal_name: Optional[str] = None
    crm_deal_stage: Optional[str] = None
    crm_deal_amount: Optional[float] = None
    crm_provider: Optional[str] = None


# ─── Feedback read endpoints ──────────────────────────────────────────────────


@router.get(
    "/feedback",
    response_model=PublicFeedbackListResponse,
    dependencies=[Depends(require_scope("read"))],
    summary="List feedback (public API)",
    description="Paginated, filterable list of feedback items scoped to the key's organization.",
)
def public_list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sentiment: Optional[str] = Query(None),
    is_urgent: Optional[bool] = Query(None),
    customer_email: Optional[str] = Query(None),
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicFeedbackListResponse:
    q = db.query(FeedbackItem).filter(FeedbackItem.organization_id == auth.organization_id)

    if sentiment is not None:
        q = q.filter(FeedbackItem.sentiment_label == sentiment)
    if is_urgent is not None:
        q = q.filter(FeedbackItem.is_urgent == is_urgent)
    if customer_email is not None:
        q = q.filter(FeedbackItem.customer_email == customer_email)

    total = q.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = q.order_by(FeedbackItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return PublicFeedbackListResponse(
        items=[PublicFeedbackItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/feedback/{feedback_id}",
    response_model=PublicFeedbackItem,
    dependencies=[Depends(require_scope("read"))],
    summary="Get a single feedback item (public API)",
)
def public_get_feedback(
    feedback_id: int,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicFeedbackItem:
    row = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == feedback_id,
            FeedbackItem.organization_id == auth.organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    return PublicFeedbackItem.model_validate(row)


# ─── Feedback ingest ──────────────────────────────────────────────────────────


@router.post(
    "/feedback",
    response_model=PublicFeedbackItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("ingest"))],
    summary="Ingest feedback (public API)",
    description=(
        "Create a new feedback item and enqueue it for AI analysis — "
        "mirrors the internal ``POST /api/v1/feedback`` path."
    ),
)
def public_ingest_feedback(
    data: PublicFeedbackCreate,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicFeedbackItem:
    row = FeedbackItem(
        organization_id=auth.organization_id,
        text=data.text,
        source=data.source or "api",
        customer_email=data.customer_email,
        is_urgent=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Enqueue analysis exactly like the internal feedback route does
    queue_analyze_feedback(row.id)

    return PublicFeedbackItem.model_validate(row)


# ─── Feedback write (PATCH) ───────────────────────────────────────────────────


class PublicCorrectionInput(BaseModel):
    """A single human-in-the-loop correction on an AI-derived field."""

    field: Literal["pain_point", "feature_request", "sentiment"]
    corrected_value: str = Field(..., min_length=1)


class PublicFeedbackUpdate(BaseModel):
    """Mutable fields on a feedback item exposed to the public write API.

    ``workflow_status`` moves the item through the workflow (timeline event +
    webhook).  ``correction`` records a human correction of an AI-derived field
    (record-only — the stored category/sentiment column is NOT mutated).
    """

    workflow_status: Optional[
        Literal["new", "in_review", "resolved", "closed"]
    ] = None
    resolution_note: Optional[str] = None
    correction: Optional[PublicCorrectionInput] = None


def _resolve_correction(fb: FeedbackItem, field: str) -> tuple[str, Optional[str]]:
    """Map a public correction ``field`` → (correction_type, current stored value)."""
    if field == "pain_point":
        return "category", fb.pain_point_category
    if field == "feature_request":
        return "category", fb.feature_request_category
    # field == "sentiment"
    return "sentiment", fb.sentiment_label


@router.patch(
    "/feedback/{feedback_id}",
    response_model=PublicFeedbackItem,
    dependencies=[Depends(require_scope("write"))],
    summary="Update a feedback item (public API)",
    description=(
        "Update a feedback item's workflow status and/or record a correction of "
        "an AI-derived field.  Requires the ``write`` scope.  Corrections are "
        "record-only — they capture a training signal without mutating the stored "
        "category/sentiment."
    ),
)
async def public_update_feedback(
    feedback_id: int,
    data: PublicFeedbackUpdate,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicFeedbackItem:
    if data.workflow_status is None and data.correction is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    fb = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id == feedback_id,
            FeedbackItem.organization_id == auth.organization_id,
        )
        .first()
    )
    if fb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    key_label = f"api-key:{auth.key_row.name}"

    # ── Workflow status change ────────────────────────────────────────────────
    if data.workflow_status is not None:
        from src.services.workflow_service import (
            apply_status_change,
            dispatch_status_webhooks,
        )

        changed = apply_status_change(
            db,
            [fb],
            data.workflow_status,
            organization_id=auth.organization_id,
            actor_id=None,
            actor_label=key_label,
            resolution_note=data.resolution_note,
        )
        db.commit()

        if changed:
            # Best-effort side effects — a failing webhook must not fail the PATCH.
            try:
                from src.services.cache_service import cache_invalidate

                cache_invalidate(f"dashboard:{auth.organization_id}:*")
                cache_invalidate(f"analytics:{auth.organization_id}:*")
            except Exception:
                logger.warning("cache_invalidate failed on public PATCH", exc_info=True)

            try:
                dispatch_status_webhooks(
                    db,
                    auth.organization_id,
                    changed,
                    data.workflow_status,
                    changed_by_label=key_label,
                )
            except Exception:
                logger.warning("webhook dispatch failed on public PATCH", exc_info=True)

            try:
                from src.services.event_emitter import emit_event

                await emit_event(
                    org_id=auth.organization_id,
                    event_type="workflow:status_changed",
                    data={"feedback_ids": [fb.id], "new_status": data.workflow_status},
                )
            except Exception:
                logger.warning("emit_event failed on public PATCH", exc_info=True)

    # ── Correction (record-only) ──────────────────────────────────────────────
    if data.correction is not None:
        from src.services.ai_correction_service import create_ai_correction

        correction_type, original_value = _resolve_correction(fb, data.correction.field)
        create_ai_correction(
            db,
            organization_id=auth.organization_id,
            user_id=None,
            correction_type=correction_type,
            entity_type="feedback_item",
            entity_id=fb.id,
            signal="correction",
            original_value=original_value,
            corrected_value=data.correction.corrected_value,
            feedback_text=fb.text,
        )

    db.refresh(fb)
    return PublicFeedbackItem.model_validate(fb)


# ─── Analytics summary ────────────────────────────────────────────────────────


@router.get(
    "/analytics/summary",
    response_model=PublicAnalyticsSummary,
    dependencies=[Depends(require_scope("read"))],
    summary="Analytics summary (public API)",
    description="Aggregate counts and sentiment distribution for the key's organization.",
)
def public_analytics_summary(
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicAnalyticsSummary:
    q = db.query(FeedbackItem).filter(FeedbackItem.organization_id == auth.organization_id)

    total = q.count()
    stats = q.with_entities(
        func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("pos"),
        func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neu"),
        func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("neg"),
        func.sum(case((FeedbackItem.is_urgent == True, 1), else_=0)).label("urg"),
        func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
    ).first()

    return PublicAnalyticsSummary(
        total_feedback=total,
        positive_count=int(stats.pos or 0),
        neutral_count=int(stats.neu or 0),
        negative_count=int(stats.neg or 0),
        urgent_count=int(stats.urg or 0),
        avg_sentiment_score=round(float(stats.avg_sent), 3) if stats.avg_sent is not None else None,
    )


# ─── Webhook management (read scope) ─────────────────────────────────────────


@router.get(
    "/webhooks",
    response_model=List[PublicWebhookItem],
    dependencies=[Depends(require_scope("read"))],
    summary="List webhook endpoints (public API)",
)
def public_list_webhooks(
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> List[PublicWebhookItem]:
    rows = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.organization_id == auth.organization_id)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )
    return [PublicWebhookItem.model_validate(r) for r in rows]


# ─── Customers & churn (read scope) ──────────────────────────────────────────


@router.get(
    "/customers",
    response_model=PublicCustomerListResponse,
    dependencies=[Depends(require_scope("read"))],
    summary="List customers (public API)",
    description="Paginated list of customers with health scores, scoped to the key's organization.",
)
def public_list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = Query(None),
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicCustomerListResponse:
    q = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == auth.organization_id,
        CustomerHealth.is_archived == False,  # noqa: E712
    )
    if risk_level is not None:
        q = q.filter(CustomerHealth.risk_level == risk_level)

    total = q.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = (
        q.order_by(CustomerHealth.health_score.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PublicCustomerListResponse(
        items=[PublicCustomer.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/customers/{customer_email}/health",
    response_model=PublicCustomerHealth,
    dependencies=[Depends(require_scope("read"))],
    summary="Get a customer's health (public API)",
    description=(
        "Health-score summary for a single customer.\n\n"
        "Includes the 4 core health components (churn_risk, sentiment, resolution, "
        "frequency) **plus** ``usage_component`` (null when product-usage data has "
        "not been collected for this customer), calibrated churn probability with "
        "90 % confidence interval, and ``time_to_churn_bucket``."
    ),
)
def public_customer_health(
    customer_email: str,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicCustomerHealth:
    row = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == auth.organization_id,
            CustomerHealth.customer_email == customer_email,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer health not found")
    return PublicCustomerHealth.model_validate(row)


# ─── Customer 360 profile (public) ───────────────────────────────────────────


@router.get(
    "/customers/{customer_email}",
    response_model=PublicCustomerProfile360,
    dependencies=[Depends(require_scope("read"))],
    summary="Get Customer 360 profile (public API)",
    description=(
        "Full Customer 360 profile for a customer by email — health score, "
        "5 health components (including usage), churn probability, and LLM "
        "analysis fields.  Mirrors the v1 profile shape via the shared serializer."
    ),
)
def public_customer_profile(
    customer_email: str,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicCustomerProfile360:
    row = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == auth.organization_id,
            CustomerHealth.customer_email == customer_email,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health record found for customer '{customer_email}'",
        )

    from src.services.customer_profile_serializer import serialize_customer_profile
    profile_data = serialize_customer_profile(row, db)
    return PublicCustomerProfile360(**profile_data)


# ─── Customer timeline (public) ───────────────────────────────────────────────


class PublicActivityEvent(BaseModel):
    """A single timeline event on the public surface.

    Field layout matches the v1 ``ActivityEvent`` to ensure wire-shape parity.
    """

    type: str
    description: str
    timestamp: datetime
    feedback_id: Optional[int] = None
    old_score: Optional[int] = None
    new_score: Optional[int] = None
    risk_level: Optional[str] = None
    reason_code: Optional[str] = None
    feature_name: Optional[str] = None
    source: Optional[str] = None
    gap_days: Optional[int] = None
    # CRM payload fields (additive — all Optional)
    company_name: Optional[str] = None
    renewal_date: Optional[datetime] = None
    deal_stage: Optional[str] = None
    arr: Optional[float] = None


class PublicTimelineResponse(BaseModel):
    events: List[PublicActivityEvent]
    next_cursor: Optional[str] = None


@router.get(
    "/customers/{customer_email}/timeline",
    response_model=PublicTimelineResponse,
    dependencies=[Depends(require_scope("read"))],
    summary="Get customer timeline (public API)",
    description=(
        "Cursor-paged, reverse-chronological activity timeline for a customer. "
        "Merges feedback, health-score changes, churn, and notable usage events. "
        "Backed by the same ``build_timeline`` service as the v1 timeline endpoint "
        "— identical cursor encoding, sort order, and pagination semantics.\n\n"
        "**Cursor pagination:** pass the ``next_cursor`` value from any response as "
        "the ``before`` query parameter to fetch the next page.  A ``null`` "
        "``next_cursor`` indicates the last page.  Malformed cursors return 422."
    ),
    response_description=(
        "``events``: list of timeline events, newest first.  "
        "``next_cursor``: opaque string for the next page; null on last page."
    ),
)
def public_customer_timeline(
    customer_email: str,
    before: Optional[str] = Query(
        None, description="Opaque cursor from a previous next_cursor value"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max events per page (1–100)"),
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicTimelineResponse:
    # Validate that the customer exists in this org (cross-org isolation).
    row = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == auth.organization_id,
            CustomerHealth.customer_email == customer_email,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health record found for customer '{customer_email}'",
        )

    # Validate / decode the cursor early so we return 422 on malformed input.
    if before is not None:
        from src.services.customer_timeline_service import _decode_cursor
        try:
            _decode_cursor(before)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid cursor: {exc}",
            )

    from src.services.customer_timeline_service import build_timeline
    from src.api.routes.customers import _timeline_event_to_activity

    timeline_events, next_cursor = build_timeline(
        db, auth.organization_id, customer_email, before=before, limit=limit
    )
    # Reuse the v1 helper to convert internal events → ActivityEvent shape.
    # We then re-serialize to PublicActivityEvent (same fields, no drift possible).
    activity_events = [_timeline_event_to_activity(e) for e in timeline_events]
    public_events = [PublicActivityEvent(**e.model_dump()) for e in activity_events]
    return PublicTimelineResponse(events=public_events, next_cursor=next_cursor)


@router.get(
    "/churn/customers",
    response_model=PublicCustomerListResponse,
    dependencies=[Depends(require_scope("read"))],
    summary="List at-risk customers (public API)",
    description="Customers at risk of churn (risk_level at_risk/critical), ordered by churn probability.",
)
def public_churn_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicCustomerListResponse:
    q = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == auth.organization_id,
        CustomerHealth.is_archived == False,  # noqa: E712
        CustomerHealth.risk_level.in_(["at_risk", "critical"]),
    )
    total = q.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = (
        q.order_by(CustomerHealth.churn_probability.desc(), CustomerHealth.health_score.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PublicCustomerListResponse(
        items=[PublicCustomer.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ─── Dedicated OpenAPI docs for the public surface ───────────────────────────


@router.get("/openapi.json", include_in_schema=False)
def public_openapi(request: Request) -> JSONResponse:
    """OpenAPI schema scoped to just the public (/api/public/v1) endpoints."""
    full = request.app.openapi()
    paths = {p: ops for p, ops in full.get("paths", {}).items() if p.startswith("/api/public/v1/")}
    spec = {
        "openapi": full.get("openapi", "3.1.0"),
        "info": {
            "title": "Rereflect Public API",
            "version": "1.0.0",
            "description": (
                "Public REST API for Rereflect. Authenticate every request with an API key:\n\n"
                "`Authorization: Bearer rrf_...`\n\n"
                "Keys carry scopes: **read** (GET endpoints), **ingest** (POST /feedback), "
                "and **write** (PATCH endpoints for mutating existing feedback). "
                "All data is scoped to the organization that owns the key."
            ),
        },
        "paths": paths,
        "components": full.get("components", {}),
    }
    return JSONResponse(spec)


@router.get("/docs", include_in_schema=False)
def public_docs() -> HTMLResponse:
    """Swagger UI for the public API surface."""
    return get_swagger_ui_html(
        openapi_url="/api/public/v1/openapi.json",
        title="Rereflect Public API — Docs",
    )
