# Spec — action-core (backend action type + delivery model)

**Aspect:** `action-core` · **Slug:** `automation-send-customer-email`
**Plan output:** `docs/planning/automation-send-customer-email/action-core/plan_20260819.md`

## Problem slice

The automations engine has no way to email the customer. This aspect adds the backend
half: the `send_customer_email` action type, its config validation, the
`automation_email_deliveries` audit model + migration, the enqueue-to-worker dispatch,
and the deliveries read endpoint.

## In-scope (backend-api only)

- `VALID_ACTION_TYPES` += `"send_customer_email"` (`src/api/routes/automations.py:59-65`).
- `SendCustomerEmailConfig` Pydantic model: `template: str`, `recipient: Literal["customer","cs_assignee"] = "customer"`, `extra="forbid"`. `template` validated against the outreach registry keys (`services/outreach_templates.py:29`).
- `AutomationEngine._execute_send_customer_email` (`src/services/automation_engine.py:407-438` dispatch table):
  - Resolve recipient email: `customer` → `context["customer_email"]`; `cs_assignee` → `CustomerHealth.cs_owner_user_id` → `User.email` (loud error when missing).
  - Skip loudly (action error, no enqueue) when: `RESEND_API_KEY` unset (backend `email_service._is_email_enabled()`); org-wide trigger with no customer_email; customer `is_archived` (`customer_health.py:41`).
  - Render subject/body via the backend outreach template registry
    (`render_outreach_template`); note it returns the **body** only — the subject needs
    its own `{{PRODUCT_NAME}}` substitution. `product_name` from
    `Organization.product_name_display`.
  - Create `AutomationEmailDelivery(status="queued")` row, enqueue
    `get_celery_app().send_task("tasks.outreach.send_automation_email", args=[delivery.id])`
    (the real `run_playbook` precedent, `automation_engine.py:727-789`), return
    `{status: "queued", delivery_id}`.
- `AutomationEmailDelivery` model (Integer PK — codebase convention) + one Alembic
  migration (chained to the live single head; `alembic heads` must print exactly one
  head). Columns: `id`, `organization_id`, `rule_id`, `customer_email`, `to_email`,
  `template_key`, `subject`, `body`, `status` (`queued|sent|skipped|failed`), `reason`
  (nullable), timestamps. **No `automation_execution_id`** (execution log is written
  after actions run on every evaluator).
- `GET /api/v1/automations/{rule_id}/deliveries` (admin/owner, org-scoped, recent first, paginated like other list endpoints).

## Out-of-scope boundaries

- Worker task + mirrors → aspect `worker-mirrors`.
- Frontend → aspect `frontend-editor`.
- Seeded template + docs → aspect `docs-and-templates`.
- Not changing the lax config models for the 4 existing action types.

## Acceptance criteria (testable)

1. Creating/updating a rule with a valid `send_customer_email` action passes; unknown `template` key → 422; unknown config key → 422 (`extra="forbid"`); bad `recipient` → 422.
2. On a health-score-trigger evaluation with a `customer` recipient: a delivery row is created `queued`, and `send_task` is called with the exact string `tasks.outreach.send_automation_email` and the delivery id.
3. No-key (`RESEND_API_KEY` unset): no enqueue, action result error `email not configured`, delivery row `skipped` with that reason.
4. Org-wide `batch_sentiment_threshold` evaluation: action errors
   `no customer email (org-wide trigger)`, no enqueue — keyed on the trigger type, not
   a missing context email (the context always carries the pivot feedback's email).
5. `is_archived` customer: action errors `customer archived`, no enqueue.
6. `cs_assignee` with no health row / no owner / no owner email: loud action error, no enqueue.
7. Deliveries endpoint returns the org's rows (admin/owner only), newest first; member → 403.
8. Backend `pytest tests/ -v` green; `alembic heads` single head.

## Dependencies & sequencing

- First aspect. Must land before `worker-mirrors` (task name + delivery model contract) and before `docs-and-templates` (seeded template uses the action).
- Reuses `outreach_sender_contract.OUTREACH_COOLDOWN_PREFIX` (read-only; do not drift the key).

## Open questions / risks

- Confirm the exact `context` dict keys available on the backend health triggers (`health_score_service.py:549-566` carries `customer_email`, `feedback_id: None`).
- Confirm `send_task` import path/usage precedent in the backend (`automation_engine._execute_run_playbook` at `:727-789` is the model).