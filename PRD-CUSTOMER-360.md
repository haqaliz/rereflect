# PRD: Customer 360 Page

**Product**: Rereflect
**Author**: Rereflect Team
**Date**: 2026-02-19
**Timeline**: 2 weeks (Feb 20 - Mar 7, 2026)
**Status**: Draft
**Milestone**: AI-TRACKING M1.2

---

## 1. Overview

Build a dedicated Customer 360 experience — a `/customers` list page and `/customers/[email]` profile page — that surfaces all existing customer health data in one place. Today, customer health data is scattered: the dashboard shows only the top 5 at-risk customers, and individual health scores are only visible by opening each feedback item. This feature centralizes all customer intelligence into browsable, filterable, actionable views.

### Current State
- `CustomerHealth` model exists with 4-component weighted scores (churn 35%, sentiment 25%, resolution 25%, frequency 15%)
- Dashboard widget shows top 5 at-risk customers (expandable with LLM analysis)
- Single API endpoint: `GET /api/v1/customer-health/{email}` (Pro+ gated)
- Feedback detail page shows churn risk score and health badge (M1.1, completed)
- Feedbacks list has churn risk column and risk level filter (M1.1, completed)
- No way to browse all customers, see healthy ones, or view per-customer history

### Success Criteria
- Users can browse, search, and filter all customers with health scores
- Users can view a full customer profile with health history, feedbacks, and AI analysis
- Risk distribution is visible at a glance on the list page
- Free plan users see a blurred preview (upgrade CTA), Pro+ gets full access
- Low-confidence scores (few feedbacks) are clearly indicated
- Zero regressions on existing tests

---

## 2. Data Model Changes

### 2.1 CustomerHealth Model Updates

**File**: `services/backend-api/src/models/customer_health.py`

Add fields to support archiving and confidence:

```python
is_archived = Column(Boolean, default=False, server_default="false")  # Soft archive when all feedback deleted
confidence_level = Column(String(20), default="low")  # low (<3 feedbacks), medium (3-9), high (10+)
```

**Confidence Level Rules**:
| Feedback Count | Confidence | Display |
|----------------|------------|---------|
| 1-2 | `low` | "Low confidence" badge with tooltip |
| 3-9 | `medium` | "Medium confidence" badge |
| 10+ | `high` | No badge (default, score is reliable) |

### 2.2 Health Score History Model (NEW)

**File**: `services/backend-api/src/models/customer_health_history.py`
**Table**: `customer_health_history`

Store snapshots of health score changes for the timeline chart:

```python
id = Column(Integer, primary_key=True)
customer_health_id = Column(Integer, ForeignKey("customer_health_scores.id", ondelete="CASCADE"))
organization_id = Column(Integer, ForeignKey("organizations.id"))
health_score = Column(Integer)
churn_risk_component = Column(Integer)
sentiment_component = Column(Integer)
resolution_component = Column(Integer)
frequency_component = Column(Integer)
risk_level = Column(String(20))
recorded_at = Column(DateTime, default=func.now())
```

**Indexes**:
- `ix_health_history_customer_date` — (customer_health_id, recorded_at)
- `ix_health_history_org_date` — (organization_id, recorded_at)

**Population**: Insert a history record every time `update_customer_health()` runs and the `health_score` changes by ≥ 2 points (avoids noise from negligible fluctuations).

### 2.3 Alembic Migration

Single migration adding:
- `is_archived` column on `customer_health_scores`
- `confidence_level` column on `customer_health_scores`
- `customer_health_history` table with indexes

---

## 3. Backend API

### 3.1 Customer List Endpoint

```
GET /api/v1/customers/
```

**Auth**: JWT required
**Plan Gate**: `require_feature("customer_health_scores")` — Pro+
**RBAC**: All roles (Owner/Admin/Member)

