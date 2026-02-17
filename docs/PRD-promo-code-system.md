# PRD: Promo Code System for Outreach

**Status**: Draft
**Created**: 2026-02-17
**Author**: Ali
**Related**: [OUTREACH-TRACKING.md](../OUTREACH-TRACKING.md)

---

## 1. Problem

We're starting LinkedIn outreach to acquire our first 10 signups. Our key incentive is "3 months free Pro plan." Currently, there's no way to:
- Create and manage the promo code in Stripe
- Auto-apply the promo when prospects land on a signup link
- Track which users came from outreach

Without this, our outreach DMs have no working call-to-action.

---

## 2. Goal

Enable a frictionless promo-to-signup flow:

```
LinkedIn DM → prospect clicks link → sees "3 months Pro free!" banner →
signs up → redirected to Stripe Checkout (promo auto-applied, $0) →
Pro activated → lands on dashboard
```

After 3 months, user is automatically downgraded to Free (no card charge).

---

## 3. Scope

### 3.1 In Scope

| # | Item | Owner |
|---|------|-------|
| 1 | Create Stripe coupon + promo code `EARLYPRO3` | Admin (Stripe Dashboard/API) |
| 2 | Promo-aware signup page (`/signup?promo=EARLYPRO3`) | Frontend |
| 3 | Store promo code on organization record | Backend |
| 4 | Auto-apply promo at Stripe Checkout | Frontend + Backend |
| 5 | Auto-downgrade to Free after 3 months | Backend (Stripe webhook) |
| 6 | Analytics tracking for promo signups | Frontend + Backend |

### 3.2 Out of Scope

- Manual promo code entry field on signup or billing page
- Multiple promo codes or a promo code management UI
- In-app promo activation (all activation goes through Stripe Checkout)
- Promo codes for plans other than Pro monthly

---

## 4. Detailed Requirements

### 4.1 Stripe Coupon & Promo Code (Admin Task)

**Action**: Create via Stripe Dashboard or API. No code deployment needed.

| Setting | Value |
|---------|-------|
| Coupon type | Percentage off |
| Discount | 100% |
| Duration | Repeating — 3 months |
| Apply to | Pro Monthly price (`STRIPE_PRICE_PRO_MONTHLY`) |
| Promo code | `EARLYPRO3` |
| Max redemptions | 50 |
| Expiration | None (manual control) |
| First-time orders only | Yes |

**Stripe Coupon Config**:
```
- Name: "Early Adopter — 3 Months Free Pro"
- Percent off: 100%
- Duration: repeating, 3 months
- Applies to: Pro Monthly price only
- Promo code: EARLYPRO3
- Max redemptions: 50
- Restrictions: First-time transaction only
```

**Post-promo behavior**: After 3 months, Stripe will attempt to charge the card on file for $29/mo. Since we chose "downgrade to Free" behavior:
- The subscription in Stripe should be created **without** a payment method requirement (handled via `payment_method_collection: 'if_required'` on checkout session)
- When Stripe can't charge after 3 months (no card), the `customer.subscription.deleted` webhook fires
- Our existing webhook handler (`_handle_subscription_deleted`) already downgrades the org to Free

**Alternative approach**: Create the checkout session with `payment_method_collection: 'if_required'`. Since the coupon covers 100% for 3 months, Stripe won't require a card. After 3 free invoices, the 4th invoice at $29 will fail (no card), triggering the subscription deletion flow.

---

### 4.2 Promo-Aware Signup Page

**URL**: `/signup?promo=EARLYPRO3`

**Flow**:

```
1. User lands on /signup?promo=EARLYPRO3
2. Frontend reads `promo` query param
3. Stores promo code in:
   - localStorage (key: `rereflect_promo`)
   - React state
4. Displays promo banner (see UI spec below)
5. User signs up (email or Google — normal flow)
6. After successful signup, frontend stores promo code for checkout
7. User lands on dashboard (normal flow)
8. When user goes to billing and clicks "Upgrade to Pro":
   - Checkout request includes promo code
   - Backend passes promo to Stripe Checkout session
   - Stripe auto-applies the discount
```

**Promo persistence**: Store in `localStorage` so the promo survives page refreshes, the signup form submission, and navigation to billing. Clear after successful checkout or after 7 days (whichever comes first).

**UI — Promo Banner**:

Position: Top of signup page, above the form (both mobile and desktop).

```
┌─────────────────────────────────────────────────┐
│  🎉  You've been invited! 3 months of Pro free  │
│      2,500 feedback/mo · Slack & Intercom ·     │
│      Trends Analytics · Priority Support         │
└─────────────────────────────────────────────────┘
```

