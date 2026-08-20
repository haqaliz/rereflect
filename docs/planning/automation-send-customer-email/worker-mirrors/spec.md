# Spec — worker-mirrors (task + three evaluator mirrors)

**Aspect:** `worker-mirrors` · **Slug:** `automation-send-customer-email`
**Plan output:** `docs/planning/automation-send-customer-email/worker-mirrors/plan_20260819.md`

## Problem slice

The send actually happens in the worker. This aspect adds the single
`send_automation_email` worker task (the only place that sends) and extends all three
worker evaluator mirrors to handle the `send_customer_email` action with identical
semantics to the backend engine (aspect `action-core`).

## In-scope (worker-service only)

- **Task `src/tasks/outreach.py` += `send_automation_email`** — `@shared_task(bind=True, name="tasks.outreach.send_automation_email")`; registered in `celery_app.py` (the module is already included at line 71). Args: `(delivery_id,)`. Loads the delivery row (`organization_id`, `to_email`, `subject`, `body`, `template_key`; `product_name` is derived from the org at send time, not stored), calls `outreach_sender.send_outreach_email(...)`, maps result → row `status` (`sent`/`skipped`/`failed`) + `reason`; terminal guard (already terminal → no-op); try/except so an exception marks the row `failed` — **never leaves `queued`**. Task-name string pinned by a test (the run_playbook/outreach precedent).
- **Feedback mirror `src/services/automation_feedback_trigger.py`** (`_execute_actions`, 477-517): add `send_customer_email` handler — mirror of the backend handler: resolve recipient (`customer` via `context["customer_email"]`; `cs_assignee` via health → owner email), skip loudly on no-key / trigger-type-org-wide (`batch_sentiment_threshold`, keyed on trigger type not a missing context value) / archived, render via the worker registry mirror (`outreach_templates_mirror.py`; subject needs its own `{{PRODUCT_NAME}}` substitution), create delivery row, `send_automation_email.delay(delivery_id)`, return `{status: "queued", delivery_id}`.
- **Churn mirror `src/services/automation_churn_trigger.py`** (`:210-282`): extend the action loop so `send_customer_email` is handled (currently only `run_playbook`; everything else silently `continue`s at `:224`). Keep the silent-skip for *other* unknown types (existing pin `test_non_run_playbook_actions_are_ignored`).
- **Usage mirror `src/services/automation_usage_trend_trigger.py`** (`:260-331`): same extension (silent `continue` at `:272`).

## Out-of-scope boundaries

- Backend engine handler + model + migration + deliveries endpoint → `action-core`.
- Making *all* unknown action types loud in the churn/usage mirrors → separate delivery-integrity hardening (PRD R3), out of scope.
- Frontend → `frontend-editor`.

## Acceptance criteria (testable)

1. `send_automation_email` updates a `queued` row → `sent|skipped|failed` + reason per `outreach_sender` result; terminal rows are no-op; an exception marks the row `failed` (never `queued`).
2. Task-name string `tasks.outreach.send_automation_email` pinned by a test; the backend's `send_task` string and the mirrors' `.delay()` agree.
3. Feedback mirror: a `send_customer_email` action creates a delivery row + calls `send_automation_email.delay`; no-key / no-customer_email / archived / bad recipient all error loudly with no enqueue and no row left `queued`.
4. Churn mirror: a `send_customer_email` action now executes (delivery row + `.delay`); a `send_notification` action is still silently ignored (existing pin green, unmodified).
5. Usage mirror: same as churn.
6. Worker `pytest tests/ -v` green; `test_worker_import_sweep.py` stays green (no backend imports, no bare try/except).

## Dependencies & sequencing

- Depends on `action-core` (delivery model + migration + task-name contract). Plan/implement after it.
- Must land before `frontend-editor` only insofar as the UI needs the action to work end-to-end.
- Reuses `outreach_sender.send_outreach_email` (worker-local) — do NOT duplicate its logic.

## Open questions / risks

- Confirm the feedback-mirror `context` keys (`analysis.py:201` carries `customer_email`, `feedback_id`).
- `cs_assignee` resolution in the feedback mirror has no guaranteed `CustomerHealth` row — must mirror the backend's loud-error behavior (spec AC6 in action-core).