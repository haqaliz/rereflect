# Aspect Spec — crm-profile-and-timeline

**Parent PRD:** `../prd.md` · **Slug:** `hubspot-crm-enrichment`

## Problem slice & user outcome

A CS lead viewing `/customers/{email}` sees a **CRM / Company** card (company,
lifecycle stage, ARR, renewal date, primary deal + stage + amount) and CRM events
interleaved in the Full Activity Timeline. The same CRM fields ride the public
profile serializer automatically (no new public endpoint).

## In scope

### Backend
- **Serializer:** add CRM fields to `serialize_customer_profile`
  (`src/services/customer_profile_serializer.py`) — reads the `(org, email)`
  `crm_enrichment` row, emits `crm_company_name`, `crm_lifecycle_stage`, `crm_arr`,
  `crm_renewal_date`, `crm_deal_name`, `crm_deal_stage`, `crm_deal_amount` (all
  Optional/None when absent). Flows to both `CustomerProfileResponse`
  (`customers.py`) and `PublicCustomerProfile360` (`public_api.py`) automatically —
  extend both Pydantic schemas with the Optional fields.
- **Timeline source:** `_fetch_crm_events(db, org_id, email, ...)` in
  `customer_timeline_service.py` returning `TimelineEvent`s with new types
  `crm_contact_synced`, `crm_deal_stage_changed`, `crm_renewal_upcoming`,
  `source="hubspot"`; add one `extend()` call in `build_timeline`. Add new
  `Optional` payload fields to the `TimelineEvent` dataclass + the `ActivityEvent`
  Pydantic model (`customers.py`, additive/Optional only) + map them in
  `_timeline_event_to_activity`.
  - v1 events are **derived from current enrichment state** (e.g.
    `crm_renewal_upcoming` when `renewal_date` within window; `crm_contact_synced`
    at `last_synced_at`) — no separate CRM-event history table in v1 (note honestly:
    `crm_deal_stage_changed` only fires if we can detect a change; if change-tracking
    isn't available from a single snapshot, defer that one event type and ship
    `crm_contact_synced` + `crm_renewal_upcoming`).

### Frontend
- **`CrmCompanyCard`** on the profile Overview tab
  (`app/(dashboard)/customers/[email]/page.tsx`), mirroring `UsageActivityCard`
  (self-contained, `useQuery`, three-state body, labeled stat grid, shadcn `Card`,
  theme CSS vars only). Placed near the top of Overview (after header / near Usage).
  Reads CRM fields from the profile response (already fetched) or a small
  `customersAPI` getter.
- **Timeline icons:** extend `ActivityEvent['type']` union in `lib/api/customers.ts`
  with the new `crm_*` literals + any Optional CRM payload fields; add matching
  `eventIconMap` entries in `components/customers/ActivityTimeline.tsx` (Lucide icon
  + `var(--chart-N)` tint via `color-mix(in oklch, …)`). Both timeline components
  render from the map automatically.

## Out of scope (this aspect)

- Pulling/storing CRM data (→ `hubspot-sync`).
- Health component math (→ `crm-health-component`).
- Connection UI (→ `hubspot-connection`).
- A new public API route (fields ride the existing serializer).

## Acceptance criteria (testable)

- Profile API returns CRM fields when a `crm_enrichment` row exists, and
  `None`/omitted when it doesn't (backend test like `tests/test_customer_profile.py`).
- Public profile (`tests/test_public_api_customer360.py` style) includes the same
  CRM fields.
- `build_timeline` interleaves CRM events in correct reverse-chronological order
  with existing events; cursor pagination still works (extend
  `tests/test_customer_timeline_service.py`).
- Frontend: `CrmCompanyCard` renders company/ARR/renewal when present, an empty
  state when not, a skeleton while loading (Vitest + Testing Library, mirror
  `__tests__/customers/`); unknown event types fall back to the muted dot.
- New timeline event types render with an icon + tint from `eventIconMap`
  (mirror `__tests__/customers/ActivityTimelineIcons.test.tsx`).

## Dependencies & sequencing

- **Reads `crm_enrichment`** (from `hubspot-sync`) and is most visible once sync
  runs, but can be built in parallel against the agreed schema using fixture rows.
- Backend serializer/timeline tasks and frontend tasks are independent → can be two
  parallel agents.
- No new migration (consumes columns/tables from other aspects).

## Open questions / risks

- `crm_deal_stage_changed` needs change detection; if v1 stores only current state,
  ship the two derivable event types and defer stage-change to v2 (state honestly).
- Keep colors to theme CSS vars; HubSpot brand orange only on the integration tile,
  not in the timeline.
