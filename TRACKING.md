# Rereflect — Development Tracking Notes

---

## Product Usage Enrichment — follow-ups

> Added: 2026-06-28 (aspect 3 fix wave 1)

### (a) PRE-EXISTING: churn_calibration.py beat tasks appear undecorated/unregistered

`services/worker-service/src/tasks/churn_calibration.py` defines `refit_all_orgs`,
`refit_global_calibration`, and `purge_old_calibration_models` as plain Python
functions without `@shared_task` decorators.  The beat schedule in `celery_app.py`
dispatches all three by dotted name — they will raise `celery.exceptions.NotRegistered`
at runtime and silently never execute.

Action: audit all beat-scheduled tasks against a live worker startup log
(`celery inspect registered`), add `@shared_task(name="<dotted.name>")` to any
undecorated function, and add a registration assertion test for each.
This is a pre-existing issue unrelated to the product-usage-enrichment feature;
handle in a dedicated fix pass to avoid scope creep.

### (b) usage_score_service.py is duplicated across backend-api and worker-service

`services/backend-api/src/services/usage_score_service.py` and
`services/worker-service/src/services/usage_score_service.py` are byte-identical.
Both files now carry a `# DUPLICATED` header comment as a reminder.

If the scoring logic diverges in future, migrate to a shared internal package
(e.g. `packages/usage-score/`) consumed by both services, or expose it via a
lightweight RPC call so there is a single source of truth.

### (b2) segment_service.py is duplicated across backend-api and worker-service

`services/backend-api/src/services/segment_service.py` and
`services/worker-service/src/services/segment_service.py` are byte-identical
(same reasoning as (b) — the pure `classify_segment` classifier is needed by the
backend on ingest and by the worker's nightly `recompute_segments` task). Both
carry a `# DUPLICATED` header. Keep them in sync; same shared-package migration
path as (b) applies. Note the worker also mirrors the `segment` column on its
`CustomerHealth` model (`src/models/__init__.py`, "catch-up" convention).

### (c) recompute_usage_scores loads all customer_usage rows into memory

`recompute_usage_scores()` calls `db.query(CustomerUsage).all()`, which loads
every row across every org into a single Python list.  This is fine at current
scale but will OOM at tens of millions of rows.

Before scale: replace with a paginated or server-side cursor approach (e.g.
`yield_per(1000)` in SQLAlchemy) or push the recency-decay computation into
a single bulk UPDATE SQL statement.

---

## Product Usage Enrichment — final-review follow-ups

> Added: 2026-06-29 (final-review fix wave)

### (d) I-list-column: last_active_at (product usage) now surfaced on customer list — DONE

`CustomerListItem` previously lacked a `last_active_at` field; the frontend column
always displayed "—".  Fixed: `last_active_at: Optional[datetime] = None` added to
`CustomerListItem`; `list_customers` fetches `customer_usage` rollup rows for the
current page's emails in a single bulk query (keyed by email dict — no N+1) and
populates the field per-item; org-scoped; customers without a rollup row → `None`.
Covered by 4 new TDD tests in `tests/test_customers.py::TestCustomerListLastActiveAt`.

### (e) MINOR OPEN — raw usage_event 90-day retention/purge task not yet shipped

The `usage_events` raw-log table has no purge/retention job.  At sustained ingest
rates the table will grow without bound.  Recommended: add a nightly Celery beat task
that deletes `usage_events` rows older than 90 days (configurable via env), similar to
the existing `purge_old_calibration_models` pattern.  Block on confirming data-retention
policy before implementing.

### (f) MINOR OPEN — process_usage_event re-aggregates all events per invocation (write amplification)

`_do_process_usage_event` (worker-service) recomputes the entire rollup by scanning
all historical events for a customer each time a single new event arrives.  At scale
this is O(events_total) work per new event.  Preferred fix: incremental upsert — read
the existing `customer_usage` row, apply deltas for the new event only, write back once.
Worth revisiting when per-customer event counts exceed ~10 k.

### (g) MINOR OPEN — _compute_rollup_from_events uses tz-naive datetime comparisons

`_compute_rollup_from_events` compares `event.occurred_at` (which may be tz-aware UTC
after the AC fix in the ingest route) against `datetime.utcnow()` (tz-naive).  If
tz-aware datetimes ever reach the worker (e.g., stored with tzinfo from a future
migration), the comparison will raise `TypeError: can't compare offset-naive and
offset-aware datetimes`.  Fix: replace `datetime.utcnow()` with
`datetime.now(timezone.utc)` and strip tzinfo only when comparing against tz-naive
columns.

### (h) MINOR OPEN — /usage time series is sparse (no zero-fill between active days)

`GET /api/v1/customers/{email}/usage` returns only days that have at least one event.
The frontend charts may render discontinuous series or misalign the x-axis.  Consider
zero-filling the series to cover every calendar day in the requested window, even when
event_count = 0, so charting libraries can render a continuous baseline.