**Query Parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page (max 100) |
| `sort_by` | string | `health_score` | Sort field: `health_score`, `feedback_count`, `last_feedback_at`, `customer_email` |
| `sort_order` | string | `asc` | `asc` or `desc` |
| `risk_level` | string | null | Filter: `healthy`, `moderate`, `at_risk`, `critical` |
| `search` | string | null | Contains match (ILIKE) on `customer_email` and `customer_name` |
| `include_archived` | bool | false | Include soft-archived customers |

**Response**:

```json
{
  "items": [
    {
      "customer_email": "john@acme.com",
      "customer_name": "John Doe",
      "health_score": 34,
      "risk_level": "at_risk",
      "confidence_level": "high",
      "feedback_count": 28,
      "last_feedback_at": "2026-02-18T14:30:00Z",
      "sentiment_trend": {
        "direction": "declining",
        "change_percent": -12.5
      },
      "is_archived": false
    }
  ],
  "total": 156,
  "page": 1,
  "page_size": 20,
  "summary": {
    "total_customers": 156,
    "avg_health_score": 62,
    "risk_distribution": {
      "healthy": 89,
      "moderate": 38,
      "at_risk": 22,
      "critical": 7
    }
  }
}
```

**Sentiment Trend Calculation**:
- Compare average `sentiment_score` of feedbacks from last 7 days vs previous 7 days
- `direction`: `"improving"` (> +5%), `"declining"` (< -5%), `"stable"` (within ±5%)
- `change_percent`: percentage change (e.g., -12.5 means 12.5% worse)
- If no feedbacks in either period: `direction: "stable"`, `change_percent: 0`

### 3.2 Customer Profile Endpoint

```
GET /api/v1/customers/{email}
```

**Auth**: JWT required
**Plan Gate**: `require_feature("customer_health_scores")`

**Response**:

```json
{
  "customer_email": "john@acme.com",
  "customer_name": "John Doe",
  "health_score": 34,
  "risk_level": "at_risk",
  "confidence_level": "high",
  "feedback_count": 28,
  "last_feedback_at": "2026-02-18T14:30:00Z",
  "churn_risk_component": 22,
  "sentiment_component": 38,
  "resolution_component": 45,
  "frequency_component": 30,
  "llm_analysis": "Customer shows signs of frustration with...",
  "llm_analyzed_at": "2026-02-17T07:00:00Z",
  "is_archived": false,
  "created_at": "2025-12-01T10:00:00Z"
}
```

### 3.3 Customer Health History Endpoint

```
GET /api/v1/customers/{email}/history
```

