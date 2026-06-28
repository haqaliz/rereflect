# Understanding — Product Usage Enrichment (Phase 2 dig)

Synthesized from three read-only dig agents (health/churn scoring, webhook/ingest+auth, frontend Customer 360). All paths relative to the worktree.

## What the feature really asks

Add a **real product-usage signal** (logins, feature usage, last-active per customer) into Rereflect and feed it into the customer health score — the canonical leading churn indicator that is currently **absent**. First slice = inbound usage-event receiver → per-customer usage aggregates → a usage component in health + a usage section on the customer profile.

## The confirmed gap (the whole reason this is high-leverage)

`services/backend-api/src/services/health_score_service.py:435-471` — the existing **"frequency" component measures feedback complaint cadence**, not product usage (last-7d vs 30d *feedback* count). There is **no product-usage input anywhere** in the health score or the 9-factor churn scorer. The customers list "Last Active" column (`customers/page.tsx:304`) is `last_feedback_at` — also feedback-derived, not usage. So a genuine usage signal is net-new.

## How customers + health are modeled (no Customer table)

- A "customer" = **`customer_email`**, scoped per org. No dedicated table.
- `customer_health_scores` (`models/customer_health.py`) — unique on `(organization_id, customer_email)` (`:78`). Holds `health_score`, the 4 `*_component` columns, `risk_level`, confidence, churn probability/CI/bucket, LLM analysis.
- `customer_health_history` (`models/customer_health_history.py`) — snapshots each component on score change ≥2 pts.

## Health score internals

- 4 components, default weights in `health_score_service.py:24-29` — churn_risk .35, sentiment .25, resolution .25, frequency .15.
- Per-org weights in `org_ai_config` table (`models/org_ai_config.py:18-21`: `health_weight_churn/sentiment/resolution/frequency`, INT %). Read by `_get_org_weights()` (`:32-46`).
- **Sum-to-100 validation** in `api/routes/categories.py:185-190` (Pydantic `model_validator`); GET/PUT at `:193-238`.
- Each component returns **50 (neutral) when it has no data** — built-in degrade pattern.
- Recompute trigger: `analyze_single_feedback` Celery task → `_analyze_feedback_item` → `update_customer_health()` (worker `analysis.py:408-416`) → `compute_health_score()` → health-drop alert (`health_score_service.py:473-540`).

### → Adding a 5th "usage" component (caveat resolution)

The caveat (re-weighting + don't double-count) resolves cleanly with **two layers of safe degradation**:
1. **Add** a 5th component (don't replace the feedback-"frequency" one — different signal). New `health_weight_usage` column **defaulting to 0**, so *existing orgs' scores are mathematically unchanged* until an operator opts in by re-weighting (sum still 100).
2. `_compute_usage_component()` returns **50 (neutral)** for customers/orgs with no usage events — mirrors the existing per-component no-data behavior. So even at a non-zero weight, no-usage customers aren't penalized.

Touch list for the component: `org_ai_config` (+column, migration), `_get_org_weights`, new `_compute_usage_component`, `compute_health_score` aggregation, `categories.py` validation (5 weights → 100), `customer_health_scores.usage_component` (+column), `customer_health_history.usage_component` (+column), frontend `ComponentProgressBars` (5th bar).

## 9-factor churn scorer (optional v2 hook)

`worker-service/src/tasks/analysis.py:566-833` `_compute_heuristic_churn_risk` — 9 weighted factors incl. a `feedback_frequency` factor (again feedback cadence). A usage factor could be added here later, but the **health component is the cleaner first slice** (usage already flows into churn indirectly via health). Keep churn-scorer changes out of slice 1.

## Inbound ingestion (the receiver)

- **Reuse the public API-key system** for auth: `verify_api_key` + `require_scope("ingest")` (`api/public/auth.py:74-129`), already org-scoped via `auth.organization_id`. No new secret scheme; an operator mints an ingest-scoped key (`models/api_key.py`, scopes col `:22`). This beats a hardcoded env secret for multi-tenant + matches existing `/api/public` feedback ingest (`public_api.py:212-242`).
- New router `api/routes/usage_webhooks.py`, prefix `/api/v1/webhooks/usage` (or under `/api/public/v1/usage` to sit with ingest — decide in PRD), registered in `api/main.py` (include_router pattern `:226-296`).
- Pattern: **Route → auth/validate → dedup → queue Celery → 200**. Dedup via unique constraint on `(org, external_event_id)` like `feedback_source_event.py:35-40`.
- Celery task `worker-service/src/tasks/usage_metrics.py::process_usage_event` (`@shared_task`, mirror `source_events.py:18-30`); enqueue by name via `get_celery_app().send_task(...)`.
- New model(s): a raw `usage_event` log (JSON payload, dedup key) + a per-customer rollup (logins, feature-event count, last_active_at, derived usage_score). Alembic head = **`y4z5a6b7c8d9`** (new `down_revision`).

## Frontend surfaces

- Profile page `app/(dashboard)/customers/[email]/page.tsx` — new "Usage Activity" Card slots after Health Timeline (`~:688`). Data via new `customersAPI.getUsage(email, days)` (`lib/api/customers.ts` pattern `:163-231`; axios bearer interceptor `lib/api-client.ts:14-29`).
- `components/customers/ComponentProgressBars.tsx:16-21` — add 5th `{key:'usage'}` entry + tooltip; needs `usage_component` on `CustomerProfileData`.
- `components/customers/HealthTimeline.tsx` — copy to `UsageTimeline.tsx` (Recharts LineChart, period toggle).
- Operator setup UI: surface the ingest API key + the usage webhook URL/schema (reuse `settings/` patterns; NOTE the existing `settings/webhooks` page is **outbound** delivery — our receiver is inbound, so this is new copy, not that page's CRUD).

## Stale-doc guardrails honored

- Ignore plan-gating / `PLAN_WEBHOOK_LIMITS` / Pro+ tiers (pre-pivot, OSS = all unlocked).
- No vendor OAuth; receiver is a plain authenticated POST endpoint (self-hosted-first).

## Genuine product decisions to settle in the interview

1. **Endpoint shape & schema** — accept Segment `identify`+`track` verbatim, or a normalized `{event, userId/email, name, timestamp, properties}` subset (Segment-compatible but simpler)? Mount under `/api/v1/webhooks/usage` vs `/api/public/v1/usage`?
2. **Customer matching** — map Segment `email` trait (or `userId`) → existing `customer_email`. What happens to events with no resolvable email (drop, or store anonymous)?
3. **Which metrics define `usage_score`** in slice 1 — recency of last-active + login frequency + distinct-feature count? Need a concrete 0-100 mapping (like the resolution/frequency mappings).
4. **Default usage weight** — confirm 0 (opt-in re-weight) vs a small default like 10 (auto-reduce others). Recommend 0 for zero-surprise upgrades.
5. **Retention** — how long to keep raw usage events vs just the rollup.
