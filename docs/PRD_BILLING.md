# PRD: Stripe Billing Integration

**Document Version**: 1.0
**Created**: 2026-02-01
**Status**: Draft
**Owner**: Product Team

---

## 1. Overview

### 1.1 Problem Statement
Rereflect needs a billing system to monetize the platform and convert free users to paying customers. Without billing, there's no path to revenue.

### 1.2 Goal
Implement Stripe-based billing with tiered pricing, usage tracking, and self-service subscription management to achieve $500 MRR by end of Month 3.

### 1.3 Success Metrics
- 10 paying customers within 4 weeks of launch
- 20%+ trial-to-paid conversion rate
- < 5% monthly churn rate
- Self-service (no manual intervention for 95% of subscriptions)

---

## 2. Pricing Structure

### 2.1 Pricing Tiers

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| **Monthly Price** | $0 | $29 | $99 | Contact Sales |
| **Annual Price** | $0 | $290/yr (~$24/mo) | $990/yr (~$82/mo) | Custom |
| **Annual Discount** | - | 17% (2 months free) | 17% (2 months free) | Negotiated |
| **Team Members** | 2 | 10 | 25 | Unlimited |
| **Feedback/Month** | 250 | 2,500 | 25,000 | Unlimited |
| **Integrations** | CSV Import | + Slack, Webhooks | + All Future | + Custom |
| **Analytics** | Basic Dashboard | + Trends, Export | + API Access, Advanced | + Custom Reports |
| **Support** | Community | Email | Priority Email | Dedicated CSM |
| **Data Retention** | 30 days | 1 year | 2 years | Custom |

### 2.2 Trial Period
- **Duration**: 14 days
- **Credit Card**: Not required
- **Trial Plan**: Full Pro features
- **Post-Trial**: Auto-downgrade to Free (no charge)

### 2.3 Overage Pricing
When users exceed their monthly feedback limit:

| Tier | Included | Overage Rate |
|------|----------|--------------|
| Free | 250 | Hard block (must upgrade) |
| Pro | 2,500 | $0.02 per feedback |
| Business | 25,000 | $0.01 per feedback |
| Enterprise | Unlimited | N/A |

**Overage Behavior**:
- Soft warning at 80% usage
- Email notification at 100%
- Continue accepting feedback, charge overage at end of billing cycle
- Cap overage at 2x plan limit (then hard block until upgrade)

### 2.4 Additional Seats
| Tier | Included | Extra Seat Price |
|------|----------|------------------|
| Free | 2 | N/A (must upgrade) |
| Pro | 10 | $5/seat/month |
| Business | 25 | $4/seat/month |
| Enterprise | Unlimited | Included |

---

## 3. User Flows

### 3.1 New User Signup Flow
```
Landing Page → Signup → Email Verification → Onboarding → Dashboard (Free)
                                                    ↓
                                            Trial Banner: "Start 14-day Pro trial"
                                                    ↓
                                            Click → Instant Pro access (no card)
                                                    ↓
                                            Day 12: Email reminder
                                            Day 14: Trial ends → Downgrade to Free
```

### 3.2 Upgrade Flow
```
Dashboard/Settings → Pricing Page → Select Plan →
    ↓
Monthly/Annual Toggle → Stripe Checkout →
    ↓
Payment Success → Instant Plan Activation →
    ↓
Confirmation Email + Dashboard Update
```

### 3.3 Downgrade Flow
```
Settings → Billing → "Change Plan" → Select Lower Plan →
    ↓
Confirmation Modal (show what they'll lose) →
    ↓
Confirm → Plan changes at end of billing cycle →
    ↓
Email confirmation with end date
```

### 3.4 Cancellation Flow
```
Settings → Billing → "Cancel Subscription" →
    ↓
Exit Survey (Why are you leaving?) →
    ↓
Offer: "Get 30% off for 3 months?" →
    ↓
Accept → Apply discount | Decline → Cancel at period end
    ↓
Access until billing period ends → Downgrade to Free
```

---

## 4. Technical Architecture

### 4.1 Database Schema

