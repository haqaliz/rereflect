# Aspect spec — Dispatch seams (5 call sites + timeline fetcher)

**Feature:** `intercom-writeback` (prd.md R6 + R5's timeline fetcher) · **Aspect:** `dispatch-seams`

## Problem slice

The write-back only works if **every** writer that can move an Intercom-sourced item to
`resolved` dispatches the task. The repo has shipped this bug class four times
("silently never fires"); the seam-test family is mandatory, not optional. Also: the
`intercom_writeback` timeline event must render on Customer 360, which needs a fetcher
in the backend timeline service.

## In-scope

### Backend — helper + 3 call sites (all post-commit, fire-and-forget, never raise)

- New helper in `services/backend-api/src/services/workflow_service.py`:
  `dispatch_intercom_writeback(db, organization_id, changed_pairs)` — iterates the
  `apply_status_change` returned pairs, filters `new_status == "resolved" and
  fb.source == "intercom"`, collects `[{"id", "resolution_note"}]`, and
  `send_task("src.tasks.intercom_writeback.push_resolved_writeback", args=[org_id,
  items])` — the exact `dispatch_status_webhooks` shape (workflow_service.py:53-78),
  try/except, never raises. `resolution_note` read from the item's
  `metadata["resolution_note"]` (apply_status_change attaches it when resolving —
  workflow_service.py:42-43).
- Call sites:
  1. `src/api/routes/workflow.py` `change_status` — after the commit + existing
     side-effects block (after ~:169-197).
  2. `src/api/routes/public_api.py` `public_bulk_update_feedback` — after the commit
     + side effects (after ~:583-619).
  3. `src/api/routes/public_api.py` `public_update_feedback` — after commit + side
     effects (after ~:719-738).

### Worker — 2 call sites (direct task dispatch)

- `src/services/playbook_engine.py` `_handle_change_status` (:259-279): when
  `new_status == "resolved"` and `feedback.source == "intercom"`, dispatch the task
  (`.delay(...)` or `app.send_task`) with the item's id + resolution note.
- `src/services/automation_feedback_trigger.py` `_execute_change_status` (:601-614):
  same condition + dispatch.

### Timeline fetcher (backend)

- `src/services/customer_timeline_service.py`: add `_fetch_intercom_writeback`
  mirroring `_fetch_status_changed` (:256-260) — reads `FeedbackWorkflowEvent` rows
  with `event_type == "intercom_writeback"` and merges them into the timeline
  (type/source/source_id contract).

### Seam tests (the non-negotiable part)

- Backend: for each of the 3 call sites, a test asserting a `resolved` transition on an
  Intercom-sourced item dispatches `send_task` with the right args, and negative cases:
  non-Intercom source, non-resolved status, same-value no-op → no dispatch. Pattern:
  `tests/test_health_writeback_enqueue.py` (mock `send_task`, assert args).
- Worker: for each of the 2 writers, a test asserting the dispatch happens on
  `resolved` + intercom source, and does not otherwise. Pattern:
  `test_usage_trend_trigger_seam.py`.
- A registration name-consistency check: the task's registered name equals the dotted
  string all five sites dispatch (mirror `test_beat_schedule_integrity.py`).

## Out of scope

- The task body itself (worker-writeback-task aspect) — the dispatch string must match
  its registered name.
- Changing the worker writers' other behavior (they still emit no `status_changed`
  event; the dispatch is additive).
- `feedback.status_changed` webhooks / WS events (existing behavior unchanged).

## Acceptance criteria (testable)

1. 5 seam tests exist and pass — one per call site — covering dispatch-on-resolved and
   the three negative cases.
2. `dispatch_intercom_writeback` never raises even when `send_task` raises (mocked).
3. Timeline fetcher test: an `intercom_writeback` event appears in the customer
   timeline payload; `status_changed` behavior unchanged (characterization).
4. Backend + worker suites green.

## Dependencies & sequencing

- The task must exist (worker-writeback-task) for the name-consistency test and for
  `.delay()` calls to resolve; sequence this aspect after it.
- `dispatch_intercom_writeback` reads `feedback_items.intercom_writeback_at`-adjacent
  fields — needs `db-config-model` (schema) only insofar as models load; the dispatcher
  itself doesn't touch the marker.
- Independent of `config-api-routes` and the frontend.

## Open questions / risks

- Worker writers' resolution note: `_execute_change_status` and `_handle_change_status`
  take a status string but no resolution note — the dispatch payload's
  `resolution_note` is `None` from those sites (note falls back to the default text).
  Acceptable; state it in the plan.
- Whether the backend helper belongs in `workflow_service.py` (shared by 3 sites) vs a
  new module — either is fine; keep it where `dispatch_status_webhooks` lives.
