# Aspect Spec — `frontend-timeline-ui`

**Parent PRD:** `../prd.md` · **Slug:** `customer-360-unified-timeline`
**Build order:** 3 of 3 (depends on `timeline-service-v1` contract; parallel with aspect 2)

## Problem slice & outcome

The profile Overview tab shows a capped "Recent Activity" card
(`ActivityTimeline.tsx`, `app/(dashboard)/customers/[email]/page.tsx:795-803`) that omits usage
and churn and can't page back. Outcome: a **paginated Customer Timeline card** that renders all
sources (incl. usage/churn) with "Load more", reusing the existing icon/feed pattern.

## In scope

- **Extend the `ActivityEvent` discriminated union** (`lib/api/customers.ts:159-166`) and the
  `eventIconMap` (`ActivityTimeline.tsx:33-59`) with the new types: `churned`, `churn_recovered`,
  `usage_first_seen`, `usage_reactivated`, `usage_feature_adopted`. Pick lucide icons + Sunset-
  Horizon CSS-var tints via `color-mix(in oklch, var(--…) 10%, transparent)` — **no hardcoded
  colors**. (Suggested: churn → `UserMinus`/`--destructive`; recovery → `UserCheck`/`--chart-5`;
  usage → `Activity`/`Zap`/`Sparkles` on `--chart-2`.)
- **API client:** `customersAPI.getTimeline(email, { before?, limit? })` →
  `{ events: ActivityEvent[]; next_cursor: string | null }`; add the response type.
- **New `CustomerTimeline` card** (own component; can wrap/extend the existing `EventItem`
  row renderer) on the Overview tab: initial page via React Query, **"Load more"** button that
  fetches the next cursor and appends, loading skeleton (match `UsageTimeline` skeleton), empty
  state ("No activity yet"), and a graceful end state when `next_cursor` is null.
- Keep the existing **"Recent Activity"** card working as-is (it now shows usage/churn
  automatically via the refactored `/activity`) — the new full timeline is an **additive** card,
  or replaces the recent-activity card if it cleanly supersedes it (decide during implementation;
  default: add the full timeline below, leave recent card untouched to avoid regression).

## Out of scope

- Per-source filter chips (nice-to-have). Public-API consumption. Real-time updates.
- Segments / bulk actions.

## Acceptance criteria (testable)

1. Each new event type renders with its own icon + tint and a human-readable description.
2. `getTimeline` is called with no cursor initially; "Load more" calls it with `before=<next_cursor>`
   and **appends** (no replace, no duplicate keys).
3. "Load more" disappears / disables when `next_cursor` is `null`.
4. Loading shows the skeleton; empty shows the empty state; both match existing conventions.
5. Usage/churn rows appear interleaved in correct time order (driven by backend order).
6. `npm run lint` and `npm run test` pass; no hardcoded colors (CSS vars only).

## Dependencies & sequencing

- **Depends on aspect 1** endpoint contract (`/customers/{email}/timeline`, `{events, next_cursor}`)
  and the final event-type names. Can develop against the agreed contract in parallel with aspect 2.
- Reuse: `components/ui/card.tsx`, `skeleton.tsx`, `badge.tsx`, lucide icons, React Query
  (`useQuery`/`useInfiniteQuery`), and the `ActivityTimeline`/`NotificationBell` feed patterns.

## Risks

- Event-type names must match the backend `type` strings exactly — lock them in aspect 1 first.
- `useInfiniteQuery` vs manual append: either is fine; keep query keys stable to avoid refetch loops.
