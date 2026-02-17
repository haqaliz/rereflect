# PRD: Admin Promo Code Management

**Status**: Draft
**Created**: 2026-02-17
**Author**: Ali
**Depends on**: [PRD-promo-code-system.md](PRD-promo-code-system.md)

---

## 1. Problem

Creating and managing Stripe promo codes currently requires direct access to the Stripe Dashboard. As a system admin, I need to create, view, and manage promo codes from within the Rereflect app — starting with creating the `EARLYPRO3` code for outreach.

---

## 2. Goal

Build an admin page at `/system/promo-codes` (visible only to system admins) that provides full CRUD for Stripe coupons and promotion codes, with pre-built templates for common promotions and flexible custom options.

---

## 3. Existing Infrastructure

The app already has everything needed to support this:

| What | Where | Details |
|------|-------|---------|
| `is_system_admin` flag | `User.is_system_admin` column | Boolean, set on support@rereflect.ca |
| `require_system_admin` dep | `src/api/dependencies.py:273` | Raises 403 if not system admin |
| System sidebar section | `AppSidebar.tsx:243` | Shows when `user?.is_system_admin`, currently has Changelog |
| Existing admin pattern | `/system/changelog/` | Full CRUD admin page to follow as pattern |
| Stripe service | `src/services/stripe_service.py` | Already initialized with Stripe API key |

---

## 4. Scope

### 4.1 In Scope

| # | Item | Layer |
|---|------|-------|
| 1 | Admin API: List promo codes (from Stripe) | Backend |
| 2 | Admin API: Create coupon + promo code | Backend |
| 3 | Admin API: View promo code details + redemption stats | Backend |
| 4 | Admin API: Deactivate promo code | Backend |
| 5 | Admin API: Delete promo code | Backend |
| 6 | Admin page UI: `/system/promo-codes` | Frontend |
| 7 | Sidebar nav: Add "Promo Codes" link under System section | Frontend |
| 8 | Pre-built promo templates (quick-create) | Frontend + Backend |

### 4.2 Out of Scope

