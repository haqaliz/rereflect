# Aspect Spec — rollup-rewindow-fix

Parent PRD: `../prd.md`

## Problem slice & outcome

The rolling-window fields on `customer_usage` (`active_days_7d/30d`, `login_count_7d/30d`) are
computed only when an event arrives, so for a customer whose event rate falls they **freeze at
their last-event values forever**. Only recency moves with time.

Outcome: those fields re-derive against the current time on every daily run, so a customer who
goes quiet — or merely slows down — is reflected in `usage_score`, in segment classification,
and (via later aspects) in trend detection.

## Evidence (observed, verified in this worktree)

- `_compute_rollup_from_events` computes the windows against `now`
  (`worker-service/src/tasks/usage_metrics.py:39-89`) and has **exactly one call site**, on the
  event path (`:208`).
- `recompute_usage_scores` (`:306-355`) calls only `compute_usage_score(row, now)` — it never
  re-derives the window fields.
- `silent_churner` gates on `active_days_30d < FREQUENCY_LOW_MOD_DAYS` (=5)
  (`backend-api/src/services/segment_service.py:120-130`), so it is **unreachable** for a
  customer whose `active_days_30d` is frozen high.
- The existing test passes only because its fixture hand-sets `active_days_30d=0`
  (`worker-service/tests/test_usage_metrics.py:359`) — it presupposes the re-windowing that does
  not happen.

## In scope

- Re-derive `active_days_7d`, `active_days_30d`, `login_count_7d`, `login_count_30d` and the new
  `active_days_14d` inside the daily `recompute_usage_scores` pass, from `usage_event` rows,
  against the run's `now`.
- Add `active_days_14d` to `customer_usage` (nullable, populated by the first daily run or the
  next event) + Alembic migration.
- Extend `_compute_rollup_from_events` to also produce `active_days_14d`, keeping it the single
  source of truth for window derivation (both the event path and the daily path must use it —
  no second implementation).
- Fix `test_stale_rollup_score_drops_on_recompute` so its fixture reflects reality (a frozen,
  *high* `active_days_30d`) and therefore actually exercises the bug.
- Characterization test locking health-score byte-stability for orgs at `health_weight_usage = 0`.
- Keep the duplicated `usage_score_service` copies (backend-api + worker-service) in sync if
  touched; see PRD "Duplicated service modules".

## Out of scope

- The snapshot table (`usage-history-snapshot`).
- Trend state/pct and the health penalty (`trend-detection-and-health`).
- Any frontend change (`frontend-trend-and-weights`).
- D2 (`usage_event` retention / O(lifetime) reprocessing) and D3 (swallowed enqueue) — the daily
  re-derivation reads `usage_event` per customer and inherits D2's cost characteristics. Do not
  fix D2 here; do note the read pattern in the plan.

## Acceptance criteria (testable)

1. A customer with a rollup showing `active_days_30d = 25` and no events in the last 30 days has
   `active_days_30d == 0` after one `recompute_usage_scores` run.
2. That same customer's `usage_score` drops (frequency term no longer inflated), and
   `update_customer_health` is invoked when the delta ≥ `_HEALTH_RECOMPUTE_DELTA`.
3. A previously-active customer who has gone quiet classifies as `silent_churner` after the
   daily run, given the segment's other conditions hold. (Directly proves the unreachability is
   gone.)
4. A customer with steady, current activity has **unchanged** window fields after a run
   (idempotent; no spurious churn of values).
5. `active_days_14d` is populated for every scanned row after one run.
6. Running the task twice in succession produces identical rollup values (idempotency).
7. **Byte-stability:** for an org with `health_weight_usage = 0`, health scores before and after
   the change are identical for a fixture spanning active, quiet, and no-usage customers.
8. The repaired `test_stale_rollup_score_drops_on_recompute` fails against the pre-fix
   implementation (RED proves the bug) and passes after.

## Dependencies & sequencing

- **First aspect.** Nothing depends on it landing, and everything else depends on it being
  correct — a trend computed from frozen fields is meaningless.
- Independently valuable and independently shippable: it repairs `silent_churner` and corrects
  inflated scores on its own.
- Alembic is **single-head** in this repo; run a live `alembic heads` before authoring the
  migration (static parsing has repeatedly produced a false "multiple heads" reading).

## Open questions / risks

- **Cost:** re-deriving windows for every rollup row daily means a per-customer `usage_event`
  read across the whole table. With D2 unfixed (no retention, unbounded table) this is the
  aspect most exposed to that debt. The plan should choose a bounded read (e.g. only events
  within the widest window, 30 days) rather than the event path's unbounded
  full-history fetch — the daily pass does **not** need lifetime aggregates.
- `events_total`, `first_seen_at`, `distinct_features` are **lifetime** aggregates and must NOT
  be recomputed from a bounded read, or they will be silently truncated. Only the windowed
  fields are re-derived here.
- Scores will change for orgs that opted into usage weighting — deliberate, documented in the
  PRD as a correction.
