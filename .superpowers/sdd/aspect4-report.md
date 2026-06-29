# Aspect 4 Report — frontend-surface

## Status: DONE

## Commit Hashes (per phase)

| Phase | Commit | Message |
|-------|--------|---------|
| 1 — API types + getUsage | `49eeef3` | feat(usage-ui): customers API getUsage + usage types |
| 2 — ComponentProgressBars 5th bar | `98bc033` | feat(usage-ui): usage as 5th health component bar |
| 3 — UsageTimeline chart | `4388508` | feat(usage-ui): UsageTimeline chart |
| 4 — Profile Usage Activity card | `d01d1f2` | feat(usage-ui): Usage Activity card on customer profile |
| 5 — List column + settings/docs | `d7c154d` | feat(usage-ui): list last-active column + operator usage docs |

## Test / Lint / Build Results

- **Tests (aspect4-only):** 6 test files, 66 tests — all PASS
- **Lint:** `next lint` — Errors: 0, Warnings: 0
- **Build:** `next build` — ✓ Compiled successfully (no errors)
- **Full suite:** 781 passing, 24 pre-existing failures (baseline was 746 passing, 32 failing).
  My changes fixed 8 pre-existing failures (ComponentProgressBars + CustomerProfilePage)
  and added 51 new passing tests with 0 new regressions.

## Files Changed

```
services/frontend-web/lib/api/customers.ts              — types + getUsage
services/frontend-web/lib/api/__tests__/customers.usage.test.ts (new)
services/frontend-web/components/customers/ComponentProgressBars.tsx — 5 bars, score/100 format, weights
services/frontend-web/components/customers/UsageTimeline.tsx (new)
services/frontend-web/app/(dashboard)/customers/[email]/page.tsx — breadcrumb, UsageActivityCard, usage_component prop
services/frontend-web/app/(dashboard)/customers/page.tsx — last_active_at column
services/frontend-web/app/(dashboard)/settings/usage-events/page.tsx (new)
services/frontend-web/__tests__/customers/ComponentProgressBars.test.tsx — updated 4→5 bars
services/frontend-web/__tests__/customers/UsageTimeline.test.tsx (new)
services/frontend-web/__tests__/customers/CustomerProfilePage.test.tsx — added getUsage mock, breadcrumb test
services/frontend-web/__tests__/customers/CustomersPage.test.tsx — updated column header names
services/frontend-web/__tests__/settings/UsageEventsPage.test.tsx (new)
docs/SELF_HOSTING.md — "Send product-usage events" section added
```

## API-Contract Assumptions to Confirm at Integration

1. **`GET /api/v1/customers/{email}/usage?days=30`** — built against the locked contract exactly:
   `{ email, last_active_at, login_count_7d, login_count_30d, active_days_30d, distinct_feature_count, usage_score, period_days, series: [{date, events}] }`.
   Assumption: `series[].events` is the event count per day (integer). If the backend uses a different field name (e.g., `event_count`) the `UsageTimeline` chart data-key must be updated from `events` → that name.

2. **`CustomerProfileData.usage_component`** — added as `optional number`. Verify that when the backend returns this field, it's a 0-100 integer. If absent/null, the component defaults to 50 (neutral). No change needed.

3. **`CustomerListItem.last_active_at`** — added as `optional string | null`. The backend list endpoint (`GET /api/v1/customers/`) may not yet return this field. Column will render "—" gracefully when absent — no integration risk.

4. **Default weight display** — `ComponentProgressBars` shows HARDCODED default weights (35/25/25/15/0%). If org-level weights differ from defaults, the displayed weight % won't match reality. A future enhancement would pass actual org weights as props. For now this matches the spec ("show default weight %").

## Integration fix — contract alignment

### Commit
`ab84fb3` — fix(usage-ui): align usage types/components to the real backend response (rollup/time_series/event_count)

