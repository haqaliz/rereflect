# PRD — Automation action support per trigger

**Status:** Approved 2026-09-26 (user: "let's do whatever remaining") · **Branch:** `feat/automation-action-support`
**Source:** open follow-up in `DEV-TRACKING.md` (`automation-playbook-dispatch-commit`): "the rule API lets
`run_playbook` sit on any trigger — intended?" Investigating it found real inert behaviour.

## Problem
`routes/automations.py` validates action *types* but never checks them against the trigger, while each
trigger is evaluated by a different executor with a different action set (observed 2026-09-26):

| Trigger | Executor | Actually executes |
|---|---|---|
| `feedback_category_match`, `sentiment_pattern`, `batch_sentiment_threshold` | worker `automation_feedback_trigger` | auto_assign, change_status, send_notification, draft_response, send_customer_email. `run_playbook` → loud "Unsupported action type" error |
| `health_score_threshold`, `churn_risk_level_change` | backend `automation_engine` via `health_score_service` (`feedback_id` always `None`) | send_notification, run_playbook, send_customer_email. auto_assign / change_status / draft_response → loud "No feedback object" every fire |
| `churn_probability_threshold`, `usage_trend` | worker churn / usage-trend mirrors | run_playbook, send_customer_email. **Everything else silently skipped (`continue`) while the audit row says `success`** |

Two shipped templates are affected:
- **`usage_decline_outreach`** (`usage_trend` → `send_notification` only): **fully inert**. Every fire is
  logged `success` and nobody is notified.
- **`churn_prevention`** (`health_score_threshold` → auto_assign + send_notification + draft_response): two
  of three actions fail on every fire, and the description promises assignment and a draft.

## Requirements
- **R1 Worker mirrors execute `send_notification`.** The churn and usage-trend mirrors delegate to the worker's
  existing `automation_feedback_trigger._execute_notify` (same process, no duplication), with
  `feedback=None` and a customer-naming message. Recipients needing a feedback item (`assignee`) produce a
  loud error, not a silent no-op.
- **R2 No silent skips.** Any other action type in those two mirrors is recorded as an explicit error,
  so the rule status is `partial_failure` / `failed`, never a false `success`. The test pinning the silent
  skip (`test_non_run_playbook_actions_are_ignored`) is updated deliberately.
- **R3 One support matrix, enforced at the API.** `SUPPORTED_ACTIONS_BY_TRIGGER` in
  `routes/automations.py`:
  - feedback triggers → {auto_assign, change_status, send_notification, draft_response, send_customer_email}
  - health triggers → {send_notification, run_playbook, send_customer_email}
  - churn_probability_threshold, usage_trend → {send_notification, run_playbook, send_customer_email}

  Create and update both return 422 naming the trigger and the unsupported action(s). Update validates
  the effective (trigger, actions) pair, so changing only the trigger is checked too.
- **R4 Endpoint** `GET /api/v1/automations/action-support` → `{"<trigger>": ["<action>", ...]}` (auth +
  org like the other automation routes). No plan gate.
- **R5 Templates.** `churn_prevention` becomes send_notification only, with its description updated to
  match. A test asserts every template's actions are in the matrix for its trigger.
- **R6 Frontend.** The new and edit rule pages only offer actions the selected trigger supports (fetched
  from R4). An existing action that becomes unsupported after a trigger change is shown with a warning
  rather than silently removed.
- **R7 Docs.** CHANGELOG, DEV-TRACKING follow-up closed.

## Out of scope
- A data migration for rules already saved with unsupported combos. They now fail loudly in the log, and
  saving an edit requires removing the unsupported action (the 422 says which one).
- Giving health triggers a feedback item.

## Risks
- The matrix duplicates executor knowledge. A test in each worker mirror pins its handled set to the
  matrix values, via a golden fixture read by both suites:
  `services/worker-service/tests/fixtures/automation_action_support.json`.
