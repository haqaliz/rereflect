"""
Billing API routes for subscription management, usage tracking, and Stripe integration.
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.organization import Organization
from src.models.subscription import Subscription
from src.models.usage import UsageRecord
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org
from src.config.plans import PLANS, get_plan, get_feedback_limit, get_seat_limit
from src.services.stripe_service import get_stripe_service


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


class InvoicesListResponse(BaseModel):
    invoices: list["InvoiceResponse"]


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


class CheckoutRequest(BaseModel):
    plan: str  # pro, business
    billing_cycle: str  # monthly, annual
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_url: str


class PortalResponse(BaseModel):
    portal_url: str


class InvoiceResponse(BaseModel):
    id: str
    number: Optional[str]
    amount_due: int
    amount_paid: int
    currency: str
    status: str
    created: datetime
    due_date: Optional[datetime]
    paid_at: Optional[datetime]
    hosted_invoice_url: Optional[str]
    invoice_pdf: Optional[str]


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
    "slack_integration": "Slack Integration",
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
        can_manage_billing=bool(current_org.stripe_customer_id),
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
# Checkout & Portal Endpoints
# ============================================================================

@router.post("/sync-subscription", response_model=SubscriptionResponse)
def sync_subscription(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """
    Sync subscription status from Stripe.

    Call this after checkout success to immediately update the local subscription
    without waiting for webhooks. This is especially useful for local development.
    """
    if not current_org.stripe_customer_id:
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

    stripe_service = get_stripe_service()

    # Get subscriptions from Stripe for this customer
    import stripe
    stripe.api_key = stripe_service.api_key

    try:
        subscriptions = stripe.Subscription.list(
            customer=current_org.stripe_customer_id,
            status="all",
            limit=1,
        )
    except stripe.error.StripeError:
        # Return current subscription from DB if Stripe fails
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == current_org.id
        ).first()

        if not subscription:
            return SubscriptionResponse(
                subscription=SubscriptionData(
                    id=None,
                    plan=current_org.plan or "free",
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
                can_manage_billing=True,
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
            can_manage_billing=True,
        )

    if not subscriptions.data:
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
            can_manage_billing=True,
        )

    # Get the most recent active subscription
    stripe_sub = subscriptions.data[0]

    # Determine plan from price ID
    price_id = stripe_sub["items"]["data"][0]["price"]["id"] if stripe_sub["items"]["data"] else None
    plan = _get_plan_from_price_id(price_id) if price_id else "free"
    billing_cycle = _get_billing_cycle_from_price_id(price_id) if price_id else None

    # Update or create local subscription record
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == current_org.id
    ).first()

    if subscription:
        subscription.stripe_subscription_id = stripe_sub.id
        subscription.stripe_price_id = price_id
        subscription.plan = plan
        subscription.billing_cycle = billing_cycle
        subscription.status = stripe_sub.status
        subscription.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
        subscription.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
        subscription.cancel_at_period_end = stripe_sub.cancel_at_period_end
        subscription.canceled_at = datetime.fromtimestamp(stripe_sub.canceled_at) if stripe_sub.canceled_at else None
        subscription.trial_start = datetime.fromtimestamp(stripe_sub.trial_start) if stripe_sub.trial_start else None
        subscription.trial_end = datetime.fromtimestamp(stripe_sub.trial_end) if stripe_sub.trial_end else None
    else:
        subscription = Subscription(
            organization_id=current_org.id,
            stripe_subscription_id=stripe_sub.id,
            stripe_price_id=price_id,
            plan=plan,
            billing_cycle=billing_cycle,
            status=stripe_sub.status,
            current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end),
            cancel_at_period_end=stripe_sub.cancel_at_period_end,
            canceled_at=datetime.fromtimestamp(stripe_sub.canceled_at) if stripe_sub.canceled_at else None,
            trial_start=datetime.fromtimestamp(stripe_sub.trial_start) if stripe_sub.trial_start else None,
            trial_end=datetime.fromtimestamp(stripe_sub.trial_end) if stripe_sub.trial_end else None,
        )
        db.add(subscription)

    # Update organization plan
    current_org.plan = plan

    db.commit()
    db.refresh(subscription)

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
        can_manage_billing=True,
    )


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Create a Stripe Checkout session for subscription."""
    # Validate plan
    if request.plan not in ["pro", "business"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan. Must be 'pro' or 'business'"
        )

    # Validate billing cycle
    if request.billing_cycle not in ["monthly", "annual"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid billing cycle. Must be 'monthly' or 'annual'"
        )

    stripe_service = get_stripe_service()

    # Ensure organization has a Stripe customer
    if not current_org.stripe_customer_id:
        customer_id = stripe_service.create_customer(
            email=current_user.email,
            name=current_org.name,
            organization_id=current_org.id,
        )
        current_org.stripe_customer_id = customer_id
        db.commit()
    else:
        customer_id = current_org.stripe_customer_id

    # Check if org is on trial - we'll convert to paid
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == current_org.id
    ).first()

    trial_days = None
    if not subscription or subscription.plan == "free":
        # New subscriber, no trial from checkout (they can use start-trial first)
        pass

    # Create checkout session
    try:
        checkout_url = stripe_service.create_checkout_session(
            customer_id=customer_id,
            plan=request.plan,
            billing_cycle=request.billing_cycle,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            trial_days=trial_days,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/portal", response_model=PortalResponse)
def create_portal(
    request: PortalRequest,
    current_org: Organization = Depends(get_current_org),
):
    """Create a Stripe Customer Portal session."""
    if not current_org.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization has no billing account. Please subscribe first."
        )

    stripe_service = get_stripe_service()
    portal_url = stripe_service.create_portal_session(
        customer_id=current_org.stripe_customer_id,
        return_url=request.return_url,
    )

    return PortalResponse(portal_url=portal_url)


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


