# Aspect Spec — usage-rollup-and-score

Parent PRD: `../prd.md`

## Problem slice & outcome

Raw usage events become a per-customer rollup with a 0-100 `usage_score` (recency + frequency + breadth), recomputed as events arrive and on a schedule, so a customer going quiet lowers their score even with no new feedback.

## In scope

- `customer_usage` model (rollup, one per `(organization_id, customer_email)`): `last_active_at`, `login_count_7d/30d` (or session/active-day counts), `active_days_7d/30d`, `distinct_features` (JSON list) + `distinct_feature_count`, `usage_score` (0-100), `events_total`, `first_seen_at`, `updated_at`. Unique `(organization_id, customer_email)`. Alembic migration (separate from `usage_event`).
- Celery task `services/worker-service/src/tasks/usage_metrics.py::process_usage_event` (`@shared_task`, retries; mirror `source_events.py:18-30`): persist/refresh the raw event (full dedup), upsert the rollup, recompute `usage_score`, trigger `update_customer_health()` for that customer.
- `compute_usage_score(rollup, now) -> int` in a backend service module reused by both worker and read API. Mapping mirrors `_compute_resolution_component` style:
  - **Recency** (last_active_at): ≤2d→high … >30d→low.
  - **Frequency** (active_days_30d or logins): more active days → higher.
  - **Breadth** (distinct_feature_count): more distinct features → higher.
  - Weighted blend → 0-100; **no data ⇒ 50 (neutral)**.
- Scheduled recompute: a periodic task that re-derives `usage_score` (recency decays over time) for customers with a rollup. Hook into the existing scheduler used for churn calibration (`worker-service` beat).
- Read API: `GET /api/v1/customers/{email}/usage?days=30` → rollup snapshot + a time series (events bucketed by day) for the chart. Org-scoped via JWT (dashboard auth, not the ingest key).

## Out of scope

- The health component wiring + weight column (aspect `health-component`) — though this aspect *calls* `update_customer_health()`.
- Ingestion endpoint (aspect `ingestion-receiver`).
- Frontend chart/card (aspect `frontend-surface`).

## Acceptance criteria (testable)

1. `process_usage_event` with a `track` event upserts a `customer_usage` row (`events_total` increments, `last_active_at` advances, feature added to `distinct_features`).
2. Re-processing the same `messageId` does not double-count (idempotent).
3. `compute_usage_score`: recent+frequent+broad usage → high (>70); stale (last active >30d) → low (<40); **no rollup → 50**.
4. Scheduled recompute lowers `usage_score` for a customer whose `last_active_at` has aged past the recency thresholds, with no new events.
5. `process_usage_event` calls `update_customer_health(org_id, customer_email, db)` exactly once per processed event (assert via mock).
6. `GET /customers/{email}/usage` returns rollup + daily time series, scoped to the caller's org; 404 for an email with no usage.

## Dependencies & sequencing

- Depends on `ingestion-receiver` for live events but the **task + model + score are independently testable** with synthetic events.
- `health-component` must define `update_customer_health` tolerance: calling it before the usage weight exists is safe (weight 0). Land `health-component` first so the recompute path is coherent, but this aspect does not block on the 5th-component math.

## Open questions / risks

- "Login" vs generic "active day": slice 1 treat any `track`/`identify` as activity; reserve specific `event=login` counting as a refinement. Decide concrete metric set in the plan.
- Recency decay cadence for the scheduled recompute (daily?) — pick to match existing beat schedule.
