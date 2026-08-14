# Aspect spec — Worker write-back task

**Feature:** `intercom-writeback` (prd.md R3 + R5) · **Aspect:** `worker-writeback-task`

## Problem slice

The core execution unit: given an org + the feedback ids that just transitioned to
`resolved`, append a note to each linked Intercom conversation and close it — guarded,
idempotent, honest about failures, and visible on the timeline. Must never raise, and
must reuse the worker's own models/client (worker cannot import backend-api).

## In-scope

- New `services/worker-service/src/tasks/intercom_writeback.py` with the
  extracted-`_body` pattern (precedent: `src/tasks/hubspot_writeback.py`, including
  injectable client + direct body invocation in tests; `_body(task_self, db, org_id,
  payload)`).
- Task signature: `push_resolved_writeback` receiving `(org_id, items)` where `items`
  is `[{"id": int, "resolution_note": str|None}]` (dispatch payload from
  `dispatch-seams`). Registered with the `src.`-prefixed name the dispatch uses
  (beat-registration lesson: the name must exactly match `send_task`'s dotted string).
- Per-item guard chain (each → recorded `noop`/`skipped` outcome, nothing sent):
  1. Item not found / wrong org → `noop/not_found`.
  2. `source != "intercom"` or no `conversation_id` in `source_metadata` → `noop`.
  3. `intercom_writeback_at` already set → `noop/already_written`.
  4. No Intercom connection for the org — token-paste `IntercomIntegration` first, then
     legacy `Integration(type="intercom")` OAuth row (source_events.py:190-227
     OR-clause precedent) — → `noop/no_connection`.
  5. `writeback_enabled` false → `noop/writeback_disabled`.
  6. Missing `LLM_ENCRYPTION_KEY` (decrypt fails) → `error/missing_encryption_key`, no
     retry, recorded on the row (CRM R6 contract).
  7. Missing admin id (both stored `admin_id` fields absent and `fetch_admin_id`
     fails) → `error/no_admin`, recorded, no retry.
- Act per `writeback_action`: note first (body = `resolution_note` or default
  `"Marked resolved in Rereflect."`), then close when `note_and_close`.
- Error semantics: `IntercomAuthError` (401/403) → record `missing_write_scope` (or
  `auth_error`) in `last_writeback_status`, **never** flip `is_active` (soft-pause
  precedent); not-found sentinel (404) → `noop/already_closed`; `IntercomTransientError`
  (429/5xx) → `task_self.retry` (max 3, delay 30).
- On success: set `feedback_items.intercom_writeback_at` (timestamp), update
  `last_writeback_at/status/error` on the integration row (the resolved credential
  source's row), write one `FeedbackWorkflowEvent(event_type="intercom_writeback")`
  with `metadata={"source": "intercom", "action": "note_and_close"|"note_only",
  "note_sent": bool, "closed": bool, "reason"?: str}`.
- Task body **never raises** (best-effort with recorded failure, CRM writeback
  precedent); a failing item must not abort the batch (per-item isolation).
- Timeline visibility (R5): add a fetcher to
  `services/worker-service` — note: the timeline service lives in **backend-api**
  (`src/services/customer_timeline_service.py`); add `_fetch_intercom_writeback`
  mirroring `_fetch_status_changed` (backend aspect `dispatch-seams` or a small
  addition here — decide in plan: the fetcher is backend code, group it with the
  backend dispatcher work).

## Out of scope

- The dispatch call sites (dispatch-seams aspect) — this aspect owns the task only.
- Client methods (worker-write-client aspect) — consumed here.
- Redis cooldown/keys (marker is DB-durable; prd.md R4).

## Acceptance criteria (testable)

1. Guard chain: each guard returns the recorded outcome without any HTTP call (mocked
   client asserts zero calls) — tests for all 7 guards.
2. Success path: note + close called with correct args; marker set; integration row
   status updated; exactly one `intercom_writeback` event written.
3. 403 → `missing_write_scope` recorded, `is_active` untouched; 404 → `noop/already_closed`
   (and marker set so re-runs skip); 429 → retried (retry count asserts, no eager mode).
4. `noop/already_written` when marker present (re-resolve after reopen does nothing).
5. Batch isolation: one bad item doesn't abort the rest.
6. Task name matches the `send_task` string the dispatchers use (name-consistency test,
   `test_beat_schedule_integrity` style).
7. Worker suite green (in-memory SQLite per the hubspot writeback tests).

## Dependencies & sequencing

- After `db-config-model` (columns + marker) and `worker-write-client` (client
  methods).
- The timeline fetcher (backend `customer_timeline_service.py`) can land in this
  aspect or `dispatch-seams` — pick one owner in the plan; both are worker-independent.

## Open questions / risks

- Default note text "Marked resolved in Rereflect." — confirmed in PRD; no config in v1.
- Whether `last_writeback_*` update uses the token-paste row only (OAuth row has no
  writeback columns) — v1: record on the credential source that has the columns; if the
  connection is the legacy OAuth row, record status in the task log + timeline event
  only (flag in plan).