# ============================================================================
# Invoice Endpoints
# ============================================================================

@router.get("/invoices", response_model=InvoicesListResponse)
def get_invoices(
    current_org: Organization = Depends(get_current_org),
    limit: int = 10,
):
    """Get invoice history for the organization."""
    if not current_org.stripe_customer_id:
        return InvoicesListResponse(invoices=[])

    stripe_service = get_stripe_service()
    invoices = stripe_service.get_invoices(
        customer_id=current_org.stripe_customer_id,
        limit=min(limit, 100),
    )

    return InvoicesListResponse(invoices=[
        InvoiceResponse(
            id=inv["id"],
            number=inv["number"],
            amount_due=inv["amount_due"],
            amount_paid=inv["amount_paid"],
            currency=inv["currency"],
            status=inv["status"],
            created=inv["created"],
            due_date=inv["due_date"],
            paid_at=inv["paid_at"],
            hosted_invoice_url=inv["hosted_invoice_url"],
            invoice_pdf=inv["invoice_pdf"],
        )
        for inv in invoices
    ])


# ============================================================================
# Webhook Endpoints
# ============================================================================

@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    stripe_service = get_stripe_service()
    event = stripe_service.verify_webhook_signature(payload, sig_header)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature"
        )

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    # Route to appropriate handler
    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.created": _handle_subscription_created,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.paid": _handle_invoice_paid,
        "invoice.payment_failed": _handle_invoice_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(data, db)

    return {"status": "ok"}


# ============================================================================
# Webhook Handlers
# ============================================================================

async def _handle_checkout_completed(data: dict, db: Session):
    """Handle successful checkout session."""
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    if not customer_id or not subscription_id:
        return

    # Find organization by Stripe customer ID
    org = db.query(Organization).filter(
        Organization.stripe_customer_id == customer_id
    ).first()

    if not org:
        return

    # Get subscription details from Stripe
    stripe_service = get_stripe_service()
    stripe_sub = stripe_service.get_subscription(subscription_id)

    if not stripe_sub:
        return

    # Determine plan from price ID
    price_id = stripe_sub.get("price_id")
    plan = _get_plan_from_price_id(price_id)
    billing_cycle = _get_billing_cycle_from_price_id(price_id)

    # Update or create subscription record
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == org.id
    ).first()

    if subscription:
        subscription.stripe_subscription_id = subscription_id
        subscription.stripe_price_id = price_id
        subscription.plan = plan
        subscription.billing_cycle = billing_cycle
        subscription.status = stripe_sub["status"]
        subscription.current_period_start = stripe_sub["current_period_start"]
        subscription.current_period_end = stripe_sub["current_period_end"]
        subscription.trial_start = stripe_sub.get("trial_start")
        subscription.trial_end = stripe_sub.get("trial_end")
    else:
        subscription = Subscription(
            organization_id=org.id,
            stripe_subscription_id=subscription_id,
            stripe_price_id=price_id,
            plan=plan,
            billing_cycle=billing_cycle,
            status=stripe_sub["status"],
            current_period_start=stripe_sub["current_period_start"],
            current_period_end=stripe_sub["current_period_end"],
            trial_start=stripe_sub.get("trial_start"),
            trial_end=stripe_sub.get("trial_end"),
        )
        db.add(subscription)

    # Update organization plan
    org.plan = plan

    db.commit()