- Editing existing coupon parameters (Stripe doesn't support modifying coupons — create new instead)
- Customer-facing promo code entry (handled by PRD-promo-code-system)
- Promo code analytics dashboard (future enhancement)
- Bulk promo code creation

---

## 5. Detailed Requirements

### 5.1 Backend: Admin Promo API

**New file**: `services/backend-api/src/api/routes/admin_promo.py`

**Router**: `APIRouter(prefix="/api/v1/admin/promo-codes", tags=["admin-promo"])`

**All endpoints require**: `Depends(require_system_admin)`

#### Endpoints

**GET `/api/v1/admin/promo-codes`** — List all promotion codes

```python
# Response
class PromoCodeListResponse(BaseModel):
    promo_codes: list[PromoCodeResponse]
    total: int

class PromoCodeResponse(BaseModel):
    id: str                        # Stripe promo code ID
    code: str                      # e.g., "EARLYPRO3"
    active: bool
    coupon: CouponSummary
    max_redemptions: int | None
    times_redeemed: int
    expires_at: datetime | None
    created: datetime
    metadata: dict | None

class CouponSummary(BaseModel):
    id: str
    name: str | None
    percent_off: float | None
    amount_off: int | None         # cents
    currency: str | None
    duration: str                  # once, repeating, forever
    duration_in_months: int | None
```

Implementation: `stripe.PromotionCode.list(limit=50, expand=["data.coupon"])`

---

**GET `/api/v1/admin/promo-codes/{promo_code_id}`** — Get promo code details

```python
# Response: PromoCodeDetailResponse
class PromoCodeDetailResponse(PromoCodeResponse):
    # Additional fields from Stripe
    customer: str | None           # If restricted to a customer
    first_time_transaction: bool
    minimum_amount: int | None
    minimum_amount_currency: str | None
    # Redemption info from our database
    redeemed_by: list[PromoRedemption]

class PromoRedemption(BaseModel):
    organization_id: int
    organization_name: str
    redeemed_at: datetime | None
```

Implementation:
- `stripe.PromotionCode.retrieve(promo_code_id, expand=["coupon"])`
- Query local DB: `SELECT o.id, o.name, o.created_at FROM organizations WHERE promo_code_used = <code>`

---

**POST `/api/v1/admin/promo-codes`** — Create coupon + promo code

```python
class CreatePromoRequest(BaseModel):
    # Promo code
    code: str                               # e.g., "EARLYPRO3"
    max_redemptions: int | None = None      # None = unlimited
    first_time_transaction: bool = True
    expires_at: datetime | None = None

    # Coupon (created automatically)
    coupon_name: str                        # e.g., "Early Adopter — 3 Months Free Pro"
    discount_type: str                      # "percent" or "amount"
    percent_off: float | None = None        # 1-100
    amount_off: int | None = None           # cents
    currency: str = "usd"
    duration: str                           # "once", "repeating", "forever"
    duration_in_months: int | None = None   # Required if duration = "repeating"
    applies_to_prices: list[str] | None = None  # Stripe price IDs, None = all prices
```

Implementation:
1. Create Stripe Coupon: `stripe.Coupon.create(...)`
2. Create Stripe PromotionCode: `stripe.PromotionCode.create(coupon=coupon.id, code=code, ...)`
3. Return the created PromoCodeResponse

---

**POST `/api/v1/admin/promo-codes/{promo_code_id}/deactivate`** — Deactivate

Implementation: `stripe.PromotionCode.modify(promo_code_id, active=False)`

---

**DELETE `/api/v1/admin/promo-codes/{promo_code_id}`** — Delete promo code

Implementation:
- `stripe.PromotionCode.modify(promo_code_id, active=False)` (can't truly delete promo codes in Stripe)
- Optionally delete the coupon if no other promo codes use it: `stripe.Coupon.delete(coupon_id)`
- Note: Stripe promo codes can't be deleted, only deactivated. The UI should clarify this.

---

#### Pre-built Templates

The create endpoint accepts raw params, but the frontend will offer templates:

| Template | Name | Discount | Duration | Limits |
|----------|------|----------|----------|--------|
| 3 Months Free Pro | "3 Months Free Pro" | 100% off | Repeating, 3 months | First-time only |
| 1 Month Free Pro | "1 Month Free Pro" | 100% off | Repeating, 1 month | First-time only |
| 50% Off 3 Months | "50% Off 3 Months" | 50% off | Repeating, 3 months | First-time only |
| 50% Off First Month | "50% Off First Month" | 50% off | Once | First-time only |
| Custom | User-defined | Any | Any | Any |

Templates are frontend-only — they pre-fill the create form. The API receives the same `CreatePromoRequest` regardless.

---

### 5.2 Backend: Stripe Service Additions

**File**: `services/backend-api/src/services/stripe_service.py`

Add new methods:

```python
def list_promotion_codes(self, limit: int = 50, active: bool | None = None) -> list:
    """List all promotion codes from Stripe."""

def get_promotion_code(self, promo_code_id: str) -> dict | None:
    """Get promotion code details."""

def create_coupon_and_promo(self, coupon_params: dict, promo_params: dict) -> dict:
    """Create a coupon and associated promotion code."""

def deactivate_promotion_code(self, promo_code_id: str) -> bool:
    """Deactivate a promotion code."""

def delete_coupon(self, coupon_id: str) -> bool:
    """Delete a coupon (only if no active promo codes use it)."""
```

---

### 5.3 Frontend: Admin Promo Codes Page

**New file**: `services/frontend-web/app/(dashboard)/system/promo-codes/page.tsx`

**Access**: Only rendered if `user?.is_system_admin` (redirect to `/dashboard` otherwise)

**Layout** (follow existing `/system/changelog` pattern):

```
┌──────────────────────────────────────────────────────────────┐
│  🏷️  Promo Codes                           [+ Create Promo] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Code    │ Discount     │ Duration  │ Used │ Status │ │    │
│  ├─────────┼──────────────┼───────────┼──────┼────────┤ │    │
│  │EARLYPRO3│ 100% off     │ 3 months  │ 2/50 │ Active │ │    │
│  │HALFOFF  │ 50% off      │ 1 month   │ 10   │ Active │ │    │
│  │BETA2026 │ 100% off     │ 1 month   │ 5/20 │Inactive│ │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Table columns**:
- Code (string)
- Discount (e.g., "100% off" or "$10 off")
- Duration (e.g., "3 months", "Once", "Forever")
- Redemptions (e.g., "2/50" or "10/∞")
- Status (Active / Inactive badge)
- Actions: View details, Deactivate, Delete

**Create Promo Dialog** (opened by "+ Create Promo" button):

```
┌─────────────────────────────────────────────────┐
│  Create Promo Code                              │
├─────────────────────────────────────────────────┤
│                                                 │
│  Quick Templates:                               │
│  [3mo Free Pro] [1mo Free Pro] [50% Off] [Custom]│
│                                                 │
│  ── OR customize ──                             │
│                                                 │
│  Promo Code:    [EARLYPRO3          ]           │
│  Coupon Name:   [Early Adopter — 3mo Free Pro]  │
│                                                 │
│  Discount:  ○ Percentage [100]%                 │
│             ○ Fixed amount [$   ]               │
│                                                 │
│  Duration:  ○ Once                              │
│             ○ Repeating [ 3 ] months            │
│             ○ Forever                           │
│                                                 │
│  Max Redemptions: [50  ] (empty = unlimited)    │
│  First-time only: [✓]                           │
│  Expires at:      [    ] (optional)             │
│                                                 │
│  Apply to specific prices: [    ] (optional)    │
│                                                 │
│             [Cancel]  [Create Promo Code]       │
└─────────────────────────────────────────────────┘
```

When a template is clicked, it pre-fills all fields:
- "3mo Free Pro" → code: auto-generated, 100% off, repeating 3 months, first-time only
- The user can modify any pre-filled values before creating

**Detail View** (click on a row or view action):
- Shows all promo code properties
- Shows redemption list (orgs that used this code, from local DB)
- Deactivate / Delete buttons

---

### 5.4 Frontend: Sidebar Navigation

**File**: `services/frontend-web/components/AppSidebar.tsx`

Add "Promo Codes" link in the System section (next to Changelog):

```tsx
{user?.is_system_admin && (
  <>
    <SidebarSeparator />
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={isActive('/system/changelog')} tooltip="Changelog">
              <Link href="/system/changelog"><FileText /><span>Changelog</span></Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {/* NEW */}
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={isActive('/system/promo-codes')} tooltip="Promo Codes">
              <Link href="/system/promo-codes"><Tag /><span>Promo Codes</span></Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  </>
)}
```

---

### 5.5 Frontend: API Client

**New file**: `services/frontend-web/lib/api/admin-promo.ts`

```typescript
export interface PromoCode {
  id: string;
  code: string;
  active: boolean;
  coupon: {
    id: string;
    name: string | null;
    percent_off: number | null;
    amount_off: number | null;
    currency: string | null;
    duration: string;
    duration_in_months: number | null;
  };
  max_redemptions: number | null;
  times_redeemed: number;
  expires_at: string | null;
  created: string;
}

export interface CreatePromoRequest {
  code: string;
  coupon_name: string;
  discount_type: 'percent' | 'amount';
  percent_off?: number;
  amount_off?: number;
  currency?: string;
  duration: 'once' | 'repeating' | 'forever';
  duration_in_months?: number;
  max_redemptions?: number;
  first_time_transaction?: boolean;
  expires_at?: string;
  applies_to_prices?: string[];
}

export const adminPromoAPI = {
  list: () => apiClient.get('/api/v1/admin/promo-codes'),
  get: (id: string) => apiClient.get(`/api/v1/admin/promo-codes/${id}`),
  create: (data: CreatePromoRequest) => apiClient.post('/api/v1/admin/promo-codes', data),
  deactivate: (id: string) => apiClient.post(`/api/v1/admin/promo-codes/${id}/deactivate`),
  delete: (id: string) => apiClient.delete(`/api/v1/admin/promo-codes/${id}`),
};
```

---

## 6. Files to Create / Modify

### Backend (new)
| File | Description |
|------|-------------|
| `src/api/routes/admin_promo.py` | New admin promo code routes (CRUD) |

### Backend (modify)
| File | Change |
|------|--------|
| `src/services/stripe_service.py` | Add promo CRUD methods |
| `src/api/main.py` | Register `admin_promo` router |

### Frontend (new)
| File | Description |
|------|-------------|
| `app/(dashboard)/system/promo-codes/page.tsx` | Admin promo codes page |
| `lib/api/admin-promo.ts` | API client for admin promo endpoints |

### Frontend (modify)
| File | Change |
|------|--------|
| `components/AppSidebar.tsx` | Add "Promo Codes" to System section |

---

## 7. Acceptance Criteria

- [ ] System admin can see "Promo Codes" in the sidebar under System section
- [ ] Non-system-admin users cannot access `/system/promo-codes` (redirect to dashboard)
- [ ] API returns 403 for non-system-admin users on all admin promo endpoints
- [ ] System admin can create a promo code using a quick template (e.g., "3 Months Free Pro")
- [ ] System admin can create a custom promo code with flexible discount/duration
- [ ] Table lists all promo codes with code, discount, duration, redemptions, status
- [ ] System admin can view promo code details including which orgs redeemed it
- [ ] System admin can deactivate an active promo code
- [ ] System admin can delete a promo code (deactivates in Stripe + deletes coupon if unused)
- [ ] Creating EARLYPRO3 (100% off, 3 months, 50 max, first-time only) works end-to-end
- [ ] Created promo code is usable at Stripe Checkout (verified with the promo signup flow from PRD-promo-code-system)

---

## 8. First Action After Build

Create the `EARLYPRO3` promo code via the new admin UI:
- Template: "3 Months Free Pro"
- Code: `EARLYPRO3`
- Max redemptions: 50
- First-time transaction only: Yes
- Coupon name: "Early Adopter — 3 Months Free Pro"