### Files Changed
- `services/frontend-web/lib/api/customers.ts` — removed flat `UsageHistoryEntry`/`CustomerUsageResponse`; added `UsageRollup`, `UsageTimeSeriesBucket`, nested `CustomerUsageResponse { rollup, time_series, period_days }`
- `services/frontend-web/components/customers/UsageTimeline.tsx` — `data?.series` → `data?.time_series`, `dataKey="events"` → `dataKey="event_count"`
- `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx` — `UsageActivityCard` reads stats from `data.rollup.*` (login_count_30d, active_days_30d, distinct_feature_count, last_active_at)
- `services/frontend-web/lib/api/__tests__/customers.usage.test.ts` — updated all fixtures and assertions to nested shape (`rollup.*`, `time_series`, `event_count`); imports `UsageRollup`/`UsageTimeSeriesBucket`
- `services/frontend-web/__tests__/customers/UsageTimeline.test.tsx` — updated `mockUsageWithSeries`/`mockUsageEmpty` to nested shape
- `services/frontend-web/__tests__/customers/CustomerProfilePage.test.tsx` — updated both `getUsage` mock returns to nested shape

### Test / Lint / Build Results
- **Targeted tests (3 files, 28 tests):** all PASS
- **Full suite:** 781 passing, 24 pre-existing failures — no regressions introduced
- **TypeScript:** 0 errors in modified files (pre-existing errors in AI settings tests unrelated)
- **Build:** `next build` — ✓ Compiled successfully (no errors)

## Concerns

- ~~The `settings/usage-events` page is a new route that needs to be reachable from the settings navigation.~~ **Fixed in final-review (I2).**
- ~~The `ComponentProgressBars` usage weight shows `0%` as the default display.~~ **Fixed in final-review (I3).**
- The `UsageActivityCard` in the profile page makes a separate `getUsage` call independent of `UsageTimeline`'s own React Query call. Both share the same query key `['customer-usage', email, days]` so they hit the React Query cache — no double network request in practice.

---

## Final-review fixes (frontend)

### Files changed

| File | Change |
|------|--------|
| `services/frontend-web/components/AppSidebar.tsx` | Added `Activity` icon import; added `{ title: 'Usage Events', href: '/settings/usage-events', icon: Activity, requiredRole: 'admin' }` entry to `settingsNavItems` |
| `services/frontend-web/components/customers/ComponentProgressBars.tsx` | Added `'use client'`; imports `useQuery` + `categoriesAPI`; fetches org health weights via `['health-weights']` query; maps backend field names (churn→churn_risk etc.) to `liveWeights`; renders `· N%` from live weights with fallback to documented defaults (35/25/25/15/0) |
| `services/frontend-web/lib/api/categories.ts` | Added `HealthWeightsResponse` interface extending `HealthWeights` with `usage: number`; updated `getHealthWeights()` return type to `HealthWeightsResponse` (keeps `HealthWeights` 4-field interface intact so `HealthWeightsEditor` is unaffected) |
| `services/frontend-web/__tests__/customers/ComponentProgressBars.test.tsx` | All tests updated to use `QueryClientProvider` wrapper + `categoriesAPI.getHealthWeights` mock; 7 new tests added (TDD): live `usage=10` shows `· 10%`, default `usage=0` shows `· 0%`, fallback on fetch failure, full live-weights assertion |
| `services/frontend-web/__tests__/settings/AppSidebar.test.tsx` | New file: 5 tests — "Usage Events" link renders for admin, renders for owner, is hidden for member, points to correct href, absent before user loads |

### How weights are sourced

`ComponentProgressBars` issues a `useQuery(['health-weights'], categoriesAPI.getHealthWeights)` call (staleTime 5 min, shared cache key with `HealthWeightsEditor`). The returned `HealthWeightsResponse` maps backend field names (`churn`, `sentiment`, `resolution`, `frequency`, `usage`) to component keys (`churn_risk`, etc.) in a `liveWeights` record. Each bar renders `· liveWeights[key]%`. Until the query resolves (or if it fails), the bar falls back to the documented defaults (35/25/25/15/0).

### Test results

- **ComponentProgressBars:** 21/21 PASS (was 14; 7 new live-weights tests added)
- **AppSidebar:** 5/5 PASS (new file)
- **Full suite:** 792 passing, 24 pre-existing failures unchanged (baseline was 781 / 24)
- **Lint:** `next lint` — no errors in changed files (TypeScript: 0 errors in modified files)
- **Build:** `next build` — ✓ Compiled successfully
