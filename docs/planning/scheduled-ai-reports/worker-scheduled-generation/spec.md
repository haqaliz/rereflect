# Aspect spec — worker-scheduled-generation

**Feature:** scheduled-ai-reports · **Aspect:** `worker-scheduled-generation`
**Source:** `docs/planning/scheduled-ai-reports/prd.md` §4.2, §5

## Problem slice & user outcome

A Celery beat task materializes each due, enabled report schedule into a real `Report` row —
exactly once per cadence window — with data sections identical to on-demand reports plus a
concise LLM narrative when the org has an LLM configured, and data-only otherwise.

## In-scope requirements

1. **Mirrored models** in `services/worker-service/src/models/__init__.py` (worker cannot
   import backend-api; `# DUPLICATED` header convention):
   - `Report` mirror of `services/backend-api/src/models/report.py` (columns incl.
     `report_metadata` mapped to column `metadata`).
   - `ReportSchedule` mirror of the backend aspect-1 model (lightweight, no FK constraints —
     the worker model convention).
2. **Mirrored data-only generator** `services/worker-service/src/services/report_generator.py`:
   copy `ReportGenerator` + the four `_query_*` builders verbatim from
   `services/backend-api/src/services/copilot/report_generator.py` (drop the copilot-only
   extraction helpers if unused), `# DUPLICATED` header. It runs against the worker's own DB
   session; tables `feedback_items` / `customer_health_scores` already exist in worker models.
3. **Narrative writer** `services/worker-service/src/services/scheduled_report_narrative.py`:
   - `generate_report_narrative(report_data, org_id, db) -> Optional[str]` — one concise,
     data-led summary paragraph per section, citing the section data; built on a short LLM
     completion. Follow the worker LLM pattern in `src/llm_client.py` (resolve org LLM via
     `src/llm/org_resolver.py`, non-streaming completion, `org_id`-scoped). Return `None` on
     any LLM failure/absence (never raise).
4. **Task** `services/worker-service/src/tasks/scheduled_reports.py`:
   - `@shared_task(name="src.tasks.scheduled_reports.generate_scheduled_reports")` — beat
     entry: iterate enabled schedules whose cadence + `hour_utc` are due; for each, atomic
     claim `UPDATE report_schedules SET last_run_at=:now WHERE id=:id AND enabled=TRUE AND
     (last_run_at IS NULL OR last_run_at < :cutoff)` — proceed only when rowcount == 1.
     Cutoffs: daily → start of today UTC; weekly → the most recent occurrence of
     `day_of_week` before now; monthly → the most recent occurrence of `day_of_month` before
     now (month without that day → skipped, documented).
   - Per-schedule `try/except` with `db.rollback()` in the handler; tally
     `{status, generated, skipped, errors}`; one failure never aborts the batch
     (`classifier_training.py:425-472` pattern).
   - Build + commit the `Report` row: `report_type`, `date_range_days`, `title`
     (`"<Type label> report — <date range label>"`), `sections`, `report_metadata`
     `{schedule_id, source: "scheduled", generated_at, date_start, date_end, model_used?}`,
     `created_by_user_id` = schedule creator id if the user still exists else NULL,
     `conversation_id` = NULL, `pdf_generated` = False.
   - After a successful commit, when `recipients` non-empty → call
     `send_scheduled_report_email(...)` (aspect `worker-email-delivery`); email failure is
     logged, never fails the run.
   - `@shared_task(name="src.tasks.scheduled_reports.generate_schedule_once")` — `(schedule_id)`
     single-schedule run, same pipeline, for the manual "Sync now" endpoint.
5. **Beat wiring** in `services/worker-service/src/celery_app.py`:
   - add `"src.tasks.scheduled_reports"` to `include` (line ~45-72);
   - beat entry `"generate-scheduled-reports"` → the task above, `crontab(minute=15)` (hourly;
     avoids the crowded top-of-hour and Monday cluster).
6. **Backend manual-run endpoint** `POST /api/v1/report-schedules/{id}/run` (admin/owner,
   org-scoped) in `services/backend-api/src/api/routes/report_schedules.py`, dispatching
   `app.send_task("src.tasks.scheduled_reports.generate_schedule_once", args=[schedule_id])`
   via `src/background/celery_client.py` (exact dotted-name convention).

## Out-of-scope boundaries

- No email implementation (aspect 3 owns it; this aspect only calls the fixed signature).
- No backfill of missed windows; no multi-window reports; no custom ranges/types.

## Acceptance criteria (testable)

- Worker `pytest tests/test_scheduled_reports.py`:
  - daily/weekly/monthly due-filtering incl. hour boundary and month-31 skip;
  - exactly-one-per-window: invoking the task twice for the same window yields one Report
    (claim-by-rowcount); a concurrently "claimed" schedule is skipped;
  - disabled schedules skipped; empty-recipients → no email call; email failure → run still
    succeeds; narrative present when LLM mocked, absent (data-only) when LLM none/fails;
  - Report row content incl. `report_metadata` tags and `created_by_user_id` NULL when the
    creator user is gone; per-schedule exception isolation + rollback (one bad schedule does
    not abort others).
  - `test_beat_schedule_integrity.py` auto-covers the new beat entry (registration, name,
    include) — do not weaken it.
- Backend: `POST /{id}/run` dispatches the exact dotted name (mocked `send_task`).
- Full worker + backend suites green.

## Dependencies & sequencing

- Depends on aspect `backend-schedule-crud` (table + contract) and aspect
  `worker-email-delivery` (sender signature). Build last among the four.

## Open questions / risks

- **Mirror divergence (highest risk):** copy the generator verbatim, keep the `# DUPLICATED`
  header, and pin it with a characterization test on a fixed seeded dataset (deterministic
  raw-SQL output) so a future drift is caught by a failing worker test.
- LLM narrative reuse: prefer the existing worker `llm_client` completion path; if it has no
  generic completion helper, add a small `generate_report_narrative` there following the
  same resolve→call→return-None-on-failure shape.