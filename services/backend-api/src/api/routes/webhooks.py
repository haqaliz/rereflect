"""
Custom Webhook Endpoints — CRUD API (M3.1).

Endpoints:
  GET    /api/v1/webhooks                       List org's webhook endpoints
  POST   /api/v1/webhooks                       Create webhook endpoint (admin+)
  GET    /api/v1/webhooks/{id}                  Get webhook details
  PUT    /api/v1/webhooks/{id}                  Update webhook config (admin+)
  DELETE /api/v1/webhooks/{id}                  Delete webhook (admin+)
  POST   /api/v1/webhooks/{id}/test             Send test delivery (admin+)
  POST   /api/v1/webhooks/{id}/rotate-secret    Rotate signing secret (admin+)
  GET    /api/v1/webhooks/{id}/deliveries       List last 50 deliveries
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
)
from src.config.plans import get_webhook_limit, get_webhook_header_limit
from src.database.session import get_db
from src.models.organization import Organization
from src.models.webhook_delivery import WebhookDelivery
from src.models.webhook_endpoint import WebhookEndpoint
from src.utils.encryption import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_EVENTS = frozenset({
    "feedback.created",
    "feedback.analyzed",
    "feedback.status_changed",
    "feedback.urgent",
    "feedback.category_match",
})

MASKED_SECRET = "***"


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class WebhookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=8, max_length=2048)
    events: List[str] = Field(default_factory=list)
    category_filters: List[str] = Field(default_factory=list)
    custom_headers: Optional[Dict[str, str]] = None
    retry_mode: str = Field(default="fire_and_forget")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: List[str]) -> List[str]:
        invalid = [e for e in v if e not in VALID_EVENTS]
        if invalid:
            raise ValueError(
                f"Invalid event(s): {invalid}. "
                f"Valid events: {sorted(VALID_EVENTS)}"
            )
        return v

    @field_validator("retry_mode")
    @classmethod
    def validate_retry_mode(cls, v: str) -> str:
        valid = {"fire_and_forget", "exponential_backoff"}
        if v not in valid:
            raise ValueError(f"retry_mode must be one of {valid}")
        return v

    @model_validator(mode="after")
    def validate_category_filters(self) -> "WebhookCreate":
        if self.category_filters and "feedback.category_match" not in self.events:
            raise ValueError(
                "category_filters can only be used when 'feedback.category_match' "
                "is included in events"
            )
        return self


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    url: Optional[str] = Field(None, min_length=8, max_length=2048)
    events: Optional[List[str]] = None
    category_filters: Optional[List[str]] = None
    custom_headers: Optional[Dict[str, str]] = None
    retry_mode: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        invalid = [e for e in v if e not in VALID_EVENTS]
        if invalid:
            raise ValueError(f"Invalid event(s): {invalid}")
        return v

    @field_validator("retry_mode")
    @classmethod
    def validate_retry_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = {"fire_and_forget", "exponential_backoff"}
        if v not in valid:
            raise ValueError(f"retry_mode must be one of {valid}")
        return v


class WebhookResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    url: str
    signing_secret: str  # raw on create, "***" on get/list
    events: List[str]
    category_filters: List[str]
    retry_mode: str
    is_active: bool
    consecutive_failures: int
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


class DeliveryResponse(BaseModel):
    id: int
    webhook_id: int
    event: str
    feedback_id: Optional[int]
    status: str
    attempt: int
    response_code: Optional[int]
    response_body: Optional[str]
    error_message: Optional[str]
    latency_ms: Optional[int]
    created_at: Any

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_webhook_or_404(webhook_id: int, org_id: int, db: Session) -> WebhookEndpoint:
    """Return webhook if it belongs to the org, else raise 404."""
    webhook = (
        db.query(WebhookEndpoint)
        .filter(
            WebhookEndpoint.id == webhook_id,
            WebhookEndpoint.organization_id == org_id,
        )
        .first()
    )
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return webhook


def _to_response(webhook: WebhookEndpoint, reveal_secret: bool = False) -> dict:
    """Serialise a WebhookEndpoint to a response dict."""
    return {
        "id": webhook.id,
        "organization_id": webhook.organization_id,
        "name": webhook.name,
        "url": webhook.url,
        "signing_secret": (
            decrypt_api_key(webhook.signing_secret) if reveal_secret else MASKED_SECRET
        ),
        "events": webhook.events or [],
        "category_filters": webhook.category_filters or [],
        "retry_mode": webhook.retry_mode,
        "is_active": webhook.is_active,
        "consecutive_failures": webhook.consecutive_failures,
        "created_at": webhook.created_at,
        "updated_at": webhook.updated_at,
    }


def _check_header_limit(
    custom_headers: Optional[Dict[str, str]],
    plan: str,
) -> None:
    """Raise 422 if the number of custom headers exceeds the plan limit."""
    if not custom_headers:
        return
    limit = get_webhook_header_limit(plan)
    if len(custom_headers) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{
                "msg": (
                    f"Custom header count {len(custom_headers)} exceeds plan limit of {limit}. "
                    "Upgrade your plan to add more headers."
                ),
                "type": "value_error.header_limit",
            }],
        )


def _send_test_delivery(webhook: WebhookEndpoint, db: Session) -> dict:
    """
    Send a sample payload to the webhook URL and return result metadata.

    This is a module-level function so tests can monkeypatch it.
    """
    import hmac
    import hashlib
    import httpx
    from datetime import datetime

    sample_payload = {
        "event": "test",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "webhook_id": webhook.id,
        "organization_id": webhook.organization_id,
        "data": {
            "feedback": {
                "id": 0,
                "text": "This is a test delivery from Rereflect.",
                "sentiment_label": "neutral",
                "sentiment_score": 0.0,
                "tags": [],
                "is_urgent": False,
                "churn_risk_score": None,
                "pain_point_category": None,
                "feature_request_category": None,
                "workflow_status": "new",
                "assigned_to": None,
                "customer_email": None,
                "source": "test",
                "created_at": datetime.utcnow().isoformat() + "Z",
            }
        },
    }

    payload_bytes = json.dumps(sample_payload, default=str).encode()
    raw_secret = decrypt_api_key(webhook.signing_secret)
    signature = hmac.new(raw_secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "X-Rereflect-Signature": f"sha256={signature}",
    }

    # Merge in custom headers if any
    if webhook.custom_headers:
        try:
            stored = json.loads(decrypt_api_key(webhook.custom_headers))
            headers.update(stored)
        except Exception:
            pass

    start = time.monotonic()
    try:
        resp = httpx.post(
            webhook.url,
            content=payload_bytes,
            headers=headers,
            timeout=10.0,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        result = {
            "status": "sent" if resp.is_success else "failed",
            "response_code": resp.status_code,
            "response_body": resp.text[:1024],
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        result = {
            "status": "failed",
            "response_code": None,
            "response_body": None,
            "latency_ms": latency_ms,
            "error": str(exc),
        }

    # Log the test delivery
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event="test",
        feedback_id=None,
        status=result["status"],
        attempt=1,
        response_code=result["response_code"],
        response_body=result.get("response_body"),
        error_message=result.get("error"),
        latency_ms=result["latency_ms"],
        payload=sample_payload,
    )
    db.add(delivery)
    db.commit()

    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=None)
def list_webhooks(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all webhook endpoints for the current organisation."""
    plan = current_org.plan or "free"
    limit = get_webhook_limit(plan)

    webhooks = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.organization_id == current_org.id)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )

    return {
        "webhooks": [_to_response(w, reveal_secret=False) for w in webhooks],
        "count": len(webhooks),
        "limit": limit,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=None,
             dependencies=[Depends(require_admin_or_owner)])