**Query Parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days` | int | 30 | Time range: 30, 60, or 90 |

**Response**:

```json
{
  "history": [
    {
      "health_score": 34,
      "churn_risk_component": 22,
      "sentiment_component": 38,
      "resolution_component": 45,
      "frequency_component": 30,
      "risk_level": "at_risk",
      "recorded_at": "2026-02-18T14:30:00Z"
    }
  ],
  "period_start": "2026-01-19T00:00:00Z",
  "period_end": "2026-02-18T23:59:59Z"
}
```

### 3.4 Customer Recent Feedbacks Endpoint

```
GET /api/v1/customers/{email}/feedbacks
```

Returns last 15 feedbacks for a customer (compact, no full pagination).

**Response**:

```json
{
  "feedbacks": [
    {
      "id": 1234,
      "text_snippet": "The billing page keeps crashing when...",
      "sentiment_label": "negative",
      "sentiment_score": -0.72,
      "churn_risk_score": 68,
      "workflow_status": "in_review",
      "created_at": "2026-02-18T14:30:00Z",
      "source": "slack"
    }
  ],
  "total_count": 28,
  "view_all_url": "/feedbacks?customer_email=john@acme.com"
}
```

### 3.5 Customer Recent Activity Endpoint

```
GET /api/v1/customers/{email}/activity
```

Returns last 10 events for the overview timeline.

**Response**:

```json
{
  "events": [
    {
      "type": "feedback_created",
      "description": "New feedback submitted",
      "feedback_id": 1234,
      "timestamp": "2026-02-18T14:30:00Z"
    },
    {
      "type": "status_changed",
      "description": "Feedback #1230 moved to Resolved",
      "feedback_id": 1230,
      "timestamp": "2026-02-17T09:15:00Z"
    },
    {
      "type": "health_score_changed",
      "description": "Health score dropped from 48 to 34",
      "old_score": 48,
      "new_score": 34,
      "timestamp": "2026-02-16T14:00:00Z"
    },
    {
      "type": "llm_analysis_generated",
      "description": "Weekly AI analysis generated",
      "timestamp": "2026-02-17T07:00:00Z"
    }
  ]
}
```

**Event Sources**:
- `feedback_created`: From `feedback_items` WHERE `customer_email = X`, ordered by `created_at`
- `status_changed`: From `feedback_workflow_events` joined with feedback WHERE `customer_email = X`
- `health_score_changed`: From `customer_health_history` table
- `llm_analysis_generated`: From `customer_health_scores.llm_analyzed_at`

### 3.6 On-Demand LLM Analysis Endpoint

```
POST /api/v1/customers/{email}/analyze
```

**Plan Gate**: `require_feature("churn_llm_insights")`

Triggers an on-demand LLM analysis for the customer (reuses existing `CHURN_ANALYSIS_PROMPT` from the weekly job). Queues a Celery task and returns immediately.

**Response**: `202 Accepted`

```json
{
  "message": "Analysis queued",
  "estimated_wait_seconds": 15
}
```

The frontend polls `GET /api/v1/customers/{email}` until `llm_analyzed_at` updates.

### 3.7 Soft Archive / Unarchive

When all feedbacks for a customer are deleted, set `is_archived = True` on the CustomerHealth record. The list endpoint excludes archived customers by default (`include_archived=false`).

**Trigger**: Add a post-deletion check in feedback delete routes — if remaining feedback count for `customer_email` is 0, archive the customer health record.

---

## 4. Frontend — `/customers` List Page

**File**: `services/frontend-web/app/(dashboard)/customers/page.tsx`

### 4.1 Page Layout (top to bottom)

```
┌─────────────────────────────────────────────────────┐
│ Page Header: "Customers"                             │
├─────────────────────────────────────────────────────┤
│ Summary Stat Cards (4)                               │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │
│ │Total   │ │Avg     │ │At Risk │ │Critical│        │
│ │Customers│ │Health  │ │  %     │ │ Count  │        │
│ └────────┘ └────────┘ └────────┘ └────────┘        │
├─────────────────────────────────────────────────────┤
│ Risk Distribution Bar                                │
│ ████████████████░░░░░░░░░▒▒▒▒▒▓▓                   │
│ Healthy 57%  Moderate 24%  At Risk 14%  Critical 5% │
├─────────────────────────────────────────────────────┤
│ Search + Risk Level Filter                           │
│ [🔍 Search customers...]  [Risk Level ▾]            │
├─────────────────────────────────────────────────────┤
│ DataTable                                            │
│ Email | Name | Health | Risk | Feedbacks | Last     │
│                                  Count   | Active   │
│                                          | Trend    │
│ ─────────────────────────────────────────────────── │
│ john@acme.com | John | 34 🟡 | At Risk | 28 | 2h  │
│                                             | ↓-12% │
│ jane@corp.io  | —    | 72 🟢 | Healthy | 12 | 1d  │
│                                             | ↑+5%  │
│ ... rows ...                                         │
├─────────────────────────────────────────────────────┤
│ Pagination: « 1 2 3 4 5 ... 8 »                    │
└─────────────────────────────────────────────────────┘
```

### 4.2 Summary Stat Cards

4 cards using existing `StatCard` component pattern:

| Card | Value | Color |
|------|-------|-------|
| Total Customers | `summary.total_customers` | Default |
| Avg Health Score | `summary.avg_health_score` | Color-coded by score |
| At Risk % | `(at_risk + critical) / total * 100` | `--chart-1` (coral) |
| Critical Count | `summary.risk_distribution.critical` | `--destructive` |

### 4.3 Risk Distribution Bar

Horizontal stacked bar showing proportions:
- Segments: Healthy (green), Moderate (amber), At Risk (coral), Critical (red)
- Each segment shows label + percentage
- Uses theme CSS variables: `--chart-5`, `--chart-2`, `--chart-1`, `--destructive`
- Segments are clickable → sets the risk level filter

### 4.4 Table Columns

| Column | Content | Sortable |
|--------|---------|----------|
| Customer | Email (bold) + name below (muted). Email links to `/customers/[email]` | Yes (by email) |
| Health Score | 0-100 number with color-coded circle badge | Yes |
| Risk Level | Badge: Healthy/Moderate/At Risk/Critical | No (use filter) |
| Confidence | "Low" or "Medium" badge (hidden when "high") | No |
| Feedbacks | Count number | Yes |
| Last Active | Relative time (e.g., "2h ago", "3d ago") | Yes |
| Trend | Arrow + percentage: "↑ +12%" (green) or "↓ -8%" (red) or "→ 0%" (muted) | No |

### 4.5 Health Score Color Coding (consistent everywhere)

| Score Range | Color | CSS Variable |
|-------------|-------|--------------|
| 70-100 | Green | `--chart-5` |
| 50-69 | Amber | `--chart-2` |
| 30-49 | Coral | `--chart-1` |
| 0-29 | Red | `--destructive` |

### 4.6 Free Plan: Blurred Preview

For Free plan users:
- Page is accessible (sidebar link visible)
- Summary cards and stacked bar render normally
- Table shows ALL rows but with **blurred** health score, risk level, confidence, and trend columns
- Overlay CTA card above table: "Upgrade to Pro to unlock Customer Health Intelligence" with upgrade button
- Row clicks are disabled (no navigation to profile)

### 4.7 Empty State

When org has zero customers (no feedback with `customer_email`):
- Centered icon + message: "No customer data yet"
- Description: "Import feedback with customer emails to see health scores and risk analysis."
- CTA button: "Import Feedback" → `/feedbacks` (or CSV import)

---

## 5. Frontend — `/customers/[email]` Profile Page

**File**: `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx`

### 5.1 Page Layout

```
┌─────────────────────────────────────────────────────┐
│ Breadcrumb: Customers > john@acme.com                │
├─────────────────────────────────────────────────────┤
│ Profile Header                                       │
│ ┌──────┐                                             │
│ │  34  │  john@acme.com                [View All    │
│ │ score│  John Doe                      Feedbacks]  │
│ │  🟡  │  At Risk · 28 feedbacks · Last active 2h   │
│ └──────┘  ⚠ Low confidence (2 feedbacks)            │
├─────────────────────────────────────────────────────┤
│ Tabs: [Overview] [Feedbacks]                         │
├─────────────────────────────────────────────────────┤
│                                                      │
│  (Tab content below)                                 │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 5.2 Profile Header

