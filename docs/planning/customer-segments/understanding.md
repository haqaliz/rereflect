# Understanding — Customer Segments (Phase 2 dig)

**Slug:** `customer-segments` · **Branch:** `feat/customer-segments` · Freeform (rereflect-next handoff, 2026-07-08)

## What this is really asking

Group customers into **rule-based behavioral cohorts** (power users, silent churners, happy
advocates, at-risk, dormant, …) computed **only from signals that already exist** — no ML — and
make the segment (a) visible as a column + filter on the Customers page and on the profile, and
(b) a *hook* that later becomes a target in automation / playbooks / copilot. Slice 1 = engine +
Customers surface. Honesty: label it a **rule-based heuristic** in the UI, exactly like churn.

## Affected areas (which services)

- **backend-api** — segment engine (new service), storage on `CustomerHealth`, list-API filter/column, serializer, config API for segment definitions.
- **worker-service** — nightly `recompute_segments` beat task.
- **frontend-web** — Customers page column + filter, `SegmentBadge`, profile badge, API-client types, (optional) a segment-definitions settings page.
- **analysis-engine** — not touched (segments read already-computed signals).

## Key code facts (from the dig, cited)

**Customer identity & storage.** Customers are **not** a table — they're the per-`(org, email)`
rollup row in `customer_health_scores` / `CustomerHealth` (`models/customer_health.py:7-86`, unique
`(organization_id, customer_email)` at :80). This is the one cached, indexed per-customer row the
list query already reads → **the natural home for a persisted `segment` value** (nullable column +
backfill), giving SQL-filterable/sortable segments with zero N+1.

**Signals available today (all no-ML):**
- `CustomerHealth`: `health_score` + components, `risk_level`, `churn_probability`,
  `confidence_level`, `feedback_count`, `last_feedback_at` (`models/customer_health.py:17-62`).
- `CustomerUsage` rollup: `last_active_at`, `active_days_7d/30d`, `distinct_feature_count`,
  `usage_score`, `events_total` (`models/customer_usage.py:47-68`); reusable named thresholds in
  `usage_score_service.py:29-85`.
- Sentiment trend (improving/declining/stable) via `compute_sentiment_trend`
  (`health_score_service.py:568-604`) — the silent-churner / declining signal.

**List API (where filter/column land):** `list_customers` at `customers.py:247-347` — add `segment`
query param + validation (near :24-27 / :252-262), a filter clause (:276-306), populate in the item
loop (:322-337), add `segment` to `CustomerListItem` (:39-50).

**Serializer / profile:** add `segment` in `serialize_customer_profile` Core block
(`customer_profile_serializer.py:57-66`) + `CustomerProfileResponse` (`customers.py:83-116`). This
serializer is shared by the internal route AND the public REST API — segment surfaces on both for
free.

**Recompute pattern:** mirror `recompute-usage-scores-daily` (task
`src.tasks.usage_metrics.recompute_usage_scores`, 04:00 UTC, `celery_app.py:194-198`) → new
`recompute_segments` at ~04:15 so it reads fresh usage/health. Health is also recomputed reactively
in `update_customer_health` (`health_score_service.py:374-517`) — segment can be set there too, so
membership updates on feedback ingest, not only nightly.

**Frontend:** Customers page uses TanStack Table + local state (not URL-synced); risk-level
`<Select>` at `app/(dashboard)/customers/page.tsx:452-467` is the filter template; queryParams
assembled :126-133. Mirror `components/customers/ChurnTimelineBadge.tsx` for a `SegmentBadge`; add a
`SEGMENT_COLOR` map in `lib/constants/churn.ts` using `--chart-*` CSS vars + `color-mix(in oklch)`.
Profile badge row at `app/(dashboard)/customers/[email]/page.tsx:647-671`. API-client edits in
`lib/api/customers.ts` (`CustomerListItem` :8-25, `CustomerListParams` :53, `list()` :232-245).

**Follow-on targeting (NOT slice 1):**
- Copilot scope + `@segment:` mention — **small, cleanest** (enum entry + one context-builder +
  regex lines; `copilot/context_resolver.py:20-25,156-163`; add segments table to SQL whitelist if
  live-queried). Fast-follow.
- Playbooks — **medium**: target is already a `CustomerHealth` predicate
  (`playbooks.py:128-157`); add a `segment` filter, but `probability_min/max` are NOT NULL with a
  CheckConstraint (`churn_playbook.py:64-102`) → needs a migration to allow segment-only playbooks.
  Fast-follow.
- Automation — **split**: segment-as-**filter/condition** on existing triggers is a small branch
  (`automation_engine.py:196-211`); segment-as-standalone-**trigger** ("entered segment X") is a
  **big lift** — the engine is event-driven with only two emitters and no membership-change event →
  **defer** until a segment-diff event source exists.

## Contradictions / corrections to the brief

- **Alembic is NOT 6 heads.** Full parse of all 60 revisions → **single head `a5b6c7d8e9f0`**
  (`add_asana_integration_tables.py`). The "6 heads" in `asana-integration/prd.md:71` no longer
  holds; a new migration just chains off `a5b6c7d8e9f0`. (Confirm with `alembic heads` in Phase 5.)
- Brief said "no per-customer computed row to store segment on" was an open question — resolved:
  `CustomerHealth` is exactly that row.

## Open questions for the interview (Phase 3)

1. **Segment set:** ship a fixed set of built-in segments (power user / silent churner / happy
   advocate / at-risk / dormant / new), or user-editable rule definitions from day one? (Built-in
   first, editable later is the lighter slice.)
2. **Overlap:** can a customer be in multiple segments (tags) or exactly one (priority-ordered
   assignment)? Single-value `segment` column is simplest; multi-segment needs a join table.
3. **Compute model:** persisted column on `CustomerHealth` + nightly recompute + on-ingest update
   (recommended), vs. computed on-the-fly at query time (no migration, but not SQL-filterable).
4. **Scope of slice 1:** engine + Customers column/filter + profile badge only? Or include the
   segment-definitions settings UI and/or a segment breakdown on the list summary?
5. **Naming/branding:** confirm the honest "rule-based" label copy and where it appears.
