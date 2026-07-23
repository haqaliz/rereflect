"""
Public REST API — /api/public/v1 (Feature C, PRD §6).

All endpoints are authenticated via API-key (``rrf_...``) resolved by
``verify_api_key``.  Every query is hard-scoped to the organization that owns
the key — no cross-tenant data access is possible.

Scopes
------
  read   — GET endpoints (feedback, customers, analytics, webhooks, categories)
  ingest — POST /feedback (create + enqueue analysis)
  write  — PATCH /feedback/{id} + DELETE /feedback/{id} (workflow status,
           corrections, tags, is_urgent); POST /feedback/bulk (uniform patch
           applied to up to 500 ids in one request); custom categories CRUD
           (POST/PATCH/DELETE /categories)

Prefix: /api/public/v1
Tag:    public
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from src.api.public.auth import ApiKeyAuth, require_scope, verify_api_key
from src.background import queue_analyze_feedback
from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.models.custom_category import CustomCategory
from src.models.feedback import FeedbackItem
from src.models.webhook_endpoint import WebhookEndpoint
from src.services import custom_category_service

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
    tags: Optional[List[str]] = None
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
    # Rule-based customer segment (customer-segments feature); nullable —
    # None = unsegmented / not yet computed.
    segment: Optional[str] = None
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
    ``tags`` replaces the stored tag list (``[]`` clears; omitted leaves
    unchanged).  ``is_urgent`` sets the urgency flag (omitted leaves unchanged).
    """

    model_config = {"extra": "forbid"}

    workflow_status: Optional[
        Literal["new", "in_review", "resolved", "closed"]
    ] = None
    resolution_note: Optional[str] = None
    correction: Optional[PublicCorrectionInput] = None
    tags: Optional[list[str]] = None
    is_urgent: Optional[bool] = None

    @field_validator("tags", mode="after")
    @classmethod
    def _validate_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in v:
            if not isinstance(item, str):
                raise ValueError("each tag must be a string")
            trimmed = item.strip()
            if not trimmed:
                raise ValueError("tags must not be empty (after trimming)")
            if len(trimmed) > 50:
                raise ValueError("each tag must be at most 50 characters")
            if trimmed not in seen:
                seen.add(trimmed)
                cleaned.append(trimmed)

        if len(cleaned) > 20:
            raise ValueError("at most 20 tags are allowed")

        return cleaned


class PublicFeedbackBulkUpdate(BaseModel):
    """Request body for ``POST /feedback/bulk`` — a uniform patch applied to
    every id in ``ids`` (deduped, order-preserving)."""

    model_config = {"extra": "forbid"}

    ids: list[int] = Field(..., min_length=1, max_length=500)
    patch: PublicFeedbackUpdate


class PublicFeedbackBulkResultItem(BaseModel):
    """Per-id result entry in the bulk response, ordered by deduped input order."""

    id: int
    status: Literal["updated", "noop", "skipped", "error"]
    reason: Optional[str] = None


class PublicFeedbackBulkResponse(BaseModel):
    matched: int
    updated: int
    skipped: int
    results: list[PublicFeedbackBulkResultItem]


def _resolve_correction(fb: FeedbackItem, field: str) -> tuple[str, Optional[str]]:
    """Map a public correction ``field`` → (correction_type, current stored value)."""
    if field == "pain_point":
        return "category", fb.pain_point_category
    if field == "feature_request":
        return "category", fb.feature_request_category
    # field == "sentiment"
    return "sentiment", fb.sentiment_label


