"""
Billing API routes for subscription management and usage tracking.

SELF-HOSTED OSS NOTE (B3):
Stripe-only routes have been removed:
  - POST /checkout
  - POST /portal
  - GET  /invoices
  - POST /sync-subscription
  - POST /webhooks/stripe
  - GET  /subscription   (exposed Stripe columns — dropped in B4 cleanup)
  - POST /start-trial    (trials meaningless when everything is unlimited)

Kept (Stripe-free, useful for self-hosted):
  - GET  /plans   — plan comparison / info
  - GET  /usage   — feedback and seat usage counters (calendar-month window,
                    no Stripe billing period, no Stripe-era counters)

The `stripe_service` import is retained so the module compiles whether or not
the `stripe` package is installed (stripe_service itself is now import-guarded).
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.organization import Organization
from src.models.usage import UsageRecord
from src.models.user import User
from src.api.dependencies import get_current_org
from src.config.plans import PLANS, get_plan, get_feedback_limit, get_seat_limit
from src.services.stripe_service import get_stripe_service  # import-guarded stub


router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


# ============================================================================
# Schemas
# ============================================================================

class PlanFeature(BaseModel):
    id: str
    name: str
    included: bool


class PlanResponse(BaseModel):
    id: str
    name: str
    description: str
    price_monthly: Optional[int]  # cents
    price_annual: Optional[int]  # cents
    feedback_limit: Optional[int]
    seat_limit: Optional[int]
    features: list[PlanFeature]
    is_popular: bool = False
    overage_enabled: bool = False
    overage_price_cents: Optional[int] = None


class PlansListResponse(BaseModel):
    plans: list[PlanResponse]


class UsageResponse(BaseModel):
    feedback_used: int
    feedback_limit: Optional[int]
    feedback_percentage: float
    seats_used: int
    seats_limit: Optional[int]
    seats_percentage: float
    period_start: Optional[datetime]
    period_end: Optional[datetime]


# ============================================================================
# Plan Endpoints
# ============================================================================

PLAN_DESCRIPTIONS = {
    "free": "Get started with basic feedback analysis",
    "pro": "For growing teams that need more power",
    "business": "Advanced features for larger organizations",
    "enterprise": "Custom solutions for enterprise needs",
}

FEATURE_NAMES = {
    "basic_dashboard": "Dashboard & Analytics",
    "csv_import": "CSV Import",
    "sentiment_analysis": "Sentiment Analysis",
    "email_support": "Email Support",
    "slack_integration": "Slack, Intercom, Email & more",
    "email_integration": "Email Forwarding",
    "webhooks": "Webhooks",
    "data_export": "Data Export",
    "trends_analytics": "Trends Analytics",
    "priority_support": "Priority Support",
    "api_access": "API Access",
    "advanced_analytics": "Advanced Analytics",
    "custom_categories": "Custom Categories",
    "dedicated_support": "Dedicated Support",
    "sso_saml": "SSO/SAML",
    "custom_integrations": "Custom Integrations",
    "sla": "SLA",
    "dedicated_csm": "Dedicated CSM",
    "audit_logs": "Audit Logs",
    "custom_retention": "Custom Retention",
}

ALL_FEATURE_IDS = list(FEATURE_NAMES.keys())


@router.get("/plans", response_model=PlansListResponse)
def get_plans():
    """Get all available subscription plans."""
    plans = []
    for plan_id, plan in PLANS.items():
        plan_features = plan.get("features", [])
        features = [
            PlanFeature(
                id=f_id,
                name=FEATURE_NAMES.get(f_id, f_id),
                included=f_id in plan_features,
            )
            for f_id in ALL_FEATURE_IDS
        ]
        plans.append(PlanResponse(
            id=plan_id,
            name=plan["name"],
            description=PLAN_DESCRIPTIONS.get(plan_id, ""),
            price_monthly=plan["price_monthly"],
            price_annual=plan["price_annual"],
            feedback_limit=plan["feedback_limit"],
            seat_limit=plan["seat_limit"],
            features=features,
            is_popular=plan_id == "pro",
            overage_enabled=plan.get("overage_enabled", False),
            overage_price_cents=plan.get("overage_price_cents"),
        ))
    return PlansListResponse(plans=plans)


# ============================================================================
# Usage Endpoints
# ============================================================================

def _current_calendar_month() -> tuple[datetime, datetime]:
    """Return (period_start, period_end) for the current calendar month (UTC)."""
    now = datetime.utcnow()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        period_end = period_start.replace(year=now.year + 1, month=1)
    else:
        period_end = period_start.replace(month=now.month + 1)
    return period_start, period_end


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get current usage for the current calendar month.

    Stripe-free: period is always the UTC calendar month.
    No Stripe billing period or overage columns are read.
    """
    from src.models.feedback import FeedbackItem

    # Always use calendar-month window — no Stripe billing period
    period_start, period_end = _current_calendar_month()

    # Get or create usage record for this calendar month
    usage = db.query(UsageRecord).filter(
        UsageRecord.organization_id == current_org.id,
        UsageRecord.period_start == period_start,
    ).first()

    if not usage:
        # Count feedback for this calendar period
        feedback_count = db.query(FeedbackItem).filter(
            FeedbackItem.organization_id == current_org.id,
            FeedbackItem.created_at >= period_start,
            FeedbackItem.created_at < period_end,
        ).count()

        usage = UsageRecord(
            organization_id=current_org.id,
            period_start=period_start,
            period_end=period_end,
            feedback_count=feedback_count,
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)

    # Get limits based on plan
    plan = current_org.plan or "free"
    feedback_limit = get_feedback_limit(plan)
    seat_limit = get_seat_limit(plan)

    # Count current seats
    seats_used = db.query(User).filter(
        User.organization_id == current_org.id
    ).count()

    # Calculate percentages
    feedback_percentage = 0.0
    if feedback_limit:
        feedback_percentage = min(100.0, (usage.feedback_count / feedback_limit) * 100)

    seats_percentage = 0.0
    if seat_limit:
        seats_percentage = min(100.0, (seats_used / seat_limit) * 100)

    return UsageResponse(
        feedback_used=usage.feedback_count,
        feedback_limit=feedback_limit,
        feedback_percentage=round(feedback_percentage, 1),
        seats_used=seats_used,
        seats_limit=seat_limit,
        seats_percentage=round(seats_percentage, 1),
        period_start=period_start,
        period_end=period_end,
    )
