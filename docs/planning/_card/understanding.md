# Understanding — feat/customer-360-unified-timeline (Phase 2 deep dig)

## Headline finding: this is NOT greenfield

The brief (via `rereflect-next`) assumed "nothing stitches the event sources together."
**That's wrong** — a customer activity timeline already exists and merges 5 sources.
The real gap is narrower and more honest. Surfacing this contradiction up front.

### What already exists

- **`GET /api/v1/customers/{email}/activity`** → `CustomerActivityResponse{ events: ActivityEvent[] }`
  (`services/backend-api/src/api/routes/customers.py:512-611`). It already merges:
  - `feedback_created` (from `feedback_items.created_at`)
  - `status_changed` (from `feedback_workflow_events`, `event_type="status_changed"`)
  - `health_score_changed` (from `customer_health_history.recorded_at`, with old→new score)
  - `llm_analysis_generated` (from `customer_health.llm_analyzed_at`)
  - `action_completed` (from `customer_analysis_actions.completed_at`, status completed/dismissed)
- **It is capped, not paginated**: each source is `.limit(10)`, merged, sorted desc, then `events[:10]`.
  Docstring literally says *"Get last 10 mixed activity events."* No `page`/`page_size`/cursor.
- **Frontend already renders it**: `ActivityTimeline` (`components/customers/ActivityTimeline.tsx`)
  on the profile **Overview tab** as a "Recent Activity" card
  (`app/(dashboard)/customers/[email]/page.tsx:795-803`). It has an icon-per-type system,
  loading skeleton, and empty state. `customersAPI.getActivity(email)` in `lib/api/customers.ts`.

### What's genuinely missing (the actual work)

1. **Usage events are NOT a timeline source.** M3.2 usage data (`usage_events`,
   `customer_usage`) just shipped (`a8047d9`) but the activity endpoint predates it and
   ignores it. The `ActivityEvent` union has no usage type. **This is the freshly-unblocked
   gap that motivated the pick.**
2. **Churn events are NOT a timeline source.** `customer_churn_events` (M4.1) exists
   (`models/churn_event.py`) — manual/CSV/auto churn marks with `churned_at` + `recovered_at`
   — but aren't in the timeline.
3. **No full, paginated, browsable timeline.** "Recent Activity" is a 10-item widget.
   M3.4's intent ("unified customer timeline ... in chronological order") is a browsable
   history. Need pagination (or "load more") over the merged sources.
4. **No public-API surface.** The activity endpoint is v1/JWT only, behind
   `require_feature("customer_health_scores")`. M3.4 also calls for a **Customer 360 API +
   health-score API for programmatic/external consumption**. Public API
   (`routes/public_api.py`, API-key + `require_scope("read")`) currently has `/customers`
   (list) and `/customers/{email}/health` — but **no full Customer 360 profile** and **no
   timeline**.

## Reframed scope (to confirm in the interview)

This slice = **extend the existing activity timeline into a true unified, paginated timeline**
(add usage + churn sources), **+ expose read-only Customer 360 / health-score (and possibly
timeline) endpoints on the public API.** Build on the existing `ActivityEvent` / `ActivityTimeline`
patterns rather than inventing parallel ones.

## Event sources — confirmed data shapes & timestamps

| Source | Table / model | Timeline timestamp | Org scope | Notes |
|---|---|---|---|---|
| Feedback | `feedback_items` | `created_at` (ingest) | `organization_id` | sentiment/category/churn_risk_score/is_urgent available |
| Health score change | `customer_health_history` | `recorded_at` | `organization_id` | one row per ≥2pt change or risk-level change; has old→new |
| Status change | `feedback_workflow_events` | `created_at` | `organization_id` | `event_type="status_changed"`, `new_value` |
| LLM analysis | `customer_health.llm_analyzed_at` | that column | `organization_id` | single latest, not historical |
| Action completed | `customer_analysis_actions.completed_at` | that column | — (via health_id) | completed/dismissed |
| **Usage (NEW)** | `usage_events` (raw) / `customer_usage` (rollup) | `occurred_at` / `updated_at` | `organization_id` | **raw events are HIGH-VOLUME** (every track/identify) — see open Q |
| **Churn (NEW)** | `customer_churn_events` | `churned_at` (+ `recovered_at`) | `organization_id` | reason_code, source manual/csv/auto |

## Conventions to reuse

- **v1 pagination**: `page` (≥1), `page_size` (1–100), `sort_by`, `sort_order`; org via
  `get_current_org` (JWT → `current_user.organization`).
- **Public API**: `verify_api_key` + `require_scope("read")` (`api/public/auth.py:74-129`),
  `rrf_` keys, org resolved from key. Add new read endpoint mirroring
  `/customers/{email}/health` (`routes/public_api.py:343-364`).
- **Frontend**: `ActivityEvent` discriminated union + `eventIconMap` (extend with usage/churn
  icons), React Query (`useQuery`), Card/Skeleton/Badge, Sunset-Horizon CSS vars + `color-mix`
  (no hardcoded colors). Precedent feed UIs: `ActivityTimeline.tsx`, `NotificationBell.tsx`.

## Open questions for the requirements interview (Phase 3)

1. **Extend `/activity` or add a new `/timeline` endpoint?** Options: (a) add a separate
   paginated `GET /customers/{email}/timeline` and keep `/activity` as the capped 10-item
   widget; (b) refactor `/activity` to delegate to a shared timeline service with `limit=10`.
   Recommend (a)+(b): one service, two entry points.
2. **How to represent usage in the timeline without flooding it?** Raw `usage_events` are
   per-track-event (could be thousands). Options: (a) raw events (noisy), (b) **notable usage
   events only** — first-seen, reactivation-after-dormancy, first-use-of-feature, usage-drop;
   (c) daily/weekly buckets. Leaning (b)/(c). **Needs a decision.**
3. **Pagination strategy:** offset `page/page_size` (matches house style but awkward across a
   merged multi-source UNION) vs **cursor by timestamp** (cleaner for heterogeneous merge).
4. **Churn representation:** emit `recovered_at` as a separate "recovered" event? Churn is
   near-terminal — does the timeline keep accumulating after it?
5. **Public API scope:** which exactly — full Customer 360 profile endpoint, health-score
   endpoint, and/or the timeline itself? (`/customers/{email}/health` already exists.)
6. **`require_feature` gate:** the v1 activity/customer routes sit behind
   `require_feature("customer_health_scores")`. OSS self-hosted unlocks everything — confirm
   the new endpoints follow the same (now no-op) gate or drop it.

## Affected files (anchor list for plan)

- Backend: `routes/customers.py` (timeline endpoint + schemas), new `services/customer_timeline_service.py`,
  `routes/public_api.py` (+ `api/public/auth.py` patterns), models already exist (no new tables expected).
- Frontend: `components/customers/ActivityTimeline.tsx` (extend) or new `CustomerTimeline.tsx`,
  `lib/api/customers.ts` (+ types), profile page Overview tab.
- Likely **no migration** — all source tables exist. Confirm in plan.
