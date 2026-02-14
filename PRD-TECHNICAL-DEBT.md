# PRD: Technical Debt Resolution

**Product**: Rereflect
**Author**: Rereflect Team
**Date**: 2026-02-15
**Timeline**: 3-4 weeks (Feb 17 - Mar 14, 2026)
**Status**: Draft

---

## 1. Overview

This PRD covers the resolution of three technical debt items identified in DEV-TRACKING.md:

1. **Performance Optimization (Caching)** - Redis server-side caching + React Query client-side caching
2. **Database Query Optimization** - Missing indexes, N+1 queries, search improvements
3. **Test Coverage** - Billing/Stripe tests (highest risk gap) + frontend test infrastructure (Vitest)

### Current Data Scale
< 1,000 feedback items in production. Optimizations are preventive — designed to scale to 100K+ items without rework.

### Success Criteria
- Dashboard endpoint: < 200ms response time (currently 1000ms+ at scale)
- Redis cache hit rate > 80% for dashboard/analytics
- Billing/Stripe endpoints: 100% test coverage for critical paths
- Frontend test infrastructure: Vitest configured and running with initial component tests
- All critical database indexes added via Alembic migration
- Zero regressions (existing 39 test files continue passing)

---

## 2. Phase 1: Database Query Optimization (Week 1)

### 2.1 Add Missing Indexes

**Priority**: Critical
**Files**: `services/backend-api/src/models/feedback.py`, new Alembic migration

Add 4 compound indexes to `feedback_items` table:

| Index Name | Columns | Used By |
|-----------|---------|---------|
| `ix_feedback_org_sentiment` | (organization_id, sentiment_label) | Dashboard sentiment stats, feedback list filter |
| `ix_feedback_org_urgent` | (organization_id, is_urgent) | Urgent feedbacks page, dashboard urgent section |
| `ix_feedback_org_pain_cat` | (organization_id, pain_point_category) | Dashboard pain points, analytics trends |
| `ix_feedback_org_feature_cat` | (organization_id, feature_request_category) | Dashboard feature requests, analytics trends |

**Implementation**:
1. Add indexes to FeedbackItem model `__table_args__`
2. Create Alembic migration: `alembic revision -m "add_critical_feedback_indexes"`
3. Test migration up/down locally
4. Apply to production

### 2.2 Add SQLAlchemy Relationships for Eager Loading

**Priority**: High
**File**: `services/backend-api/src/models/feedback.py`

Add relationships to FeedbackItem model:
```python
feedback_source = relationship("FeedbackSource", backref="feedback_items", lazy="select")
assigned_user = relationship("User", foreign_keys=[assigned_to], backref="assigned_feedback_items", lazy="select")
```

Then update `services/backend-api/src/api/routes/feedback.py` (lines 325-337) to use `joinedload` instead of separate batch queries:
```python
from sqlalchemy.orm import joinedload
query = query.options(
    joinedload(FeedbackItem.feedback_source),
    joinedload(FeedbackItem.assigned_user),
)
```

This eliminates 2 extra queries per feedback list request.

### 2.3 Fix Tag Aggregation

**Priority**: Medium
**File**: `services/backend-api/src/api/routes/dashboard.py` (lines 212-224)

Replace Python-side tag counting with SQL aggregation:
```python
# BEFORE: Loads ALL feedback into memory, counts tags in Python
all_feedback_with_tags = base_query.filter(FeedbackItem.tags.isnot(None)).all()
tag_counter = Counter()
for item in all_feedback_with_tags:
    tag_counter.update(item.tags)

# AFTER: SQL-level aggregation
from sqlalchemy import func, text
tag_rows = db.query(
    func.jsonb_array_elements_text(FeedbackItem.tags).label('tag'),
    func.count().label('cnt')
).filter(
    FeedbackItem.organization_id == current_org.id,
    FeedbackItem.tags.isnot(None)
).group_by(text('tag')).order_by(text('cnt DESC')).limit(20).all()
```

### 2.4 Enable SQL Query Logging (Dev Only)

**Priority**: Low
**File**: `services/backend-api/src/database/session.py`

Add optional query logging controlled by environment variable:
```python
import os
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)
```

### Phase 1 Deliverables
- [ ] Alembic migration with 4 new indexes
- [ ] FeedbackItem relationships added
- [ ] Feedback list endpoint uses eager loading
- [ ] Tag aggregation moved to SQL
- [ ] SQL_ECHO env var support
- [ ] All existing tests pass

---

## 3. Phase 2: Performance Optimization - Server Caching (Week 2)

### 3.1 Redis Cache Layer

**Priority**: Critical
**New file**: `services/backend-api/src/services/cache_service.py`

Create a reusable Redis caching service using the already-reserved Redis DB 2:

