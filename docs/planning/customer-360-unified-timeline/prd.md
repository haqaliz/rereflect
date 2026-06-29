# PRD — Customer 360 Unified Timeline

**Product:** Rereflect (open-source, self-hosted, BYOK/local-LLM — MIT, all features unlocked)
**Slug:** `customer-360-unified-timeline`
**Branch:** `feat/customer-360-unified-timeline`
**Date:** 2026-06-29
**Status:** Draft (pre review-gate)
**Milestone:** AI-TRACKING **M3.4 — Enhanced Customer 360** (unified timeline + Customer 360 API), first slice
**Source:** Freeform task selected via `rereflect-next`. See `docs/planning/_card/card.md` + `understanding.md`.

---

## Problem Statement

A self-hosted operator looking at a customer in Rereflect cannot see that customer's
**full story in one place, in time order.** The data exists but is scattered:

- A **"Recent Activity" card** already exists on `/customers/[email]` but it is a capped
  *last-10* widget (`GET /api/v1/customers/{email}/activity`,
  `services/backend-api/src/api/routes/customers.py:512-611`). It merges 5 sources —
  `feedback_created`, `status_changed`, `health_score_changed`, `llm_analysis_generated`,
  `action_completed` — then truncates to 10. There is no way to page back through history.
- The **product-usage data shipped in M3.2** (`usage_events`, `customer_usage`, merge
  `a8047d9`) is **completely absent** from that timeline — the activity endpoint predates it.
- **Churn events** (`customer_churn_events`, M4.1) — when a customer churned and why,
  whether they were recovered — are **also absent** from the timeline.
- None of this is reachable **programmatically**: the public REST API (API-key, `read`
  scope) exposes only a customers *list* and a thin `/customers/{email}/health`
  (`routes/public_api.py:305-364`). There is **no full Customer 360 profile and no
  timeline** for external consumption.

**Evidence it's real:** the activity endpoint's own docstring says *"Get last 10 mixed
activity events"*; the `ActivityEvent` union (`lib/api/customers.ts`) has no usage or churn
member; the just-merged M3.2 usage work added a separate "Usage Activity" card but never
wired usage into the activity feed. AI-TRACKING M3.4 (`AI-TRACKING.md:201-206`) is pending
`[ ]` and explicitly lists "unified customer timeline … in chronological order" plus a
"Customer 360 API" and "health score API endpoint for programmatic access."

This is the connective tissue of the churn → health → playbook loop: a single chronological
view is where an operator *sees why* a health score moved (a usage drop, then negative
feedback, then a score drop, then churn).

## Goals & Success Metrics

| Goal | Metric (testable) |
|---|---|
| Usage + churn become first-class timeline events | A customer with usage events and a churn event shows `usage_*` and `churned`/`churn_recovered` rows in the timeline, interleaved in correct time order with feedback/health rows |
| The timeline is browsable, not capped | `GET /customers/{email}/timeline?limit=20` returns ≤20 events + a `next_cursor`; following the cursor returns the next page with **no duplicates and no skips** across events that share a timestamp |
| No regression to the existing widget | `GET /customers/{email}/activity` still returns the same `{events: [...]}` shape, still ≤10 items, now also drawing usage/churn — driven by the **same shared service** |
| Programmatic Customer 360 | Public API (`rrf_` key, `read` scope) returns a full customer profile, a health detail, and the timeline; a key **without** `read` scope gets 403; cross-org access is impossible |
| Honest usage representation | Usage rows are **synthesized notable events** (first-seen, reactivation, feature-adoption), never a flood of raw track events |
| Fits OSS self-hosted | No plan gating; runs against the operator's own Postgres; no external service required to demo |

## User Personas & Scenarios

- **CS / Success operator (primary):** opens a customer flagged at-risk, scrolls the
  timeline to understand the sequence — "usage dropped two weeks ago, then they filed an
  angry bug, health fell to 38, we ran a playbook." Acts with context.
- **Founder / operator-developer (self-host):** pulls the Customer 360 profile + timeline
  via the public API into their own dashboard, Slack bot, or warehouse — the "build on top
  of Rereflect" surface that fits BYOK/self-hosted.

## Requirements

### Must-have

1. **Shared timeline service** (`services/customer_timeline_service.py`) that merges, for an
   org+email, in reverse-chronological order:
   - `feedback_created`, `status_changed`, `health_score_changed`, `llm_analysis_generated`,
     `action_completed` (port the existing `/activity` logic into the service)
   - **`churned`** (from `customer_churn_events.churned_at`, with `reason_code`) and
     **`churn_recovered`** (from `recovered_at` when present)
   - **notable usage events** (see below)
   - Returns a **source-extensible** event shape (a CRM source can be added later without a
     schema change) and supports **cursor pagination** + a **`limit`** mode for the widget.
2. **Notable-usage derivation** (on-read from `usage_events` + `customer_usage`, no flood):
   - `usage_first_seen` — at `customer_usage.first_seen_at` (one event).
   - `usage_reactivated` — an event whose `occurred_at` follows a gap of **≥ 14 days** with
     no prior usage events (dormancy threshold; tunable constant).
   - `usage_feature_adopted` — first `occurred_at` at which each distinct feature
     (`properties`-derived, matching how M3.2 computes `distinct_features`) first appears.
3. **New v1 endpoint** `GET /api/v1/customers/{email}/timeline?before=<iso>&limit=<n>` →
   `{ events: [...], next_cursor: <iso|null> }`, org-scoped via `get_current_org`, JWT auth.
4. **Refactor** `GET /customers/{email}/activity` to call the shared service with `limit=10`
   — same external response shape, now including usage/churn.
