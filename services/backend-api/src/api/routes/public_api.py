"""
Public REST API — /api/public/v1 (Feature C, PRD §6).

All endpoints are authenticated via API-key (``rrf_...``) resolved by
``verify_api_key``.  Every query is hard-scoped to the organization that owns
the key — no cross-tenant data access is possible.

Scopes
------
  read   — GET endpoints (feedback, customers, analytics, webhooks)
  ingest — POST /feedback (create + enqueue analysis)

Prefix: /api/public/v1
Tag:    public
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

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
    churn_probability: Optional[float] = None
    churn_probability_low: Optional[float] = None
    churn_probability_high: Optional[float] = None
    time_to_churn_bucket: Optional[str] = None
    confidence_level: Optional[str] = None
    feedback_count: int = 0
    last_feedback_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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
                "Keys carry scopes: **read** (GET endpoints) and **ingest** (POST /feedback). "
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
