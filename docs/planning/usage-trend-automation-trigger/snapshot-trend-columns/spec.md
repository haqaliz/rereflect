# Aspect — `snapshot-trend-columns`

**Slice:** persist trend state on the daily usage snapshot, so a trend *change* has a durable
backing row the timeline can derive from.

**PRD requirement:** M3.

---

## Problem slice & outcome

`customer_usage` holds only the *current* trend state; `customer_usage_history` carries no trend
columns at all. The timeline is assembled at read time from durable rows (F6), so without this
aspect there is nothing for a `usage_trend_change` event to be derived from.

Outcome: every daily snapshot row records the trend state and pct that were in effect for that
customer on that date.

## In scope

1. Add to `services/backend-api/src/models/customer_usage_history.py` (currently :48-55):
   - `usage_trend_state` — `String(30)`, **nullable** (pre-existing rows have no value)
   - `usage_trend_pct` — `Float`, nullable
2. Additive Alembic migration (no data migration, no backfill).
3. Mirror both columns on the worker's model
   (`services/worker-service/src/models/__init__.py:1004-1032`).
4. **Fix the payload ordering defect.** The snapshot payload is assembled at
   `services/worker-service/src/tasks/usage_metrics.py:563-573`, *before* trend classification
   at `:583-593`. Written naively the snapshot records the **previous** state. Build or amend
   the payload after classification so the snapshot and the `customer_usage` row agree for the
   same date.

## Out of scope

- Backfilling trend state onto existing snapshot rows (they stay `NULL`).
- Any read/derivation of transitions — that is `timeline-trend-event`.
- Changing retention (180 days) or the prune task.

## Acceptance criteria

- **AC1** — Both columns exist, are nullable, and a row written without them succeeds.
- **AC2** — `test_worker_and_backend_customer_usage_history_columns_match` (the existing
  column-parity guard) stays green.
- **AC3** — After one `recompute_usage_scores` run, for every customer the snapshot row's
  `usage_trend_state` **equals** the `customer_usage` row's `usage_trend_state` for that date.
  This is the regression test for the ordering defect and must fail before the fix.
- **AC4** — A customer whose trend changes on day N has a snapshot for day N carrying the
  **new** state, and a snapshot for day N-1 carrying the old one.
- **AC5** — Migration `upgrade()` then `downgrade()` round-trips cleanly; pre-existing rows are
  untouched and read back `NULL`.
- **AC6** — `tests/test_usage_trend_churn_boundary.py` unchanged and green.

## Dependencies & sequencing

None — this is the foundation aspect. `timeline-trend-event` depends on it.
Migration precedent: `alembic/versions/a5b63dbbce9b_add_usage_trend_fields.py` (the M3.2b
additive migration) is the closest template, including its downgrade shape.

## Risks / open questions

- The snapshot write runs in a **separate, later transaction** (`usage_metrics.py:625`) from the
  trend commit (`:611`) and is caught-and-logged on failure (`:627-633`). AC3 holds for a
  successful run; a failed snapshot write leaves the day with no row at all (not a wrong row),
  which is the accepted divergence documented as PRD R1.
- `_write_usage_history_snapshots` uses `bulk_insert_mappings` in 1000-row chunks
  (`usage_metrics.py:221-276`) — the payload dict keys must match the new column names exactly;
  `bulk_insert_mappings` will not error on a stale key set, it will simply omit the columns.
