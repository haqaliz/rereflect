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

### (c) recompute_usage_scores loads all customer_usage rows into memory

`recompute_usage_scores()` calls `db.query(CustomerUsage).all()`, which loads
every row across every org into a single Python list.  This is fine at current
scale but will OOM at tens of millions of rows.

Before scale: replace with a paginated or server-side cursor approach (e.g.
`yield_per(1000)` in SQLAlchemy) or push the recency-decay computation into
a single bulk UPDATE SQL statement.
