"""
AI settings API endpoints.
Manage AI analysis configuration, BYOK keys, usage, and budget for the organization.
"""

import os
from datetime import datetime, date, timedelta
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field

from src.database.session import get_db
from src.models.organization import Organization
from src.models.user import User
from src.models.org_ai_config import OrgAIConfig
from src.models.org_api_key import OrgApiKey
from src.models.llm_usage_log import LLMUsageLog
from src.models.llm_model_price import LLMModelPrice
from src.api.dependencies import (
    get_current_user,
    get_current_org,
    require_admin_or_owner,
    require_owner,
    require_feature,
)
from src.config.plans import plan_includes, PLAN_HIERARCHY

router = APIRouter(prefix="/api/v1/settings/ai", tags=["ai-settings"])

VALID_PROVIDERS = {"openai", "anthropic", "google"}


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class ModelConfig(BaseModel):
    categorization: str
    analysis: str
    insights: str


class AISettingsResponse(BaseModel):
    ai_analysis_enabled: bool
    default_provider: str
    models: ModelConfig


class AISettingsUpdate(BaseModel):
    ai_analysis_enabled: Optional[bool] = None
    default_provider: Optional[str] = None
    model_categorization: Optional[str] = None
    model_analysis: Optional[str] = None
    model_insights: Optional[str] = None


class APIKeyResponse(BaseModel):
    provider: str
    key_hint: Optional[str]
    is_valid: bool
    created_at: datetime


class AddAPIKeyRequest(BaseModel):
    provider: Literal["openai", "anthropic", "google"]
    api_key: str = Field(..., min_length=1)


class ValidateKeyRequest(BaseModel):
    provider: Literal["openai", "anthropic", "google"]
    api_key: str = Field(..., min_length=1)


class ValidateKeyResponse(BaseModel):
    valid: bool
    error_message: Optional[str] = None


class TestModelRequest(BaseModel):
    provider: Literal["openai", "anthropic", "google"]
    model: str


class TestModelResponse(BaseModel):
    provider: str
    model: str
    result: dict
    tokens: int
    cost_cents: float
    latency_ms: int


class ModelInfo(BaseModel):
    id: int
    provider: str
    model_id: str
    display_name: str
    tier: str
    min_plan: str
    supports_json_mode: bool
    input_price_per_1m_tokens: float
    output_price_per_1m_tokens: float


class ProviderUsage(BaseModel):
    provider: str
    tokens: int
    requests: int
    cost_cents: float


class UsageSummaryResponse(BaseModel):
    month: str
    total_tokens: int
    total_requests: int
    estimated_cost_cents: float
    by_provider: list[ProviderUsage]
    fallback_count: int


class DayUsage(BaseModel):
    date: str
    tokens: int
    requests: int
    cost_cents: float


class UsageDailyResponse(BaseModel):
    days: list[DayUsage]


