"""
System Admin: AI Model Price Management API endpoints.
All endpoints require system admin access.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.api.dependencies import require_system_admin
from src.models.llm_model_price import LLMModelPrice

router = APIRouter(prefix="/api/v1/admin/ai-models", tags=["admin-ai-models"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class AdminModelResponse(BaseModel):
    id: int
    provider: str
    model_id: str
    display_name: str
    input_price_per_1m_tokens: float
    output_price_per_1m_tokens: float
    context_window: Optional[int]
    max_output_tokens: Optional[int]
    supports_json_mode: bool
    tier: str
    min_plan: str
    is_available: bool
    is_deprecated: bool
    replacement_model_id: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminModelUpdate(BaseModel):
    input_price_per_1m_tokens: Optional[float] = None
    output_price_per_1m_tokens: Optional[float] = None
    is_available: Optional[bool] = None
    is_deprecated: Optional[bool] = None
    replacement_model_id: Optional[str] = None
    min_plan: Optional[str] = None
    tier: Optional[str] = None


class SyncPricesResponse(BaseModel):
    synced: int
    errors: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_provider_prices() -> dict:
    """
    Fetch latest prices from provider APIs.
    In production, this would call actual provider pricing APIs.
    Returns a dict with synced count and any errors.
    """
    # Stub: actual provider API calls would go here
    return {"synced": 0, "errors": ["Provider pricing APIs not yet integrated"]}


# ── GET /api/v1/admin/ai-models ───────────────────────────────────────────────

@router.get("", response_model=list[AdminModelResponse], dependencies=[Depends(require_system_admin)])
def list_all_models(db: Session = Depends(get_db)):
    """List all models including deprecated ones. System admin only."""
    models = db.query(LLMModelPrice).order_by(
        LLMModelPrice.provider,
        LLMModelPrice.tier,
        LLMModelPrice.model_id,
    ).all()
    return models


# ── PATCH /api/v1/admin/ai-models/{id} ───────────────────────────────────────

@router.patch("/{model_id}", response_model=AdminModelResponse, dependencies=[Depends(require_system_admin)])
def update_model(
    model_id: int,
    data: AdminModelUpdate,
    db: Session = Depends(get_db),
):
    """Update model price, availability, or deprecation. System admin only."""
    model = db.query(LLMModelPrice).filter(LLMModelPrice.id == model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model with ID {model_id} not found",
        )

    if data.input_price_per_1m_tokens is not None:
        model.input_price_per_1m_tokens = data.input_price_per_1m_tokens
    if data.output_price_per_1m_tokens is not None:
        model.output_price_per_1m_tokens = data.output_price_per_1m_tokens
    if data.is_available is not None:
        model.is_available = data.is_available
    if data.is_deprecated is not None:
        model.is_deprecated = data.is_deprecated
    if data.replacement_model_id is not None:
        model.replacement_model_id = data.replacement_model_id
    if data.min_plan is not None:
        model.min_plan = data.min_plan
    if data.tier is not None:
        model.tier = data.tier

    model.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(model)
    return model


# ── POST /api/v1/admin/ai-models/sync-prices ─────────────────────────────────

@router.post("/sync-prices", response_model=SyncPricesResponse, dependencies=[Depends(require_system_admin)])
def sync_prices(db: Session = Depends(get_db)):
    """Fetch latest prices from provider APIs and update the model price table. System admin only."""
    result = fetch_provider_prices()
    return SyncPricesResponse(
        synced=result.get("synced", 0),
        errors=result.get("errors", []),
    )
