"""
Billing API routes for subscription management and usage tracking.

SELF-HOSTED OSS NOTE (B3):
Stripe-only routes have been removed:
  - POST /checkout
  - POST /portal
  - GET  /invoices
  - POST /sync-subscription
  - POST /webhooks/stripe

Kept (Stripe-free, useful for self-hosted):
  - GET  /plans         — plan comparison / info
  - GET  /subscription  — shows "self-hosted / active" subscription
  - POST /start-trial   — internal trial state (non-Stripe)
  - GET  /usage         — feedback and seat usage counters

The `stripe_service` import is retained so the module compiles whether or not
the `stripe` package is installed (stripe_service itself is now import-guarded).
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.organization import Organization
from src.models.subscription import Subscription
from src.models.usage import UsageRecord
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org
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


class SubscriptionData(BaseModel):
    id: Optional[int] = None
    plan: str
    status: str
    billing_cycle: Optional[str]
    is_trial: bool
    trial_days_remaining: Optional[int]
    trial_end: Optional[datetime] = None
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    canceled_at: Optional[datetime] = None
    stripe_subscription_id: Optional[str] = None


class SubscriptionResponse(BaseModel):
    subscription: SubscriptionData
    can_manage_billing: bool


class TrialResponse(BaseModel):
    message: str
    subscription: SubscriptionData


class UsageResponse(BaseModel):
    feedback_used: int
    feedback_limit: Optional[int]
    feedback_percentage: float
    seats_used: int
    seats_limit: Optional[int]
    seats_percentage: float
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    overage_enabled: bool
    overage_count: int


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
# Subscription Endpoints
# ============================================================================

@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get current organization's subscription status."""
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == current_org.id
    ).first()

    if not subscription:
        # Return free plan info if no subscription exists
        return SubscriptionResponse(
            subscription=SubscriptionData(
                id=None,
                plan="free",
                status="active",
                billing_cycle=None,
                is_trial=False,
                trial_days_remaining=None,
                trial_end=None,
                current_period_start=None,
                current_period_end=None,
                cancel_at_period_end=False,
                canceled_at=None,
                stripe_subscription_id=None,
            ),
            can_manage_billing=False,
        )

    return SubscriptionResponse(
        subscription=SubscriptionData(
            id=subscription.id,
            plan=subscription.plan,
            status=subscription.status,
            billing_cycle=subscription.billing_cycle,
            is_trial=subscription.is_trial,
            trial_days_remaining=subscription.trial_days_remaining,
            trial_end=subscription.trial_end,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            canceled_at=subscription.canceled_at,
            stripe_subscription_id=subscription.stripe_subscription_id,
        ),
        can_manage_billing=False,  # Stripe billing not available in self-hosted mode
    )


@router.post("/start-trial", response_model=TrialResponse)
def start_trial(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Start a 14-day Pro trial for the organization."""
    # Check if already has an active subscription or trial
    existing = db.query(Subscription).filter(
        Subscription.organization_id == current_org.id
    ).first()

    if existing:
        if existing.status == "trialing":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization is already on a trial"
            )
        if existing.plan != "free":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization already has an active subscription"
            )

    # Create or update subscription with trial
    now = datetime.utcnow()
    trial_end = now + timedelta(days=14)

    if existing:
        existing.plan = "pro"
        existing.status = "trialing"
        existing.trial_start = now
        existing.trial_end = trial_end
        existing.current_period_start = now
        existing.current_period_end = trial_end
        subscription = existing
    else:
        subscription = Subscription(
            organization_id=current_org.id,
            plan="pro",
            status="trialing",
            trial_start=now,
            trial_end=trial_end,
            current_period_start=now,
            current_period_end=trial_end,
        )
        db.add(subscription)

    # Update organization plan
    current_org.plan = "pro"

    db.commit()
    db.refresh(subscription)

    return TrialResponse(
        message="Trial started successfully",
        subscription=SubscriptionData(
            id=subscription.id,
            plan=subscription.plan,
            status=subscription.status,
            billing_cycle=subscription.billing_cycle,
            is_trial=subscription.is_trial,
            trial_days_remaining=subscription.trial_days_remaining,
            trial_end=subscription.trial_end,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            canceled_at=subscription.canceled_at,
            stripe_subscription_id=subscription.stripe_subscription_id,
        ),
    )


# ============================================================================
# Usage Endpoints
# ============================================================================

@router.get("/usage", response_model=UsageResponse)
def get_usage(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get current usage for the billing period."""
    from src.models.feedback import FeedbackItem

    # Get subscription
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == current_org.id
    ).first()

    # Determine billing period
    if subscription and subscription.current_period_start:
        period_start = subscription.current_period_start
        period_end = subscription.current_period_end
    else:
        # Default to current month for free plans
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)

    # Get or create usage record
    usage = db.query(UsageRecord).filter(
        UsageRecord.organization_id == current_org.id,
        UsageRecord.period_start == period_start,
    ).first()

    if not usage:
        # Count feedback for this period
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
    plan_config = get_plan(plan)

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
        overage_enabled=plan_config.get("overage_enabled", False),
        overage_count=usage.overage_feedback,
    )