class BudgetResponse(BaseModel):
    monthly_limit_cents: Optional[int]
    used_cents: int
    resets_at: Optional[datetime]
    is_exceeded: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_create_config(org_id: int, db: Session) -> OrgAIConfig:
    """Get or create OrgAIConfig for an organization."""
    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    if not config:
        config = OrgAIConfig(
            organization_id=org_id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _build_settings_response(org: Organization, config: Optional[OrgAIConfig]) -> AISettingsResponse:
    """Build the AI settings response object.

    Budget machinery has been removed (A6): there is no owner-level spend cap
    in the self-hosted product. The DB columns remain as dead columns; we
    simply stop reading them here.
    """
    if config:
        default_provider = config.default_provider
        model_config = ModelConfig(
            categorization=config.model_categorization,
            analysis=config.model_analysis,
            insights=config.model_insights,
        )
    else:
        default_provider = "openai"
        model_config = ModelConfig(
            categorization="gpt-4o-mini",
            analysis="gpt-4o-mini",
            insights="gpt-4o-mini",
        )

    return AISettingsResponse(
        ai_analysis_enabled=org.ai_analysis_enabled,
        default_provider=default_provider,
        models=model_config,
    )


def validate_provider_key(provider: str, api_key: str) -> tuple[bool, Optional[str]]:
    """
    Validate an API key by making a minimal test call to the provider.
    Returns (valid, error_message).
    """
    try:
        if provider == "openai":
            import openai
            client = openai.OpenAI(api_key=api_key)
            client.models.list()
            return True, None
        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.models.list()
            return True, None
        elif provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            list(genai.list_models())
            return True, None
        return False, f"Unknown provider: {provider}"
    except Exception as e:
        return False, str(e)


def run_model_test(
    provider: str,
    model: str,
    api_key: str,
) -> dict:
    """
    Run a canned sample feedback through a model for testing.
    Returns result dict with provider, model, result, tokens, cost_cents, latency_ms.
    """
    import time
    import json

    sample_text = (
        "I've been having terrible issues with your payment system. "
        "It keeps crashing and I can't process any orders. This is urgent!"
    )
    prompt = (
        "Analyze this customer feedback and return JSON with: "
        "sentiment_label (positive/neutral/negative), is_urgent (bool), "
        "pain_point_category (string or null), confidence (0-1).\n\n"
        f"Feedback: \"{sample_text}\""
    )

    start = time.time()

    try:
        if provider == "openai":
            import openai
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            tokens = resp.usage.total_tokens if resp.usage else 0
            prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
            completion_tokens = resp.usage.completion_tokens if resp.usage else 0

        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt + "\n\nReturn ONLY valid JSON."}],
            )
            content = resp.content[0].text if resp.content else "{}"
            prompt_tokens = resp.usage.input_tokens if resp.usage else 0
            completion_tokens = resp.usage.output_tokens if resp.usage else 0
            tokens = prompt_tokens + completion_tokens

        elif provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            gen_model = genai.GenerativeModel(model)
            resp = gen_model.generate_content(prompt)
            content = resp.text or "{}"
            tokens = 0
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                prompt_tokens = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
                completion_tokens = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
                tokens = prompt_tokens + completion_tokens

        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model test failed: {str(e)}")

    latency_ms = int((time.time() - start) * 1000)

    # Estimate cost from pricing table
    from src.models.llm_model_price import LLMModelPrice
    cost_cents = 0.0
    # Simple estimate: (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    # We don't have db here, so use a rough calculation
    cost_cents = round((prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000 * 100, 4)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {"raw": content}

    return {
        "provider": provider,
        "model": model,
        "result": result,
        "tokens": tokens,
        "cost_cents": cost_cents,
        "latency_ms": latency_ms,
    }


def _plan_level(plan: str) -> int:
    """Return numeric plan level (higher = better)."""
    try:
        return PLAN_HIERARCHY.index(plan)
    except ValueError:
        return 0


# ── GET /api/v1/settings/ai ───────────────────────────────────────────────────

@router.get("", response_model=AISettingsResponse)
def get_ai_settings(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get AI analysis settings for the organization."""
    config = db.query(OrgAIConfig).filter_by(organization_id=current_org.id).first()
    return _build_settings_response(current_org, config)


# ── PATCH /api/v1/settings/ai ─────────────────────────────────────────────────

@router.patch(
    "",
    response_model=AISettingsResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_ai_settings(
    data: AISettingsUpdate,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update AI analysis settings. Admin+ only."""
    if data.ai_analysis_enabled is not None:
        current_org.ai_analysis_enabled = data.ai_analysis_enabled

    config = _get_or_create_config(current_org.id, db)

    if data.default_provider is not None:
        if data.default_provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}",
            )
        config.default_provider = data.default_provider

    if data.model_categorization is not None:
        config.model_categorization = data.model_categorization
    if data.model_analysis is not None:
        config.model_analysis = data.model_analysis
    if data.model_insights is not None:
        config.model_insights = data.model_insights

    db.commit()
    db.refresh(current_org)
    db.refresh(config)

    return _build_settings_response(current_org, config)


# ── GET /api/v1/settings/ai/keys ─────────────────────────────────────────────