- **Left**: Large health score circle (color-coded, same palette as list)
- **Center**: Customer email (primary, bold), name below (muted, or "—" if none), metadata line: risk level badge + feedback count + last active relative time
- **Confidence badge**: Shown below metadata when `confidence_level` is `low` or `medium`. Warning icon + "Low confidence — score based on only 2 feedbacks" tooltip.
- **Right**: "View All Feedbacks" button → `/feedbacks?customer_email={email}`

### 5.3 Overview Tab

#### Health Score Components (Progress Bars)

4 horizontal progress bars in a 2×2 grid:

```
Churn Risk (35%)           Sentiment (25%)
[████████░░░░░░░░] 22/100  [█████████████░░░] 38/100

Resolution (25%)            Frequency (15%)
[██████████████░░] 45/100  [████████░░░░░░░░] 30/100
```

- Label shows component name + weight percentage
- Progress bar fill color-coded by value (same health score palette)
- Tooltip explains the component (e.g., "Based on average time to resolve this customer's feedbacks")

#### Health Score Timeline Chart

- **Chart type**: Line chart (Recharts)
- **Toggle**: 30d / 60d / 90d buttons (default 30d)
- **Y-axis**: Health score 0-100
- **X-axis**: Dates
- **Data**: From `GET /api/v1/customers/{email}/history?days=N`
- **Reference lines**: Horizontal dashed lines at 70 (healthy threshold) and 30 (critical threshold)
- **Empty state**: "Not enough history yet. Score history builds as feedback is analyzed."