```sql
-- Subscription Plans (reference data)
CREATE TABLE subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,           -- 'free', 'pro', 'business'
    stripe_price_id_monthly VARCHAR(100),
    stripe_price_id_annual VARCHAR(100),
    price_monthly INTEGER NOT NULL,       -- cents: 2900 = $29
    price_annual INTEGER NOT NULL,        -- cents: 29000 = $290
    feedback_limit INTEGER NOT NULL,
    seat_limit INTEGER NOT NULL,
    features JSONB NOT NULL,              -- {"api_access": true, "advanced_analytics": true}
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Organization Subscription
ALTER TABLE organizations ADD COLUMN
    stripe_customer_id VARCHAR(100),
    subscription_plan_id INTEGER REFERENCES subscription_plans(id),
    subscription_status VARCHAR(50) DEFAULT 'free',  -- 'free', 'trialing', 'active', 'past_due', 'canceled'
    stripe_subscription_id VARCHAR(100),
    trial_ends_at TIMESTAMP,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancel_at_period_end BOOLEAN DEFAULT false,
    feedback_count_this_period INTEGER DEFAULT 0,
    seat_count INTEGER DEFAULT 1;

-- Usage Tracking
CREATE TABLE usage_records (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    feedback_count INTEGER DEFAULT 0,
    overage_count INTEGER DEFAULT 0,
    overage_charged INTEGER DEFAULT 0,    -- cents
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, period_start)
);

-- Billing Events (audit log)
CREATE TABLE billing_events (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id),
    event_type VARCHAR(50) NOT NULL,      -- 'subscription_created', 'payment_succeeded', etc.
    stripe_event_id VARCHAR(100),
    data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 Backend API Endpoints

```
# Subscription Management
GET    /api/v1/billing/plans              # List available plans
GET    /api/v1/billing/subscription       # Get current subscription
POST   /api/v1/billing/checkout           # Create Stripe checkout session
POST   /api/v1/billing/portal             # Create Stripe billing portal session
POST   /api/v1/billing/start-trial        # Start 14-day Pro trial

# Usage
GET    /api/v1/billing/usage              # Get current period usage
GET    /api/v1/billing/invoices           # List past invoices