@router.get("/keys", response_model=list[APIKeyResponse])
def list_api_keys(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List BYOK API keys for the organization (key_hint only, not full key)."""
    keys = db.query(OrgApiKey).filter_by(organization_id=current_org.id).all()
    return [
        APIKeyResponse(
            provider=k.provider,
            key_hint=k.key_hint,
            is_valid=k.is_valid,
            created_at=k.created_at,
        )
        for k in keys
    ]


# ── POST /api/v1/settings/ai/keys ────────────────────────────────────────────

@router.post(
    "/keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_owner)],
)
def add_api_key(
    data: AddAPIKeyRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Add or replace a BYOK API key. Owner only.

    No plan gate — in the self-hosted product BYOK is the only way AI works,
    so it must be available on every plan (A7).
    """
    from src.utils.encryption import encrypt_api_key, get_key_hint

    try:
        encrypted = encrypt_api_key(data.api_key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption not configured. Contact support.",
        )
    hint = get_key_hint(data.api_key)

    # Upsert: check if key for this provider already exists
    existing = db.query(OrgApiKey).filter_by(
        organization_id=current_org.id,
        provider=data.provider,
    ).first()

    if existing:
        existing.encrypted_key = encrypted
        existing.key_hint = hint
        existing.is_valid = True
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        key = existing
    else:
        key = OrgApiKey(
            organization_id=current_org.id,
            provider=data.provider,
            encrypted_key=encrypted,
            key_hint=hint,
            is_valid=True,
        )
        db.add(key)
        db.commit()
        db.refresh(key)

    return APIKeyResponse(
        provider=key.provider,
        key_hint=key.key_hint,
        is_valid=key.is_valid,
        created_at=key.created_at,
    )


# ── DELETE /api/v1/settings/ai/keys/{provider} ───────────────────────────────

@router.delete(
    "/keys/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_owner)],
)
def delete_api_key(
    provider: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Remove a BYOK API key for the given provider. Owner only."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}",
        )

    key = db.query(OrgApiKey).filter_by(
        organization_id=current_org.id,
        provider=provider,
    ).first()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key found for provider '{provider}'",
        )

    db.delete(key)
    db.commit()
    return None


# ── POST /api/v1/settings/ai/keys/validate ───────────────────────────────────

@router.post("/keys/validate", response_model=ValidateKeyResponse)
def validate_api_key(
    data: ValidateKeyRequest,
    current_org: Organization = Depends(get_current_org),
):
    """Validate an API key against the provider. Does not store the key."""
    valid, error = validate_provider_key(data.provider, data.api_key)
    return ValidateKeyResponse(valid=valid, error_message=error)


# ── POST /api/v1/settings/ai/test-model ──────────────────────────────────────