#### LLM Analysis Section

- **Card with AI icon** header: "AI Analysis"
- **If `llm_analysis` exists**: Render the analysis text. Show "Last analyzed: {relative time}" below.
- **If no analysis + health_score < 40**: Should auto-generate weekly. Show "Analysis pending" with next scheduled date.
- **If no analysis + health_score ≥ 40**: Show "Generate Analysis" button. On click → `POST /api/v1/customers/{email}/analyze`, show loading spinner, poll until `llm_analyzed_at` updates.
- **Plan gate**: "Generate Analysis" button requires `churn_llm_insights` feature. Otherwise show upgrade CTA.

#### Recent Activity Timeline

- **Last 5-10 events** in a vertical timeline component
- Event types with icons:
  - 📩 `feedback_created` — "New feedback submitted" + link to feedback
  - 🔄 `status_changed` — "Feedback #{id} moved to {status}" + link
  - 📉 `health_score_changed` — "Health score changed from {old} to {new}" (color-coded arrow)
  - 🤖 `llm_analysis_generated` — "AI analysis generated"
- Relative timestamps ("2 hours ago", "3 days ago")
- "View all feedbacks →" link at the bottom

### 5.4 Feedbacks Tab

Compact list of the customer's last 15 feedbacks:

```
┌─────────────────────────────────────────────────────┐
│ 😠 Negative · Churn Risk: 68 · In Review · 2h ago  │
│ "The billing page keeps crashing when I try to..."  │
├─────────────────────────────────────────────────────┤
│ 😐 Neutral · Churn Risk: 22 · Resolved · 3d ago    │
│ "Would be nice to have dark mode on the..."         │
├─────────────────────────────────────────────────────┤
│ ...                                                  │
└─────────────────────────────────────────────────────┘
│ Showing 15 of 28 feedbacks · View All →             │
```

Each row shows:
- Sentiment emoji + label
- Churn risk score (if > 0)
- Workflow status badge
- Relative timestamp
- Text snippet (first ~100 chars, truncated)
- Click → navigate to `/feedbacks/{id}`

"View All →" links to `/feedbacks?customer_email={email}`

---

## 6. Navigation & Entry Points

### 6.1 Sidebar

Add "Customers" to the **Main Navigation** group in `AppSidebar.tsx`:

```
Main Navigation:
  - Dashboard (/dashboard)
  - Feedbacks (/feedbacks)
  - Customers (/customers)       ← NEW
  - Workflow (/workflow)
  - Shared Links (/shared-links)
```

**Icon**: `Users` from Lucide React
**Plan badge**: Show a small "Pro" badge next to the link for Free plan users

### 6.2 Entry Points to Customer Profile

| Source | Behavior |
|--------|----------|
| `/customers` list → row click | Navigate to `/customers/{email}` |
| `/feedbacks/{id}` detail page | Clickable `customer_email` link → `/customers/{email}` (when email exists) |

### 6.3 Breadcrumbs

Profile page: `Customers > john@acme.com`
- "Customers" links back to `/customers`

---

## 7. Plan Gating

| Feature | Free | Pro+ |
|---------|------|------|
| `/customers` sidebar link | Visible (with Pro badge) | Visible |
| `/customers` list page | Blurred preview | Full access |
| `/customers/[email]` profile | Redirect to `/customers` with upgrade CTA | Full access |
| "Generate Analysis" button | Upgrade CTA | Working (requires `churn_llm_insights`) |

**Backend enforcement**: All `/api/v1/customers/*` endpoints use `Depends(require_feature("customer_health_scores"))`.

**Frontend enforcement**:
- List page: Check org plan in AuthContext. If Free → render blurred table + upgrade CTA.
- Profile page: If Free → redirect to `/customers`.

---

## 8. Archiving Behavior

### Soft Archive Trigger