def create_webhook(
    payload: WebhookCreate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new webhook endpoint. Admin or Owner only."""
    plan = current_org.plan or "free"
    limit = get_webhook_limit(plan)

    # Enforce plan limit
    if limit is not None:
        existing = (
            db.query(WebhookEndpoint)
            .filter(WebhookEndpoint.organization_id == current_org.id)
            .count()
        )
        if existing >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "webhook_limit_exceeded",
                    "limit": limit,
                    "used": existing,
                    "message": (
                        f"You have reached your plan limit of {limit} webhook endpoint(s). "
                        "Upgrade your plan to add more."
                    ),
                    "upgrade_url": "/settings/billing",
                },
            )

    # Enforce custom headers plan limit
    _check_header_limit(payload.custom_headers, plan)

    # Enforce retry_mode plan limit: free plan is fire_and_forget only
    if plan == "free" and payload.retry_mode == "exponential_backoff":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{
                "msg": "Exponential backoff retry requires Pro plan or higher.",
                "type": "value_error.retry_mode",
            }],
        )

    # Generate and encrypt signing secret
    raw_secret = secrets.token_hex(32)
    encrypted_secret = encrypt_api_key(raw_secret)

    # Encrypt custom headers if provided
    encrypted_headers = None
    if payload.custom_headers:
        encrypted_headers = encrypt_api_key(json.dumps(payload.custom_headers))

    webhook = WebhookEndpoint(
        organization_id=current_org.id,
        name=payload.name,
        url=payload.url,
        signing_secret=encrypted_secret,
        events=payload.events,
        category_filters=payload.category_filters,
        custom_headers=encrypted_headers,
        retry_mode=payload.retry_mode,
        is_active=True,
        consecutive_failures=0,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    # Reveal raw secret only on creation
    return _to_response(webhook, reveal_secret=True)


@router.get("/{webhook_id}", response_model=None)
def get_webhook(
    webhook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get a single webhook endpoint (masked secret)."""
    webhook = _get_webhook_or_404(webhook_id, current_org.id, db)
    return _to_response(webhook, reveal_secret=False)


@router.put("/{webhook_id}", response_model=None,
            dependencies=[Depends(require_admin_or_owner)])
def update_webhook(
    webhook_id: int,
    payload: WebhookUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update a webhook endpoint configuration. Admin or Owner only."""
    webhook = _get_webhook_or_404(webhook_id, current_org.id, db)
    plan = current_org.plan or "free"

    # Determine final events list for category_filters validation
    final_events = payload.events if payload.events is not None else (webhook.events or [])
    final_filters = payload.category_filters if payload.category_filters is not None else (webhook.category_filters or [])
    if final_filters and "feedback.category_match" not in final_events:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{
                "msg": "category_filters can only be used when 'feedback.category_match' is included in events",
                "type": "value_error.category_match",
            }],
        )

    if payload.name is not None:
        webhook.name = payload.name
    if payload.url is not None:
        webhook.url = payload.url
    if payload.events is not None:
        webhook.events = payload.events
    if payload.category_filters is not None:
        webhook.category_filters = payload.category_filters
    if payload.retry_mode is not None:
        if plan == "free" and payload.retry_mode == "exponential_backoff":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[{
                    "msg": "Exponential backoff retry requires Pro plan or higher.",
                    "type": "value_error.retry_mode",
                }],
            )
        webhook.retry_mode = payload.retry_mode
    if payload.is_active is not None:
        webhook.is_active = payload.is_active
    if payload.custom_headers is not None:
        _check_header_limit(payload.custom_headers, plan)
        webhook.custom_headers = encrypt_api_key(json.dumps(payload.custom_headers))

    db.commit()
    db.refresh(webhook)
    return _to_response(webhook, reveal_secret=False)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin_or_owner)])
def delete_webhook(
    webhook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete a webhook endpoint. Admin or Owner only."""
    webhook = _get_webhook_or_404(webhook_id, current_org.id, db)
    db.delete(webhook)
    db.commit()


@router.post("/{webhook_id}/test", response_model=None,
             dependencies=[Depends(require_admin_or_owner)])
def test_webhook(
    webhook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Send a test payload to the webhook URL and return the result."""
    webhook = _get_webhook_or_404(webhook_id, current_org.id, db)
    result = _send_test_delivery(webhook, db)
    return result


@router.post("/{webhook_id}/rotate-secret", response_model=None,
             dependencies=[Depends(require_admin_or_owner)])
def rotate_secret(
    webhook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Rotate the signing secret. Returns the new raw secret (shown once)."""
    webhook = _get_webhook_or_404(webhook_id, current_org.id, db)

    raw_secret = secrets.token_hex(32)
    webhook.signing_secret = encrypt_api_key(raw_secret)
    db.commit()
    db.refresh(webhook)

    return {"signing_secret": raw_secret}


@router.get("/{webhook_id}/deliveries", response_model=None)
def list_deliveries(
    webhook_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List the last 50 delivery attempts for a webhook endpoint."""
    webhook = _get_webhook_or_404(webhook_id, current_org.id, db)

    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.webhook_id == webhook.id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(50)
        .all()
    )

    return {
        "deliveries": [
            {
                "id": d.id,
                "webhook_id": d.webhook_id,
                "event": d.event,
                "feedback_id": d.feedback_id,
                "status": d.status,
                "attempt": d.attempt,
                "response_code": d.response_code,
                "response_body": d.response_body,
                "error_message": d.error_message,
                "latency_ms": d.latency_ms,
                "created_at": d.created_at,
            }
            for d in deliveries
        ]
    }