```python
import json
import redis
import os

redis_cache = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD", None),
    db=2,  # Reserved for application cache
    decode_responses=True,
)

def cache_get(key: str):
    """Get cached value, returns None if miss."""
    val = redis_cache.get(key)
    return json.loads(val) if val else None

def cache_set(key: str, value: dict, ttl_seconds: int = 300):
    """Set cache with TTL (default 5 min)."""
    redis_cache.setex(key, ttl_seconds, json.dumps(value, default=str))

def cache_invalidate(pattern: str):
    """Invalidate all keys matching pattern."""
    for key in redis_cache.scan_iter(match=pattern):
        redis_cache.delete(key)
```

### 3.2 Dashboard Endpoint Caching

**Priority**: Critical
**File**: `services/backend-api/src/api/routes/dashboard.py`

Cache the full dashboard response per organization with 5-minute TTL:

```python
from src.services.cache_service import cache_get, cache_set

@router.get("/")
def get_dashboard(days: int = 30, ...):
    cache_key = f"dashboard:{current_org.id}:{days}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # ... existing 12 queries ...
    result = DashboardResponse(...).dict()
    cache_set(cache_key, result, ttl_seconds=300)  # 5 min
    return result
```

### 3.3 Analytics Endpoint Caching

**Priority**: High
**File**: `services/backend-api/src/api/routes/analytics.py`

Cache analytics trends per organization + date range with 10-minute TTL:

```python
cache_key = f"analytics:{current_org.id}:{date_range}"
```

### 3.4 Cache Invalidation on Write

**Priority**: High
**Files**: `services/backend-api/src/api/routes/feedback.py`, `services/worker-service/src/tasks/analysis.py`

Invalidate dashboard/analytics cache when:
- New feedback is created (POST /feedback)
- Feedback is analyzed (worker completes analysis)
- Feedback status changes (workflow updates)

```python
from src.services.cache_service import cache_invalidate

# After feedback creation or analysis:
cache_invalidate(f"dashboard:{org_id}:*")
cache_invalidate(f"analytics:{org_id}:*")
```

### 3.5 HTTP Cache Headers

**Priority**: Medium
**File**: `services/backend-api/src/api/main.py`

Add Cache-Control headers for read-only endpoints:
- Dashboard: `Cache-Control: private, max-age=60`
- Analytics: `Cache-Control: private, max-age=120`
- Static data (categories, sources): `Cache-Control: private, max-age=300`

### Phase 2 Deliverables
- [ ] `cache_service.py` with Redis DB 2
- [ ] Dashboard endpoint cached (5 min TTL)
- [ ] Analytics endpoint cached (10 min TTL)
- [ ] Cache invalidation on feedback create/analyze/status-change
- [ ] HTTP Cache-Control headers on read endpoints
- [ ] All existing tests pass (mock Redis in tests)

---

## 4. Phase 3: Performance Optimization - Client Caching (Week 2-3)

### 4.1 Add React Query (TanStack Query)

**Priority**: High
**Files**: `services/frontend-web/package.json`, new provider component

Install and configure:
```bash
npm install @tanstack/react-query
```

Create QueryProvider wrapping the app in layout or a client component wrapper.

### 4.2 Migrate Dashboard to React Query

**Priority**: High
**File**: `services/frontend-web/app/(dashboard)/dashboard/page.tsx`

Replace `useEffect` + `useState` pattern with `useQuery`:

```typescript
const { data, isLoading, error } = useQuery({
  queryKey: ['dashboard', days],
  queryFn: () => dashboardAPI.get(days),
  staleTime: 5 * 60 * 1000,    // 5 min stale
  gcTime: 30 * 60 * 1000,       // 30 min garbage collection
});
```

Benefits:
- Stale-while-revalidate (shows cached data immediately, refreshes in background)
- Request deduplication (multiple components requesting same data = 1 fetch)
- Automatic retry on failure
- Background refetching on window focus

### 4.3 Migrate Key Pages to React Query

Migrate in this order (highest traffic first):
1. Dashboard page (`/dashboard`)
2. Feedbacks list page (`/feedbacks`)
3. Analytics page (if separate from dashboard)
4. Workflow page (`/workflow`)
5. Notifications page (`/notifications`)

### 4.4 Improve Polling Efficiency

**Priority**: Medium
**File**: `services/frontend-web/app/(dashboard)/feedbacks/page.tsx`

Replace unconditional 30s polling with React Query's `refetchInterval`:
```typescript
const { data } = useQuery({
  queryKey: ['feedbacks', filters],
  queryFn: () => feedbackAPI.list(filters),
  refetchInterval: 30000,       // Still polls every 30s
  refetchIntervalInBackground: false, // Don't poll in background tabs
});
```

### Phase 3 Deliverables
- [ ] React Query installed and configured
- [ ] QueryProvider wrapping app
- [ ] Dashboard migrated to useQuery
- [ ] Feedbacks list migrated to useQuery
- [ ] Workflow page migrated to useQuery
- [ ] Polling uses refetchInterval (no background tab polling)

---

## 5. Phase 4: Test Coverage (Week 3-4)

### 5.1 Billing/Stripe Test Suite

**Priority**: Critical (highest-risk untested code)
**New file**: `services/backend-api/tests/test_billing.py`

