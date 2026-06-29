# Aspect Spec — `timeline-service-v1`

**Parent PRD:** `../prd.md` · **Slug:** `customer-360-unified-timeline`
**Build order:** 1 of 3 (foundation; blocks the other two)

## Problem slice & outcome

Today `GET /api/v1/customers/{email}/activity` merges 5 sources inline and truncates to 10
(`routes/customers.py:512-611`). Usage (M3.2) and churn (M4.1) are absent and there is no
paging. Outcome: a **shared timeline service** producing a reverse-chronological, cursor-paged,
source-extensible event stream — exposed via a new `/timeline` endpoint and reused by `/activity`.

## In scope

- **New** `services/customer_timeline_service.py` — `build_timeline(db, org_id, email, before=None, limit=20)`
  returning `(events, next_cursor)`. `events` is a list of timeline-event dicts/objects;
  `next_cursor` is an opaque ISO-timestamp-based string or `None`.
- **Sources merged:**
  - Existing 5: `feedback_created`, `status_changed`, `health_score_changed`,
    `llm_analysis_generated`, `action_completed` — ported verbatim in meaning from `/activity`.
  - `churned` (from `customer_churn_events.churned_at`, include `reason_code`/`reason_text`),
    `churn_recovered` (from `recovered_at` when set).
  - Notable usage: `usage_first_seen` (`customer_usage.first_seen_at`), `usage_reactivated`
    (an event after a ≥ `DORMANCY_DAYS=14` gap in `usage_events`), `usage_feature_adopted`
    (first `occurred_at` per distinct feature — **reuse the M3.2 feature-extraction helper**,
    don't re-derive).
- **New** `GET /api/v1/customers/{email}/timeline?before=<iso>&limit=<n>` (default limit 20,
  max 100), org-scoped via `get_current_org`, JWT. Response:
  `{ events: [TimelineEvent], next_cursor: <iso|null> }`.
- **Refactor** `get_customer_activity` to call `build_timeline(..., limit=10)` and return the
  existing `CustomerActivityResponse{events}` shape (drop the old inline querying).
- **TimelineEvent Pydantic schema** — superset of today's `ActivityEvent`: `type`,
  `timestamp`, `description`, plus optional typed payload fields (`feedback_id`, `old_score`,
  `new_score`, `risk_level`, `reason_code`, `feature_name`, `source` discriminator). Keep it
  source-extensible (a future `crm_*` type needs no migration).
- **Cursor & ordering:** sort `(timestamp DESC, type ASC, source_id ASC)`; each per-source
  query applies `WHERE <ts> < before` (when paging) `ORDER BY <ts> DESC LIMIT limit`;
  Python k-way merge; truncate to `limit`; `next_cursor` = last emitted event's timestamp (and
  tiebreak) or `None` when fewer than `limit` remain.

## Out of scope

- Public API endpoints (aspect 2). Frontend (aspect 3). `usage_dropped` (needs history table).
- Any new table/migration — all sources exist.

## Acceptance criteria (testable, TDD)

1. `build_timeline` returns events from **all** sources interleaved in correct desc time order
   (test fixture with one of each source at known timestamps).
2. `usage_reactivated` fires only after a ≥14-day gap; back-to-back events do **not** produce one.
3. `usage_feature_adopted` emits exactly once per distinct feature, at its first occurrence.
4. `churned` and `churn_recovered` appear with `reason_code` / recovery time respectively.
5. Paging: `limit=N` returns ≤N + `next_cursor`; following the cursor yields the next slice
   with **no duplicate and no skipped** events, including when two events share a timestamp (R4).
6. `next_cursor` is `null` on the last page.
7. `GET /activity` still returns `{events}` ≤10 with the **same field shape** as before, now
   including usage/churn rows; existing `/activity` tests still pass (or are updated only where
   they asserted the *absence* of usage/churn).
8. All queries filter `organization_id`; an event for another org never appears (cross-tenant test).

## Dependencies & sequencing

- None upstream. Produces the service + `TimelineEvent` schema consumed by aspects 2 & 3.
- Confirm the M3.2 feature-extraction helper location (`worker-service` usage_metrics vs a
  shared util) before implementing `usage_feature_adopted`; if worker-only, lift the pure
  function into `backend-api` or a shared module.

## Risks

- R2 (usage scan volume), R3 (feature attribution reuse), R4 (cursor tiebreak) — from PRD.
- Porting `/activity` must not change its external contract — characterization test first.
