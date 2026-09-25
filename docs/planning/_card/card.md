# Card — feat/automation-playbook-dispatch-commit

**Source:** freeform (no GitHub issue). Picked by `rereflect-next` on 2026-09-25.

## Brief

Automation `run_playbook` actions create a `ChurnPlaybookExecution` row, `flush()` it to get
an id, and publish that id to Celery **before the row is committed**:

- `services/backend-api/src/services/automation_engine.py:827-831` (`_execute_run_playbook`,
  `send_task("tasks.churn_playbooks.run_playbook", ...)`)
- `services/worker-service/src/services/automation_churn_trigger.py:290-293`
  (`run_playbook.delay(exec_row.id)`)
- `services/worker-service/src/services/automation_usage_trend_trigger.py:333-336`
  (`run_playbook.delay(exec_row.id)`)

Postgres exposes nothing to other connections until COMMIT. The worker can consume the message
before the publisher commits, looks the row up, gets nothing, and `playbook_engine.py:49`
returns `{"skipped": True, "reason": "execution not found"}` with no retry. The row stays
`queued` forever and the playbook never runs.

The manual routes (`playbooks.py`) commit before dispatch, which is why a human-triggered run
works and a rule-triggered one silently no-ops.

Consequence: M4.1.5 (churn-triggered playbook auto-execution, `AI-TRACKING.md:400`) and the
M3.2c `usage_trend` → `run_playbook` path are marked COMPLETE but are not delivered.

## Asks

1. Commit before publish at all three sites (durable-then-publish), pinned by ordering tests
   in the style of `send_customer_email` (spy on `db.commit` vs `send_task`/`.delay`).
2. Decide deliberately what a mid-rule commit means for the backend engine's single
   end-of-`_evaluate_rule` commit (partial-failure / rollback semantics).
3. Acceptance needs a **live** run — scratch Postgres DB + real Celery worker — showing
   `queued → completed`. Unit suites cannot see this (one in-memory session, mocked Celery).
4. Record the defect in `DEV-TRACKING.md` and correct the M4.1.5 / M3.2c markers in the same
   branch.

## Provenance / honesty

This defect was not recorded in any tracked repo file as of 2026-09-25. Evidence: a live
repro on 2026-08-21 (session memory) plus the current code, which still has flush-then-publish
at all three sites.