Styling:
- Background: `bg-primary/10` with `border border-primary/20` and `rounded-xl`
- Icon: Party popper or Sparkles from Lucide
- Text: Primary heading in `text-foreground font-semibold`, features in `text-muted-foreground text-sm`
- Placement: Between the page title ("Create your account") and the form fields
- Animation: Subtle fade-in on load

**Invalid promo handling**: If `?promo=INVALID_CODE`, don't show the banner. Only show the banner for known valid codes. For now, hardcode `EARLYPRO3` as the only valid code on the frontend. We can make this dynamic later if needed.

---

### 4.3 Backend: Promo Code on Checkout

**Modified endpoint**: `POST /api/v1/billing/checkout`

**Changes**:

1. Add optional `promo_code` field to `CheckoutRequest`:

```python
class CheckoutRequest(BaseModel):
    plan: str
    billing_cycle: str
    success_url: str
    cancel_url: str
    promo_code: Optional[str] = None  # NEW
```

2. Pass promo code to Stripe Checkout session creation. When `promo_code` is provided:
   - Use `discounts` parameter with the promotion code instead of `allow_promotion_codes`
   - Look up the Stripe promotion code ID from the code string
   - Set `payment_method_collection: 'if_required'` so no card is needed when 100% discount applies

```python
# In StripeService.create_checkout_session:
if promo_code:
    # Look up promotion code in Stripe
    promo_codes = stripe.PromotionCode.list(code=promo_code, active=True, limit=1)
    if promo_codes.data:
        session_params["discounts"] = [{"promotion_code": promo_codes.data[0].id}]
        session_params.pop("allow_promotion_codes", None)  # Can't use both
        session_params["payment_method_collection"] = "if_required"
```

3. Store promo code on organization record (for tracking):

```python
# After successful checkout webhook:
org.promo_code_used = promo_code  # New nullable column
```

---

### 4.4 Backend: Organization Promo Tracking

**Database change**: Add `promo_code_used` column to `organizations` table.

```python
# Alembic migration
# Add nullable string column
promo_code_used = Column(String(50), nullable=True)
```

**When to set**:
- In the `_handle_checkout_completed` webhook handler, extract the promotion code from the Stripe session/subscription data
- Alternatively, pass it from the checkout endpoint and store it before redirecting

---

### 4.5 Analytics Tracking

**Frontend — New Mixpanel events**:

```typescript
// In analytics.ts
promoSignup: (promoCode: string, method: "email" | "google") => {
  trackEvent("Promo Signup", { promo_code: promoCode, method });
},

promoCheckoutStarted: (promoCode: string, plan: string) => {
  trackEvent("Promo Checkout Started", { promo_code: promoCode, plan });
},
```

**When to fire**:
- `Promo Signup`: When user signs up with an active promo in localStorage
- `Promo Checkout Started`: When checkout is initiated with a promo code

**Mixpanel user properties**:
- Set `promo_code: "EARLYPRO3"` on the user profile via `mixpanel.people.set()` at signup time

**Backend tracking**:
- The `promo_code_used` column on organizations serves as the source of truth
- Can query directly: "How many orgs used EARLYPRO3?" → `SELECT COUNT(*) FROM organizations WHERE promo_code_used = 'EARLYPRO3'`

---

### 4.6 Auto-Downgrade After 3 Months

**No new code needed.** The existing flow handles this:

1. Stripe creates subscription with 100% off for 3 months
2. After 3 months, Stripe tries to charge $29/mo
3. No payment method on file → invoice fails → `invoice.payment_failed` webhook fires
4. After Stripe's retry attempts fail → `customer.subscription.deleted` webhook fires
5. Existing `_handle_subscription_deleted` handler sets `org.plan = "free"` and `subscription.status = "canceled"`

**Verification needed**: Confirm Stripe's retry behavior with no payment method. It should fail immediately (no card) and delete the subscription after the dunning period. We may want to set Stripe's dunning settings to fail fast (1 retry, then cancel).

---

## 5. User Flow (End-to-End)

```
1. Ali sends LinkedIn DM with link: app.rereflect.ca/signup?promo=EARLYPRO3

2. Prospect clicks link
   → Lands on /signup?promo=EARLYPRO3
   → Sees banner: "You've been invited! 3 months of Pro free"
   → Promo stored in localStorage

3. Prospect signs up (email or Google)
   → Mixpanel: "Promo Signup" event fires
   → Redirect to /dashboard
   → User is on Free plan initially

4. Prospect navigates to Settings → Billing
   → Sees "Upgrade to Pro" button
   → OR: Show a persistent banner on dashboard: "Activate your 3 months free Pro →"
   → Clicks upgrade

5. Frontend sends checkout request WITH promo_code from localStorage
   → Backend creates Stripe Checkout session with promotion code pre-applied
   → No card required (payment_method_collection: if_required)

6. Prospect completes Stripe Checkout ($0.00)
   → Mixpanel: "Promo Checkout Started" event
   → Redirect to /settings/billing?success=true
   → Subscription synced: plan=pro, status=active

7. Prospect uses Pro for 3 months (free)

8. Month 4: Stripe invoice for $29 fails (no card)
   → Subscription canceled via webhook
   → Org downgraded to Free
   → User can upgrade with card if they want to continue
```