Test cases to cover:

**Checkout & Subscription:**
- Create checkout session for each plan tier (Pro, Business, Enterprise)
- Handle successful checkout webhook (`checkout.session.completed`)
- Handle subscription update webhook (`customer.subscription.updated`)
- Handle subscription cancellation webhook (`customer.subscription.deleted`)
- Reject checkout for already-subscribed org
- Validate plan tier transitions (upgrade/downgrade)

**Billing Portal:**
- Create portal session for owner
- Reject portal access for non-owner (admin, member)

**Usage & Limits:**
- Feedback limit enforcement per plan tier
- Overage tracking for Pro/Business
- Usage reset on billing cycle

**Feature Gating:**
- `require_feature` dependency blocks access for wrong tier
- Feature access granted for correct tier
- Enterprise features blocked for Pro/Business

**Webhook Security:**
- Stripe signature verification succeeds with valid signature
- Stripe signature verification fails with invalid signature
- Idempotent webhook handling (duplicate events ignored)

**Mock Strategy**: Mock `stripe` Python SDK calls (never hit real Stripe API in tests). Use `unittest.mock.patch` on `src.services.stripe_service` methods.

### 5.2 Frontend Test Infrastructure (Vitest)

**Priority**: High
**New files**: `services/frontend-web/vitest.config.ts`, `services/frontend-web/vitest.setup.ts`

Setup Vitest with:
```bash
npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom
```

Configuration:
```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    css: false,
  },
});
```

### 5.3 Initial Frontend Tests

Write starter tests for the most critical frontend code:

**API Client Tests** (test data transformation, error handling):
- `lib/api/auth.ts` — login, signup, token refresh
- `lib/api/dashboard.ts` — dashboard data fetching
- `lib/api/feedback.ts` — feedback CRUD, pagination

**Context Tests** (test state management logic):
- `contexts/AuthContext.tsx` — login/logout state, role checks
- `contexts/ThemeContext.tsx` — theme toggle, persistence

**Component Tests** (test rendering, user interaction):
- `components/StatCard.tsx` — renders value, handles click navigation
- `components/SettingsTabs.tsx` — tab visibility by role (owner/admin/member)

### 5.4 Test Scripts

Add to `services/frontend-web/package.json`:
```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage"
  }
}
```

Add to `services/backend-api/`:
```bash
# In start-test.sh or similar:
pytest tests/ -v --tb=short
```

### Phase 4 Deliverables
- [ ] `test_billing.py` with 15+ test cases covering all Stripe flows
- [ ] Vitest configured in frontend-web
- [ ] `@testing-library/react` installed
- [ ] 5+ frontend test files (API clients, contexts, key components)
- [ ] `npm run test` script working
- [ ] All 39 existing backend tests still pass

---

## 6. Out of Scope

The following were considered but excluded from this PRD:

| Item | Reason |
|------|--------|
| Sentry error tracking | Costs $29/mo, deferred until paying customers cover it |
| DataDog monitoring | Costs $$$, deferred |
| PostgreSQL full-text search (GIN indexes) | < 1K items, ILIKE is fine for now |
| Consolidating dashboard into fewer queries | Redis cache solves the symptom; query consolidation can come later |
| Frontend E2E tests (Playwright) | Vitest unit/component tests first, E2E later |
| CI/CD pipeline (GitHub Actions) | Manual test runs for now, add CI when team grows |
| Keyset pagination | Offset pagination works fine at < 1K items |
| Analytics pre-computation (background job) | Cache solves this for now |
| Materialized views | Overkill at current scale |

---

## 7. Implementation Schedule

| Week | Phase | Key Deliverables |
|------|-------|-----------------|
| **Week 1** (Feb 17-21) | DB Query Optimization | 4 indexes, eager loading, tag aggregation fix |
| **Week 2** (Feb 24-28) | Server Caching | Redis cache service, dashboard + analytics caching, cache invalidation |
| **Week 2-3** (Feb 28 - Mar 7) | Client Caching | React Query setup, dashboard + feedbacks migration, polling optimization |
| **Week 3-4** (Mar 7-14) | Test Coverage | Billing test suite, Vitest setup, initial frontend tests |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Redis cache gets stale | Users see outdated dashboard data | 5 min TTL + invalidation on writes |
| Index migration locks table | Downtime during deploy | Use `CREATE INDEX CONCURRENTLY` in migration |
| React Query migration breaks pages | UI regressions | Migrate one page at a time, test each |
| Billing tests don't cover edge case | Payment bug in production | Focus on webhook handling (most critical path) |
| SQLite test DB differs from PostgreSQL | Tests pass but production fails | Document PostgreSQL-specific behavior in test comments |

---

## 9. Related Documents

- [DEV-TRACKING.md](DEV-TRACKING.md) - Development roadmap
- [SALES-TRACKING.md](SALES-TRACKING.md) - Sales strategy
- [CLAUDE.md](CLAUDE.md) - Technical documentation