When feedback is deleted (single or bulk), check if the customer has remaining feedbacks:

```python
# In feedback delete route (after deletion)
remaining = db.query(FeedbackItem).filter(
    FeedbackItem.organization_id == org_id,
    FeedbackItem.customer_email == email
).count()

if remaining == 0:
    customer_health.is_archived = True
```

### Unarchive Trigger

When new feedback with that `customer_email` is ingested, set `is_archived = False` in `update_customer_health()`.

### List Behavior

- Default: `include_archived=false` — archived customers hidden
- Archived customers can be shown via filter toggle (future enhancement, not in v1)

---

## 9. Health Score Service Updates

**File**: `services/backend-api/src/services/health_score_service.py`

### 9.1 Confidence Level Computation

Add to `compute_health_score()`:

```python
if feedback_count <= 2:
    confidence_level = "low"
elif feedback_count <= 9:
    confidence_level = "medium"
else:
    confidence_level = "high"
```

### 9.2 History Recording

After `update_customer_health()` upserts a record, compare `new_score` vs `old_score`. If `abs(new_score - old_score) >= 2`, insert a `CustomerHealthHistory` record.

### 9.3 Sentiment Trend Calculation

New function `compute_sentiment_trend(org_id, customer_email, db)`:

```python
def compute_sentiment_trend(org_id: int, customer_email: str, db: Session) -> dict:
    """Compare avg sentiment last 7d vs previous 7d."""
    now = datetime.utcnow()
    recent = db.query(func.avg(FeedbackItem.sentiment_score)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.created_at >= now - timedelta(days=7)
    ).scalar() or 0

    previous = db.query(func.avg(FeedbackItem.sentiment_score)).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.created_at >= now - timedelta(days=14),
        FeedbackItem.created_at < now - timedelta(days=7)
    ).scalar() or 0

    if previous == 0:
        return {"direction": "stable", "change_percent": 0}

    change = ((recent - previous) / abs(previous)) * 100
    if change > 5:
        direction = "improving"
    elif change < -5:
        direction = "declining"
    else:
        direction = "stable"

    return {"direction": direction, "change_percent": round(change, 1)}
```

---

## 10. Implementation Phases

### Phase 1: Backend (3-4 days)

1. **Migration**: Add `is_archived`, `confidence_level` to `customer_health_scores`. Create `customer_health_history` table.
2. **Health score service updates**: Confidence level computation, history recording on score change, sentiment trend function, unarchive logic.
3. **Customer list endpoint**: `GET /api/v1/customers/` with pagination, sorting, filtering, search, summary stats.
4. **Customer profile endpoint**: `GET /api/v1/customers/{email}` with full health data.
5. **Customer history endpoint**: `GET /api/v1/customers/{email}/history` with 30/60/90d range.
6. **Customer feedbacks endpoint**: `GET /api/v1/customers/{email}/feedbacks` (last 15, compact).
7. **Customer activity endpoint**: `GET /api/v1/customers/{email}/activity` (last 10 events).
8. **On-demand analysis endpoint**: `POST /api/v1/customers/{email}/analyze` (Celery task).
9. **Archive triggers**: Post-feedback-delete check, unarchive in `update_customer_health()`.

### Phase 2: Frontend — List Page (3-4 days)

1. **Sidebar**: Add "Customers" to Main Navigation with Users icon and Pro badge.
2. **Summary stat cards**: 4 cards using existing StatCard pattern.
3. **Risk distribution bar**: Horizontal stacked bar with clickable segments.
4. **Search + filter bar**: Search input (contains match) + risk level dropdown.
5. **DataTable**: Columns per spec, sortable, clickable rows.
6. **Pagination**: Numbered pages, 20 per page.
7. **Free plan blur**: Blurred columns + upgrade CTA overlay.
8. **Empty state**: No customers message with import CTA.
9. **React Query**: `useQuery` with staleTime 5min (consistent with app patterns).

### Phase 3: Frontend — Profile Page (3-4 days)