@router.post("/test-model", response_model=TestModelResponse)
def test_model(
    data: TestModelRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Run a canned sample feedback through the specified model.
    Rate limited to 5 calls/minute per org.
    Plan gating: cannot test premium models on free plan.
    """
    # Check model plan gating
    model_price = db.query(LLMModelPrice).filter_by(
        provider=data.provider,
        model_id=data.model,
        is_available=True,
    ).first()

    if model_price:
        org_plan = current_org.plan or "free"
        if not plan_includes(org_plan, model_price.min_plan):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "model_not_available",
                    "model": data.model,
                    "required_plan": model_price.min_plan,
                    "message": f"This model requires the {model_price.min_plan.title()} plan or higher.",
                    "upgrade_url": "/settings/billing",
                },
            )

    # Get org's API key for this provider (BYOK) or use system key
    api_key = _get_api_key_for_provider(data.provider, current_org.id, db)

    result = run_model_test(
        provider=data.provider,
        model=data.model,
        api_key=api_key,
    )

    return TestModelResponse(
        provider=result["provider"],
        model=result["model"],
        result=result["result"],
        tokens=result["tokens"],
        cost_cents=result["cost_cents"],
        latency_ms=result["latency_ms"],
    )


def _get_api_key_for_provider(provider: str, org_id: int, db: Session) -> str:
    """Return the org's BYOK API key for the given provider.

    There is NO system/env key fallback. If the org has no valid BYOK key for
    this provider, raises HTTP 503 so the caller can surface a "configure your
    API key" message to the user.
    """
    from src.utils.byok import resolve_org_byok_key

    key = resolve_org_byok_key(provider, org_id, db)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"No API key configured for provider '{provider}'. "
                "Please add your API key in Settings → AI → API Keys."
            ),
        )
    return key


# ── GET /api/v1/settings/ai/models ───────────────────────────────────────────

@router.get("/models", response_model=list[ModelInfo])
def get_available_models(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return models available for the org's plan (available + not deprecated)."""
    org_plan = current_org.plan or "free"

    # Get all available, non-deprecated models
    all_models = db.query(LLMModelPrice).filter(
        LLMModelPrice.is_available == True,
        LLMModelPrice.is_deprecated == False,
    ).all()

    # Filter by plan level
    accessible = [
        m for m in all_models
        if plan_includes(org_plan, m.min_plan)
    ]

    return [
        ModelInfo(
            id=m.id,
            provider=m.provider,
            model_id=m.model_id,
            display_name=m.display_name,
            tier=m.tier,
            min_plan=m.min_plan,
            supports_json_mode=m.supports_json_mode,
            input_price_per_1m_tokens=m.input_price_per_1m_tokens,
            output_price_per_1m_tokens=m.output_price_per_1m_tokens,
        )
        for m in accessible
    ]


# ── GET /api/v1/settings/ai/usage ────────────────────────────────────────────

@router.get(
    "/usage",
    response_model=UsageSummaryResponse,
    dependencies=[Depends(require_feature("ai_usage_dashboard"))],
)
def get_usage_summary(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return monthly usage summary. Pro+ plan required."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    logs = db.query(LLMUsageLog).filter(
        LLMUsageLog.organization_id == current_org.id,
        LLMUsageLog.created_at >= month_start,
    ).all()

    total_tokens = sum(l.total_tokens for l in logs)
    total_requests = len(logs)
    estimated_cost_cents = sum(l.estimated_cost_cents for l in logs)
    fallback_count = sum(1 for l in logs if l.was_fallback)

    # By provider
    provider_map: dict[str, dict] = {}
    for l in logs:
        if l.provider not in provider_map:
            provider_map[l.provider] = {"tokens": 0, "requests": 0, "cost_cents": 0.0}
        provider_map[l.provider]["tokens"] += l.total_tokens
        provider_map[l.provider]["requests"] += 1
        provider_map[l.provider]["cost_cents"] += l.estimated_cost_cents

    by_provider = [
        ProviderUsage(
            provider=provider,
            tokens=stats["tokens"],
            requests=stats["requests"],
            cost_cents=stats["cost_cents"],
        )
        for provider, stats in provider_map.items()
    ]

    return UsageSummaryResponse(
        month=now.strftime("%Y-%m"),
        total_tokens=total_tokens,
        total_requests=total_requests,
        estimated_cost_cents=estimated_cost_cents,
        by_provider=by_provider,
        fallback_count=fallback_count,
    )


# ── GET /api/v1/settings/ai/usage/daily ──────────────────────────────────────

@router.get(
    "/usage/daily",
    response_model=UsageDailyResponse,
    dependencies=[Depends(require_feature("ai_usage_dashboard"))],
)
def get_usage_daily(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Return daily usage breakdown for the current month. Pro+ plan required."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    logs = db.query(LLMUsageLog).filter(
        LLMUsageLog.organization_id == current_org.id,
        LLMUsageLog.created_at >= month_start,
    ).all()

    # Group by date
    day_map: dict[str, dict] = {}
    for l in logs:
        day_str = l.created_at.strftime("%Y-%m-%d")
        if day_str not in day_map:
            day_map[day_str] = {"tokens": 0, "requests": 0, "cost_cents": 0.0}
        day_map[day_str]["tokens"] += l.total_tokens
        day_map[day_str]["requests"] += 1
        day_map[day_str]["cost_cents"] += l.estimated_cost_cents

    days = [
        DayUsage(
            date=day,
            tokens=stats["tokens"],
            requests=stats["requests"],
            cost_cents=stats["cost_cents"],
        )
        for day, stats in sorted(day_map.items())
    ]

    return UsageDailyResponse(days=days)


# ── GET /api/v1/settings/ai/budget ───────────────────────────────────────────

@router.get("/budget", response_model=BudgetResponse)
def get_budget(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get current AI budget status for the organization.

    A6 note: Budget capping has been removed from the self-hosted product.
    This endpoint is kept for API compatibility but always returns a
    no-budget-cap state (monthly_limit_cents=None, is_exceeded=False).
    The underlying DB columns (monthly_budget_cents etc.) are dead columns
    pending a future migration; we stop reading them here.
    """
    return BudgetResponse(
        monthly_limit_cents=None,
        used_cents=0,
        resets_at=None,
        is_exceeded=False,
    )