def _apply_bulk_item_fields(
    db: Session,
    fb: FeedbackItem,
    patch: PublicFeedbackUpdate,
    organization_id: int,
) -> bool:
    """Apply ``correction`` / ``is_urgent`` / ``tags`` to a single feedback item
    for the bulk-write path. Mirrors the field-mutation block in the single
    PATCH handler, except every ``create_ai_correction`` call passes
    ``commit=False`` — the bulk caller does one final ``db.commit()`` for the
    whole batch.

    Returns ``True`` if this item's stored state actually changed (used to
    decide ``updated`` vs ``noop``); a correction insert always counts as a
    change (it's a record-only training signal, not a no-op).
    """
    fields_touched = False

    if patch.correction is not None:
        from src.services.ai_correction_service import create_ai_correction

        correction_type, original_value = _resolve_correction(fb, patch.correction.field)
        create_ai_correction(
            db,
            organization_id=organization_id,
            user_id=None,
            correction_type=correction_type,
            entity_type="feedback_item",
            entity_id=fb.id,
            signal="correction",
            original_value=original_value,
            corrected_value=patch.correction.corrected_value,
            feedback_text=fb.text,
            commit=False,
        )
        fields_touched = True

    if "is_urgent" in patch.model_fields_set:
        from src.services.ai_correction_service import create_ai_correction, urgency_label

        old_is_urgent = bool(fb.is_urgent)
        new_is_urgent = bool(patch.is_urgent)
        fb.is_urgent = new_is_urgent

        if new_is_urgent != old_is_urgent:
            fields_touched = True
            create_ai_correction(
                db,
                organization_id=organization_id,
                user_id=None,
                correction_type="urgency",
                entity_type="feedback_item",
                entity_id=fb.id,
                signal="correction",
                original_value=urgency_label(old_is_urgent),
                corrected_value=urgency_label(new_is_urgent),
                feedback_text=fb.text,
                commit=False,
            )

    if "tags" in patch.model_fields_set:
        new_tags = list(patch.tags or [])
        if new_tags != list(fb.tags or []):
            fields_touched = True
        fb.tags = new_tags  # rebind — JSON columns aren't dirty-tracked in-place

    return fields_touched