---

## 6. Activation Prompt (Important for Conversion)

After signup via promo link, the user lands on Free plan. They need to go through Stripe Checkout to activate Pro. We should make this obvious:

**Option A — Dashboard banner** (recommended):
Show a dismissible banner at the top of the dashboard for users with a stored promo code who haven't activated Pro yet:

```
┌─────────────────────────────────────────────────────────────┐
│  🎁 You have 3 months of Pro waiting! Activate now →        │
│     Get 2,500 feedback/mo, Slack integration, and more.     │
│                                    [Activate Pro]  [Later]  │
└─────────────────────────────────────────────────────────────┘
```

Clicking "Activate Pro" triggers the checkout flow with promo auto-applied.

**Show condition**: `localStorage.rereflect_promo` exists AND org plan is "free"
**Hide condition**: User clicks "Later" (set `localStorage.rereflect_promo_dismissed = true`) OR org plan becomes "pro"

---

## 7. Files to Modify

### Frontend (`services/frontend-web/`)

| File | Change |
|------|--------|
| `app/signup/page.tsx` | Read `?promo` param, store in localStorage, show promo banner |
| `app/(dashboard)/dashboard/page.tsx` | Show activation banner if promo stored + plan is free |
| `app/(dashboard)/settings/billing/page.tsx` | Pass promo code from localStorage to checkout request |
| `lib/api/billing.ts` | Add `promo_code` field to checkout request type |
| `lib/analytics.ts` | Add `promoSignup` and `promoCheckoutStarted` events |

### Backend (`services/backend-api/`)

| File | Change |
|------|--------|
| `src/api/routes/billing.py` | Add `promo_code` to `CheckoutRequest`, pass to Stripe |
| `src/services/stripe_service.py` | Handle `promo_code` in `create_checkout_session` — look up promotion code, set `payment_method_collection` |
| `src/models/organization.py` | Add `promo_code_used` column |
| `alembic/versions/xxx_add_promo_code.py` | Migration for new column |

### Stripe (Admin — no code deploy)

| Action | Detail |
|--------|--------|
| Create coupon | 100% off, repeating 3 months, apply to Pro Monthly |
| Create promotion code | `EARLYPRO3`, 50 max redemptions, first-time only |
| Review dunning settings | Set to fail fast when no payment method (1 retry → cancel) |

---

## 8. Acceptance Criteria

- [ ] `EARLYPRO3` promo code exists in Stripe with correct config (100% off, 3 months, 50 max, Pro Monthly only)
- [ ] `/signup?promo=EARLYPRO3` shows promo banner with "3 months Pro free" messaging
- [ ] `/signup?promo=INVALID` shows normal signup page (no banner)
- [ ] Promo code persists in localStorage across page navigation and signup
- [ ] After signup with promo, dashboard shows activation banner
- [ ] Clicking "Activate Pro" on dashboard opens Stripe Checkout with promo auto-applied
- [ ] Stripe Checkout shows $0.00 total, no card required
- [ ] After checkout, org plan is updated to "pro"
- [ ] `promo_code_used` is stored on the organization record
- [ ] Mixpanel receives `Promo Signup` event with promo_code property
- [ ] Mixpanel receives `Promo Checkout Started` event
- [ ] Mixpanel user profile includes `promo_code` property
- [ ] After 3 months, subscription is canceled and org downgrades to Free (verify with Stripe test clock)
- [ ] Promo banner on dashboard hides after Pro is activated
- [ ] localStorage promo is cleared after successful checkout

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Promo code shared publicly, drains 50 redemptions | Lose control of offer | Monitor usage in Stripe; can deactivate and create new code |
| User creates multiple accounts with same promo | Inflated signups, no real users | First-time order restriction in Stripe; monitor by email domain |
| Stripe dunning retries for weeks before canceling | User on Pro longer than 3 months free | Configure dunning: 1 retry, then cancel subscription |
| localStorage cleared by user | Promo lost, can't auto-apply at checkout | Promo banner on checkout still lets Stripe's `allow_promotion_codes` work as fallback — but we use `discounts` approach, so this edge case means they'd need to go through normal upgrade without promo |

---

## 10. Future Enhancements (Not in This PRD)

- Admin UI to create/manage promo codes
- Multiple promo codes for different campaigns
- Promo code field on billing settings page
- Automated welcome email when promo is redeemed
- Promo analytics dashboard (redemptions, conversion rate, retention)
