# Spec — dispatch-ordering

**Outcome:** automation-fired `run_playbook` actions commit the `ChurnPlaybookExecution` row before
publishing its id, so the worker can always find it (PRD M1–M3).

## In scope
- `services/backend-api/src/services/automation_engine.py` `_execute_run_playbook` (flush → commit).
- `services/worker-service/src/services/automation_churn_trigger.py` run_playbook branch.
- `services/worker-service/src/services/automation_usage_trend_trigger.py` run_playbook branch.
- One ordering test per site, RED first.

## Out of scope
Deferred dispatch; retry on `not found`; publish-failure handling; trigger/action restriction.

## Acceptance criteria
1. Each site: a test spying `db.commit` and the publish call asserts `commit` precedes publish; it
   fails on `origin/master` and passes after.
2. Existing tests in `test_automation_engine_run_playbook.py`, `test_automation_churn_trigger.py`,
   `test_automation_usage_trend_trigger.py`, `test_usage_trend_trigger_seam.py`,
   `test_playbook_engine*.py` (incl. `test_execute_finalizes_done_when_handler_commits_mid_run`) pass.
3. Error branches still create no row and publish nothing; shadow still publishes nothing.
4. Worker full suite and backend automation-scoped suite green.

## Risks
`expire_on_commit` post-commit refresh (safe; asserted via returned `execution_id`).