# Webhooks (Stripe → Backend)
POST   /api/v1/webhooks/stripe            # Handle Stripe webhook events
```

### 4.3 Stripe Webhook Events to Handle

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Activate subscription, update org |
| `customer.subscription.created` | Log event, send welcome email |
| `customer.subscription.updated` | Update plan, handle upgrades/downgrades |
| `customer.subscription.deleted` | Downgrade to Free, send email |
| `invoice.paid` | Log payment, reset usage counter |
| `invoice.payment_failed` | Mark past_due, send email, retry |
| `customer.subscription.trial_will_end` | Send reminder email (3 days before) |

### 4.4 Frontend Pages

| Page | Route | Purpose |
|------|-------|---------|
| Pricing Page | `/pricing` | Show plans, feature comparison |
| Billing Settings | `/settings/billing` | Current plan, usage, manage |
| Checkout Success | `/checkout/success` | Post-payment confirmation |
| Checkout Cancel | `/checkout/cancel` | Payment canceled handler |

---

## 5. Feature Gating

### 5.1 Backend Middleware
```python
def require_plan(minimum_plan: str):
    """Decorator to gate endpoints by plan level"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            org = get_current_org()
            if not has_plan_access(org, minimum_plan):
                raise HTTPException(403, "Upgrade required")
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage
@router.get("/api/v1/analytics/export")
@require_plan("pro")
async def export_analytics():
    ...
```

### 5.2 Frontend Gating
```typescript
// Hook to check feature access
function useFeatureAccess(feature: string): boolean {
  const { subscription } = useAuth();
  return checkFeatureAccess(subscription.plan, feature);
}

// Component usage
function ExportButton() {
  const canExport = useFeatureAccess('export');

  if (!canExport) {
    return <UpgradePrompt feature="export" />;
  }

  return <Button onClick={handleExport}>Export</Button>;
}
```

### 5.3 Feature Access Matrix

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Dashboard | ✓ | ✓ | ✓ | ✓ |
| CSV Import | ✓ | ✓ | ✓ | ✓ |
| Slack Integration | - | ✓ | ✓ | ✓ |
| Webhooks | - | ✓ | ✓ | ✓ |
| Data Export | - | ✓ | ✓ | ✓ |
| API Access | - | - | ✓ | ✓ |
| Advanced Analytics | - | - | ✓ | ✓ |
| Custom Integrations | - | - | - | ✓ |
| SSO/SAML | - | - | - | ✓ |
| Dedicated Support | - | - | - | ✓ |

---

## 6. UI/UX Specifications

### 6.1 Pricing Page Layout
```
┌────────────────────────────────────────────────────────────────┐
│                    Choose Your Plan                             │
│            [Monthly] [Annual - Save 17%]                        │
├────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │   FREE   │  │   PRO    │  │ BUSINESS │  │ENTERPRISE│       │
│  │          │  │ Popular  │  │          │  │          │       │
│  │    $0    │  │   $29    │  │   $99    │  │ Contact  │       │
│  │  /month  │  │  /month  │  │  /month  │  │  Sales   │       │
│  │          │  │          │  │          │  │          │       │
│  │ 2 users  │  │ 10 users │  │ 25 users │  │Unlimited │       │
│  │ 250 fb   │  │ 2.5K fb  │  │ 25K fb   │  │Unlimited │       │
│  │          │  │          │  │          │  │          │       │
│  │ [Current]│  │[Upgrade] │  │[Upgrade] │  │[Contact] │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
├────────────────────────────────────────────────────────────────┤
│                   Feature Comparison Table                      │
│  ... detailed feature matrix ...                                │
└────────────────────────────────────────────────────────────────┘
```

### 6.2 Usage Dashboard Widget
```
┌─────────────────────────────────────┐
│  Usage This Month                   │
│  ━━━━━━━━━━━━━━━━━━━━░░░░ 75%      │
│  1,875 / 2,500 feedback items       │
│                                     │
│  Team Members: 4 / 10               │
│                                     │
│  Resets in 12 days                  │
└─────────────────────────────────────┘
```

### 6.3 Upgrade Prompt Modal
```
┌─────────────────────────────────────┐
│  ⬆️  Upgrade to unlock              │
│                                     │
│  "API Access" requires Business     │
│                                     │
│  Get 25,000 feedback/month,         │
│  25 team members, and API access    │
│                                     │
│  [See Plans]  [Maybe Later]         │
└─────────────────────────────────────┘
```

---

## 7. Implementation Plan

### Phase 1: Core Billing (Week 1)
- [ ] Set up Stripe account and products
- [ ] Create database migrations
- [ ] Implement subscription model
- [ ] Build checkout flow (Stripe Checkout)
- [ ] Handle webhook events
- [ ] Add billing settings page

### Phase 2: Usage Tracking (Week 1-2)
- [ ] Track feedback count per billing period
- [ ] Implement usage limits
- [ ] Add overage calculation
- [ ] Usage dashboard widget

### Phase 3: Feature Gating (Week 2)
- [ ] Backend plan-check middleware
- [ ] Frontend feature access hooks
- [ ] Upgrade prompts for gated features
- [ ] Trial flow implementation

### Phase 4: Polish (Week 2)
- [ ] Pricing page design
- [ ] Email templates (trial ending, payment failed, etc.)
- [ ] Billing portal integration
- [ ] Testing all flows end-to-end

---

## 8. Stripe Configuration

### 8.1 Products to Create in Stripe
```
Product: Rereflect Pro
  - Price: $29/month (price_pro_monthly)
  - Price: $290/year (price_pro_annual)

Product: Rereflect Business
  - Price: $99/month (price_business_monthly)
  - Price: $990/year (price_business_annual)

Product: Additional Seat - Pro
  - Price: $5/month/seat (price_seat_pro)

Product: Additional Seat - Business
  - Price: $4/month/seat (price_seat_business)

Product: Feedback Overage - Pro
  - Price: $0.02/unit (price_overage_pro)

Product: Feedback Overage - Business
  - Price: $0.01/unit (price_overage_business)
```

### 8.2 Webhook Endpoint
```
URL: https://api.rereflect.ca/api/v1/webhooks/stripe
Events:
  - checkout.session.completed
  - customer.subscription.created
  - customer.subscription.updated
  - customer.subscription.deleted
  - invoice.paid
  - invoice.payment_failed
  - customer.subscription.trial_will_end
```

---

## 9. Security Considerations

- Store Stripe API keys in environment variables only
- Verify webhook signatures using Stripe's signing secret
- Never log or store full card numbers
- Use Stripe Checkout (PCI compliant hosted page)
- Implement idempotency for webhook handlers
- Rate limit billing endpoints

---

## 10. Testing Checklist

- [ ] New user signup → start trial → use Pro features
- [ ] Trial expiration → downgrade to Free
- [ ] Upgrade from Free to Pro (monthly)
- [ ] Upgrade from Pro to Business (annual)
- [ ] Downgrade from Business to Pro
- [ ] Cancel subscription → access until period end
- [ ] Payment failure → retry → success
- [ ] Payment failure → retry → permanent fail
- [ ] Usage limit reached → overage charged
- [ ] Add team member (within limit)
- [ ] Add team member (over limit, pay per seat)
- [ ] Webhook replay/duplicate handling

---

## 11. Open Questions

1. **Refund Policy**: Full refund within 7 days? Pro-rated?
2. **Pause Subscription**: Allow users to pause instead of cancel?
3. **Enterprise Minimum**: Minimum contract value for Enterprise?
4. **Currency**: USD only or multi-currency?

---

## Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-02-01 | Initial PRD | Product Team |