@router.post(
    "/feedback/bulk",
    response_model=PublicFeedbackBulkResponse,
    dependencies=[Depends(require_scope("write"))],
    summary="Bulk-update feedback items (public API)",
    description=(
        "Apply a uniform patch (``workflow_status`` / ``tags`` / ``is_urgent`` / "
        "``correction``) to up to 500 feedback ids in one request.  Requires the "
        "``write`` scope.  Ids not owned by this org (or non-existent) are "
        "``skipped`` — not errors.  ``workflow_status`` is applied via one "
        "batched status-change call; ``tags``/``is_urgent``/``correction`` are "
        "applied per item and are non-contagious — a per-item failure doesn't "
        "roll back the other items in the batch.  Pass ``?count_only=true`` to "
        "preview the match count without mutating anything."
    ),
)
async def public_bulk_update_feedback(
    data: PublicFeedbackBulkUpdate,
    count_only: bool = Query(
        False, description="Dry-run: return only the match count, mutate nothing."
    ),
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicFeedbackBulkResponse:
    patch = data.patch
    if not (patch.model_fields_set & {"workflow_status", "correction", "tags", "is_urgent"}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    # Dedupe ids, preserving first-seen order.
    unique_ids: list[int] = []
    seen_ids: set[int] = set()
    for i in data.ids:
        if i not in seen_ids:
            seen_ids.add(i)
            unique_ids.append(i)

    rows = (
        db.query(FeedbackItem)
        .filter(
            FeedbackItem.id.in_(unique_ids),
            FeedbackItem.organization_id == auth.organization_id,
        )
        .all()
    )
    by_id = {fb.id: fb for fb in rows}
    matched = len(by_id)

    if count_only:
        # Dry-run: short-circuit before any mutation (status change, per-item
        # fields, side effects) — just report how many of the deduped ids
        # matched this org.
        return PublicFeedbackBulkResponse(
            matched=matched,
            updated=0,
            skipped=len(unique_ids) - matched,
            results=[],
        )

    key_label = f"api-key:{auth.key_row.name}"

    error_reasons: dict[int, str] = {}
    field_changed_ids: set[int] = set()
    changed_pairs: list[tuple[FeedbackItem, str]] = []
    changed_ids: set[int] = set()

    # ── Batched status change — one call on the whole matched set ────────────
    if patch.workflow_status is not None:
        from src.services.workflow_service import apply_status_change

        changed_pairs = apply_status_change(
            db,
            list(by_id.values()),
            patch.workflow_status,
            organization_id=auth.organization_id,
            actor_id=None,
            actor_label=key_label,
            resolution_note=patch.resolution_note,
        )
        changed_ids = {fb.id for fb, _ in changed_pairs}
        # Flush now, in the OUTER transaction — before any per-item SAVEPOINT
        # is opened below. Without this, these status UPDATEs stay pending
        # (autoflush=False) until the first per-item begin_nested() block
        # flushes them *inside* that savepoint; a flush-time failure on that
        # first item would then ROLLBACK TO SAVEPOINT and silently discard
        # the whole batch's status writes even though we report them (and
        # dispatch webhooks for them) below as updated.
        db.flush()
        # Not committed yet — folded into the single db.commit() below,
        # together with the per-item field mutations.

    # ── Per-item fields (non-contagious via SAVEPOINT) ────────────────────────
    for fid in unique_ids:
        fb = by_id.get(fid)
        if fb is None:
            continue
        # Skip the SAVEPOINT machinery entirely for status-only batches — no
        # per-item field means nothing for _apply_bulk_item_fields to do, so
        # opening (and flushing/releasing) a SAVEPOINT per id here would be
        # pure overhead across a large batch.
        if not (patch.model_fields_set & {"correction", "is_urgent", "tags"}):
            continue
        try:
            with db.begin_nested():
                item_changed = _apply_bulk_item_fields(db, fb, patch, auth.organization_id)
                db.flush()
            if item_changed:
                field_changed_ids.add(fid)
        except Exception:
            logger.warning(
                "public bulk PATCH: per-item field update failed for feedback %s",
                fid,
                exc_info=True,
            )
            # NB: this item's per-item field write was rolled back by the
            # SAVEPOINT, but a batched status change for this same id (above)
            # may already be flushed/committed and have fired its webhook —
            # that part is retry-safe (same-status re-apply is a no-op).
            error_reasons[fid] = "internal_error"

    db.commit()

    # ── Best-effort side effects — done once for the whole batch ─────────────
    if changed_ids or field_changed_ids:
        try:
            from src.services.cache_service import cache_invalidate

            cache_invalidate(f"dashboard:{auth.organization_id}:*")
            cache_invalidate(f"analytics:{auth.organization_id}:*")
        except Exception:
            logger.warning("cache_invalidate failed on public bulk PATCH", exc_info=True)

    if changed_pairs:
        try:
            from src.services.workflow_service import dispatch_status_webhooks

            dispatch_status_webhooks(
                db,
                auth.organization_id,
                changed_pairs,
                patch.workflow_status,
                changed_by_label=key_label,
            )
        except Exception:
            logger.warning("webhook dispatch failed on public bulk PATCH", exc_info=True)

    if changed_ids:
        try:
            from src.services.event_emitter import emit_event

            await emit_event(
                org_id=auth.organization_id,
                event_type="workflow:status_changed",
                data={"feedback_ids": sorted(changed_ids), "new_status": patch.workflow_status},
            )
        except Exception:
            logger.warning("emit_event failed on public bulk PATCH", exc_info=True)

    # Items changed via tags/is_urgent/correction only (no workflow_status)
    # would otherwise fire no live event at all — the single PATCH path
    # emits 'feedback:updated' for the equivalent case, so mirror that here
    # with one batch event covering the field-only-changed ids.
    if field_changed_ids:
        try:
            from src.services.event_emitter import emit_event

            await emit_event(
                org_id=auth.organization_id,
                event_type="feedback:updated",
                data={"feedback_ids": sorted(field_changed_ids)},
            )
        except Exception:
            logger.warning(
                "emit_event (feedback:updated) failed on public bulk PATCH", exc_info=True
            )

    # ── Per-item results, in deduped input order ──────────────────────────────
    results: list[PublicFeedbackBulkResultItem] = []
    updated_count = 0
    skipped_count = 0
    for fid in unique_ids:
        if fid not in by_id:
            results.append(
                PublicFeedbackBulkResultItem(id=fid, status="skipped", reason="not_found")
            )
            skipped_count += 1
        elif fid in error_reasons:
            results.append(
                PublicFeedbackBulkResultItem(id=fid, status="error", reason=error_reasons[fid])
            )
        elif fid in changed_ids or fid in field_changed_ids:
            results.append(PublicFeedbackBulkResultItem(id=fid, status="updated"))
            updated_count += 1
        else:
            results.append(PublicFeedbackBulkResultItem(id=fid, status="noop"))

    return PublicFeedbackBulkResponse(
        matched=matched,
        updated=updated_count,
        skipped=skipped_count,
        results=results,
    )


@router.patch(
    "/feedback/{feedback_id}",
    response_model=PublicFeedbackItem,
    dependencies=[Depends(require_scope("write"))],
    summary="Update a feedback item (public API)",
    description=(
        "Update a feedback item's workflow status, tags, and/or urgency flag, and/or "
        "record a correction of an AI-derived field.  Requires the ``write`` scope.  "
        "Corrections are record-only — they capture a training signal without "
        "mutating the stored category/sentiment.  ``tags`` replaces the stored tag "
        "list (``[]`` clears; omitted leaves unchanged).  ``is_urgent`` sets the "
        "urgency flag (omitted leaves unchanged)."
    ),
)
async def public_update_feedback(
    feedback_id: int,
    data: PublicFeedbackUpdate,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicFeedbackItem:
    if not (data.model_fields_set & {"workflow_status", "correction", "tags", "is_urgent"}):
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
    # NB: the correction insert commits separately from the status change above, so a
    # crash between the two is not atomic. AICorrection is an append-only training-signal
    # store, so a rare duplicate on client retry is low-harm; v2 may fold both into one
    # transaction or add a natural-key dedup.
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

    # ── Tags / is_urgent (plain field mutation) ───────────────────────────────
    fields_touched = False
    if "is_urgent" in data.model_fields_set:
        from src.services.ai_correction_service import (
            create_ai_correction,
            urgency_label,
        )

        old_is_urgent = bool(fb.is_urgent)
        new_is_urgent = bool(data.is_urgent)
        fb.is_urgent = new_is_urgent
        fields_touched = True

        # Record-only urgency training signal — same non-atomic note as the
        # correction block above: this insert commits separately from the
        # field-mutation commit below, so a crash between the two is not
        # atomic. AICorrection is append-only, so a rare duplicate on client
        # retry is low-harm.
        if new_is_urgent != old_is_urgent:
            create_ai_correction(
                db,
                organization_id=auth.organization_id,
                user_id=None,
                correction_type="urgency",
                entity_type="feedback_item",
                entity_id=fb.id,
                signal="correction",
                original_value=urgency_label(old_is_urgent),
                corrected_value=urgency_label(new_is_urgent),
                feedback_text=fb.text,
            )
    if "tags" in data.model_fields_set:
        fb.tags = list(data.tags or [])  # rebind new list — JSON columns aren't
        fields_touched = True             # dirty-tracked on in-place mutation.

    if fields_touched:
        db.commit()

        # Best-effort side effects — never fail the write.
        try:
            from src.services.cache_service import cache_invalidate

            cache_invalidate(f"dashboard:{auth.organization_id}:*")
            cache_invalidate(f"analytics:{auth.organization_id}:*")
        except Exception:
            logger.warning("cache_invalidate failed on public PATCH (fields)", exc_info=True)

        try:
            from src.services.event_emitter import emit_event

            await emit_event(
                org_id=auth.organization_id,
                event_type="feedback:updated",
                data={"id": fb.id},
            )
        except Exception:
            logger.warning("emit_event failed on public PATCH (fields)", exc_info=True)

    db.refresh(fb)
    return PublicFeedbackItem.model_validate(fb)


# ─── Feedback delete ──────────────────────────────────────────────────────────


@router.delete(
    "/feedback/{feedback_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope("write"))],
    summary="Delete a feedback item (public API)",
    description=(
        "Delete a feedback item.  Requires the ``write`` scope (no separate "
        "``delete`` scope).  Mirrors the internal dashboard delete: archives "
        "the customer's health record if this was their last feedback item, "
        "invalidates dashboard/analytics caches, and emits ``feedback:deleted``."
    ),
)
async def public_delete_feedback(
    feedback_id: int,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
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

    from src.services.feedback_service import delete_feedback_item

    await delete_feedback_item(db, fb, org_id=auth.organization_id)
    return None


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
    # usage_trend_change payload fields (timeline-trend-event, additive — all Optional)
    old_trend_state: Optional[str] = None
    new_trend_state: Optional[str] = None
    usage_trend_pct: Optional[float] = None


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


# ─── Custom categories (public CRUD) ─────────────────────────────────────────
#
# Mirrors the internal ``/api/v1/categories/custom`` CRUD (see
# src/api/routes/categories.py) via the shared src/services/custom_category_service
# module — identical create/update/delete/list semantics, gated by API-key
# scopes (``read`` for GET, ``write`` for POST/PATCH/DELETE) instead of JWT
# role. Static collection route (``/categories``) is registered before the
# parametric ``/categories/{id}`` route, per public-router convention.


class PublicCustomCategory(BaseModel):
    """Custom category exposed on the public surface."""

    id: int
    name: str
    description: Optional[str] = None
    category_type: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicCustomCategoryCreate(BaseModel):
    """Request body for ``POST /categories``."""

    model_config = {"extra": "forbid"}

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category_type: Literal["pain_point", "feature_request", "urgency", "general"]


class PublicCustomCategoryUpdate(BaseModel):
    """Request body for ``PATCH /categories/{id}``.

    ``category_type`` is intentionally not a field here — it is immutable on
    update, mirroring the internal route; passing it is an unknown field and
    422s via ``extra="forbid"``.
    """

    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


_HEADER_CONTROL_CHARS_RE = re.compile(r"[\r\n\x00-\x1f\x7f]")


def _sanitize_header_value(value: str) -> str:
    """Strip CR/LF and other control characters from an org-authored string
    before it is interpolated into an HTTP header value — prevents header
    injection via a category/rule name containing e.g. ``\\r\\n``."""
    return _HEADER_CONTROL_CHARS_RE.sub(" ", value)


@router.get(
    "/categories",
    response_model=List[PublicCustomCategory],
    dependencies=[Depends(require_scope("read"))],
    summary="List custom categories (public API)",
    description="Org-scoped list of custom categories, optionally filtered by `category_type`.",
)
def public_list_categories(
    category_type: Optional[str] = Query(None),
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> List[PublicCustomCategory]:
    rows = custom_category_service.list_categories(db, auth.organization_id, category_type)
    return [PublicCustomCategory.model_validate(r) for r in rows]


@router.post(
    "/categories",
    response_model=PublicCustomCategory,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("write"))],
    summary="Create a custom category (public API)",
    description="409 on a duplicate (organization, category_type, name).",
)
def public_create_category(
    data: PublicCustomCategoryCreate,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicCustomCategory:
    try:
        row = custom_category_service.create_category(
            db,
            auth.organization_id,
            name=data.name,
            description=data.description,
            category_type=data.category_type,
        )
    except custom_category_service.DuplicateCategoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return PublicCustomCategory.model_validate(row)


@router.patch(
    "/categories/{category_id}",
    response_model=PublicCustomCategory,
    dependencies=[Depends(require_scope("write"))],
    summary="Update a custom category (public API)",
    description=(
        "Update name/description/is_active. `category_type` is not editable "
        "(sending it 422s — unknown field). 404 on missing/other-org id, 409 "
        "on rename collision."
    ),
)
def public_update_category(
    category_id: int,
    data: PublicCustomCategoryUpdate,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> PublicCustomCategory:
    try:
        row = custom_category_service.update_category(
            db,
            auth.organization_id,
            category_id,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
    except custom_category_service.CategoryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    except custom_category_service.DuplicateCategoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return PublicCustomCategory.model_validate(row)


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope("write"))],
    summary="Delete a custom category (public API)",
    description=(
        "Hard delete (204). 404 on missing/other-org id. If the category's "
        "name is referenced by an active `feedback_category_match` automation "
        "rule, the response carries an `X-Rereflect-Warning` header — the "
        "delete still succeeds (advisory only, no cascade)."
    ),
)
def public_delete_category(
    category_id: int,
    response: Response,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomCategory)
        .filter(
            CustomCategory.id == category_id,
            CustomCategory.organization_id == auth.organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    name = row.name
    referencing_rules = custom_category_service.rules_referencing_category(
        db, auth.organization_id, name
    )

    custom_category_service.delete_category(db, auth.organization_id, category_id)

    if referencing_rules:
        safe_name = _sanitize_header_value(name)
        safe_rules = [_sanitize_header_value(r) for r in referencing_rules]
        rule_list = ", ".join(safe_rules)
        response.headers["X-Rereflect-Warning"] = (
            f"category '{safe_name}' is referenced by {len(referencing_rules)} "
            f"automation rule(s): {rule_list}"
        )
    return None


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
                "Keys carry scopes: **read** (GET endpoints, incl. `GET /categories`), "
                "**ingest** (POST /feedback), and **write** (`PATCH /feedback/{id}` — "
                "workflow status, corrections, tags replace, is_urgent — "
                "`DELETE /feedback/{id}`, `POST /feedback/bulk` — the same patch applied "
                "to up to 500 ids in one request — and the custom-categories CRUD: "
                "`POST`/`PATCH`/`DELETE /categories`). "
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