1. **Profile header**: Score circle, email/name, metadata, confidence badge, action button.
2. **Tabs**: Overview and Feedbacks using shadcn Tabs component.
3. **Overview tab**: Component progress bars (2×2 grid).
4. **Health timeline chart**: Recharts line chart with 30/60/90d toggle.
5. **LLM analysis section**: Auto/on-demand display with generate button.
6. **Recent activity timeline**: Vertical timeline with icons and relative timestamps.
7. **Feedbacks tab**: Compact list of last 15, with sentiment/status badges.
8. **Entry point**: Clickable customer_email on feedback detail page → profile.
9. **Breadcrumbs**: Customers > {email} navigation.

---

## 11. Files to Create

| File | Description |
|------|-------------|
| `services/backend-api/src/models/customer_health_history.py` | History model |
| `services/backend-api/alembic/versions/xxx_customer_360.py` | Migration |
| `services/backend-api/src/api/routes/customers.py` | Customer API routes |
| `services/frontend-web/app/(dashboard)/customers/page.tsx` | List page |
| `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx` | Profile page |
| `services/frontend-web/components/customers/RiskDistributionBar.tsx` | Stacked bar component |
| `services/frontend-web/components/customers/HealthScoreCircle.tsx` | Score circle component |
| `services/frontend-web/components/customers/ComponentProgressBars.tsx` | 4 progress bars |
| `services/frontend-web/components/customers/HealthTimeline.tsx` | Line chart component |
| `services/frontend-web/components/customers/ActivityTimeline.tsx` | Event timeline component |
| `services/frontend-web/components/customers/CustomerFeedbackList.tsx` | Compact feedback list |
| `services/frontend-web/lib/api/customers.ts` | API client functions |

## 12. Files to Modify

| File | Change |
|------|--------|
| `services/backend-api/src/models/customer_health.py` | Add `is_archived`, `confidence_level` fields |
| `services/backend-api/src/models/__init__.py` | Import new history model |
| `services/backend-api/src/services/health_score_service.py` | Confidence, history recording, sentiment trend, unarchive |
| `services/backend-api/src/api/main.py` | Register customers router |
| `services/backend-api/src/api/routes/feedback.py` | Post-delete archive check |
| `services/frontend-web/components/AppSidebar.tsx` | Add Customers nav item |
| `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx` | Clickable customer_email → profile link |
| `services/backend-api/src/config/plans.py` | Ensure `customer_health_scores` covers all new endpoints |

---

## 13. Performance Considerations

- **Customer list query**: Uses existing indexes on `customer_health_scores` (org_id + health_score, org_id + risk_level). Search adds ILIKE which needs `pg_trgm` or accepts sequential scan for < 10K customers.
- **Sentiment trend in list**: Computed per-row in the list query. For large customer lists (1000+), consider caching trend data on the `CustomerHealth` model directly and updating during `update_customer_health()`.
- **History table growth**: With ≥2-point change threshold, ~1-5 records per customer per week. At 10K customers, ~50K records/month. Add `recorded_at` index for efficient range queries. Consider 90-day retention cleanup job for history records (future).
- **Redis caching**: Cache the customer list response (5min TTL, keyed by org_id + query params). Invalidate on `update_customer_health()`.

---

## 14. Testing

### Backend Tests
- Customer list: pagination, sorting (all 4 fields), risk level filter, search (email, name), empty org, archived exclusion
- Customer profile: valid email, not found, wrong org (403), archived customer
- Customer history: 30/60/90d ranges, empty history
- Customer feedbacks: returns last 15, snippet truncation
- Customer activity: mixed event types, chronological ordering
- On-demand analysis: queues Celery task, rate limiting
- Archive/unarchive: delete last feedback → archived, new feedback → unarchived
- Confidence levels: 1-2 feedbacks (low), 3-9 (medium), 10+ (high)
- Plan gating: Free plan returns 403

### Frontend Tests
- List page renders with stat cards and stacked bar
- Table sorting and filtering
- Free plan blur overlay
- Profile header with confidence badge
- Tab switching (Overview / Feedbacks)
- Health timeline chart with period toggle
- Empty states