5. **Public API read endpoints** (`verify_api_key` + `require_scope("read")`):
   - `GET /api/public/v1/customers/{email}` — full Customer 360 profile (mirrors the v1
     `CustomerProfileResponse`: health, components incl. usage, churn probability/bucket,
     LLM summary fields).
   - `GET /api/public/v1/customers/{email}/timeline` — same paginated timeline.
   - Extend `GET /api/public/v1/customers/{email}/health` with the component breakdown if it
     is currently thin.
6. **Frontend**: extend the `ActivityEvent` union + `eventIconMap` with usage/churn types
   (new lucide icons, Sunset-Horizon CSS vars via `color-mix`); a paginated **Customer
   Timeline** card with a **"Load more"** control on the profile Overview tab;
   `customersAPI.getTimeline(email, cursor?)` + types in `lib/api/customers.ts`.
7. **Cursor correctness**: order by `(timestamp DESC, type ASC, source_id ASC)`; the cursor
   encodes the last item's timestamp (and tiebreak) so paging never skips/repeats events
   sharing a `timestamp`.

### Should-have

- `usage_dropped` notable event (week-over-week active-days decline). **Deferred** — not
  derivable without persisted usage history; see Risks. Would land with a future
  `customer_usage_history` table (mirroring `customer_health_history`).
- "Jump to first" / total-count affordance on the timeline card.

### Nice-to-have

- Per-source filter chips on the timeline (show only usage / only churn / etc.).
- Public-API OpenAPI examples for the new endpoints.

## Technical Considerations

- **Services changed:** `backend-api` (new service + v1 endpoint + public endpoints + Pydantic
  schemas) and `frontend-web` (timeline card + API client + types). **Worker-service:
  no change** for must-haves (all sources already written). **No analysis-engine change.**
- **Multi-tenancy:** every query filters `organization_id`; v1 via `get_current_org` (JWT),
  public via `verify_api_key` → `organization_id`. Timeline is keyed by org + `customer_email`.
- **No new migration for must-haves** — all source tables exist (`feedback_items`,
  `feedback_workflow_events`, `customer_health_history`, `customer_health`,
  `customer_analysis_actions`, `usage_events`, `customer_usage`, `customer_churn_events`).
  (The deferred `usage_dropped` event would need a new `customer_usage_history` table — out
  of scope here.)
- **Performance:** the merge reads several tables per request. For cursor pages, each source
  query is bounded by `WHERE timestamp < before ORDER BY timestamp DESC LIMIT n`, then merged
  in Python and re-truncated to `limit` (standard k-way-merge-with-overfetch). Existing
  indexes cover it: `ix_feedback_org_date`, `ix_health_history_customer_date`,
  `ix_usage_events_org_email_occurred`, `ix_churn_event_org_email`. Notable-usage derivation
  scans the customer's `usage_events` for the page window — acceptable per-customer; revisit
  if a customer has very high event volume.
- **Feature gating:** OSS self-hosted — **no plan gate** on new endpoints. The existing
  `require_feature("customer_health_scores")` on v1 customer routes is effectively a no-op in
  the self-hosted edition; new v1 endpoints stay consistent with sibling routes, public
  endpoints gate only on API-key `read` scope.
- **Backward compatibility:** `/activity`'s response contract is unchanged; only its internals
  move into the shared service. Existing `ActivityTimeline.tsx` keeps working; the new card is
  additive.

## Risks & Open Questions

- **R1 — `usage_dropped` not derivable today.** `customer_usage` stores only current 7d/30d
  counters, no history, so week-over-week drop can't be computed on-read. Scoped out;
  documented as needing `customer_usage_history`. *Honesty: we will not fabricate a drop event.*
- **R2 — usage event volume.** Notable-usage derivation scans `usage_events` for the customer.
  For pathological volumes this could be slow; mitigated by the per-page time window and the
  `(org, email, occurred_at)` index. Flag for the plan: cap the derivation scan window.
- **R3 — feature attribution from `properties`.** `usage_feature_adopted` depends on how M3.2
  derives `distinct_features` from event `properties`; reuse that exact logic (don't
  re-invent) to stay consistent. Confirm the helper location in the plan.
- **R4 — cursor tiebreak.** Multiple sources can emit the same `timestamp`; the
  `(timestamp, type, source_id)` ordering must be applied identically in every paged query and
  in the cursor encoding, or pages will skip rows. Covered by an explicit test.
- **Open:** should the public Customer 360 profile redact the LLM analysis free-text by
  default? (Leaning no — it's the operator's own data, self-hosted.) Confirm at review gate.

## Out of Scope

- **CRM events** in the timeline — HubSpot (M3.1) isn't built. The event shape stays
  source-extensible so CRM rows slot in later; **no CRM code now.**
- **Customer segments** (M3.4 auto-grouping power users / silent churners / advocates) —
  heuristic-only today; excluded to avoid implying ML segmentation.
- **Bulk actions** (M3.4 export / bulk-assign / outreach) — later slice.
- **`usage_dropped`** notable event and any `customer_usage_history` table (see R1).
- **Public-API write/CRUD** — read-only only (consistent with the shipped public API, D4).
- **Real-time/streaming** timeline updates — request/response only.

## Aspect Decomposition (proposed)

1. `timeline-service-v1` — shared timeline service (port `/activity` logic + add usage/churn +
   notable-usage derivation + cursor pagination), new `GET /customers/{email}/timeline`, and
   `/activity` refactored to delegate. **Foundation; build first.**
2. `public-api-customer360` — public read endpoints: full profile, timeline, health detail
   (API-key `read` scope). Depends on (1)'s service + schemas.
3. `frontend-timeline-ui` — extend `ActivityEvent`/icons, paginated Customer Timeline card with
   "Load more", `getTimeline` client + types, profile Overview slot. Depends on (1)'s contract.