async def _handle_subscription_created(data: dict, db: Session):
    """Handle subscription created event."""
    # Usually handled by checkout.session.completed
    pass


async def _handle_subscription_updated(data: dict, db: Session):
    """Handle subscription update (plan change, cancellation, etc.)."""
    subscription_id = data.get("id")
    customer_id = data.get("customer")

    if not subscription_id or not customer_id:
        return

    org = db.query(Organization).filter(
        Organization.stripe_customer_id == customer_id
    ).first()

    if not org:
        return

    subscription = db.query(Subscription).filter(
        Subscription.organization_id == org.id
    ).first()

    if not subscription:
        return

    # Update subscription fields
    subscription.status = data.get("status", subscription.status)
    subscription.cancel_at_period_end = data.get("cancel_at_period_end", False)

    if data.get("canceled_at"):
        subscription.canceled_at = datetime.fromtimestamp(data["canceled_at"])

    if data.get("current_period_start"):
        subscription.current_period_start = datetime.fromtimestamp(data["current_period_start"])

    if data.get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(data["current_period_end"])

    # Check for plan change
    items = data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")
        if price_id and price_id != subscription.stripe_price_id:
            new_plan = _get_plan_from_price_id(price_id)
            new_cycle = _get_billing_cycle_from_price_id(price_id)
            subscription.plan = new_plan
            subscription.billing_cycle = new_cycle
            subscription.stripe_price_id = price_id
            org.plan = new_plan

    db.commit()


async def _handle_subscription_deleted(data: dict, db: Session):
    """Handle subscription cancellation/deletion."""
    customer_id = data.get("customer")

    if not customer_id:
        return

    org = db.query(Organization).filter(
        Organization.stripe_customer_id == customer_id
    ).first()

    if not org:
        return

    subscription = db.query(Subscription).filter(
        Subscription.organization_id == org.id
    ).first()

    if subscription:
        subscription.status = "canceled"
        subscription.canceled_at = datetime.utcnow()
        subscription.plan = "free"

    # Downgrade organization to free
    org.plan = "free"

    db.commit()


async def _handle_invoice_paid(data: dict, db: Session):
    """Handle successful invoice payment."""
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    if not customer_id:
        return

    org = db.query(Organization).filter(
        Organization.stripe_customer_id == customer_id
    ).first()

    if not org:
        return

    # Reset usage counters for new billing period
    subscription = db.query(Subscription).filter(
        Subscription.organization_id == org.id
    ).first()

    if subscription and subscription.current_period_start:
        # Create new usage record for the new period
        # Old records are kept for history
        pass

    db.commit()


async def _handle_invoice_payment_failed(data: dict, db: Session):
    """Handle failed invoice payment."""
    customer_id = data.get("customer")

    if not customer_id:
        return

    org = db.query(Organization).filter(
        Organization.stripe_customer_id == customer_id
    ).first()

    if not org:
        return

    subscription = db.query(Subscription).filter(
        Subscription.organization_id == org.id
    ).first()

    if subscription:
        subscription.status = "past_due"

    db.commit()


# ============================================================================
# Helper Functions
# ============================================================================

def _get_plan_from_price_id(price_id: str) -> str:
    """Determine plan from Stripe price ID."""
    import os

    price_mappings = {
        os.environ.get("STRIPE_PRICE_PRO_MONTHLY", ""): "pro",
        os.environ.get("STRIPE_PRICE_PRO_ANNUAL", ""): "pro",
        os.environ.get("STRIPE_PRICE_BUSINESS_MONTHLY", ""): "business",
        os.environ.get("STRIPE_PRICE_BUSINESS_ANNUAL", ""): "business",
    }

    return price_mappings.get(price_id, "free")


def _get_billing_cycle_from_price_id(price_id: str) -> str:
    """Determine billing cycle from Stripe price ID."""
    import os

    annual_prices = [
        os.environ.get("STRIPE_PRICE_PRO_ANNUAL", ""),
        os.environ.get("STRIPE_PRICE_BUSINESS_ANNUAL", ""),
    ]

    return "annual" if price_id in annual_prices else "monthly"
