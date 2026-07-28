# Spec — `worker-trigger-mirror`

**Parent PRD:** `../prd.md` · **Aspect 2 of 2** · Services: **worker-service** + one Alembic migration

## Problem slice

`services/worker-service/src/tasks/analysis.py:175` imports `AutomationEngine` from a
module that does not exist in worker-service, inside a `try/except Exception` that logs a
warning. The `ImportError` fires on every analysis, so `feedback_category_match` and
`sentiment_pattern` have **never** executed. Four of six shipped templates are inert.

**User outcome:** those triggers evaluate — but in **shadow** on first deploy, so an
operator reviews what *would* have fired before anything acts.

## In scope

- **W1** — New `services/worker-service/src/services/automation_feedback_trigger.py`,
  following the structural precedent of `automation_churn_trigger.py`:
  module-level docstring explaining why it exists, `_get_redis()` returning `None` on
  failure (cooldowns disabled, never raises), its own `AutomationExecution` writes.
- **W2** — Implement exactly two triggers, matching backend semantics:
  - `feedback_category_match` — `categories` list + optional `is_urgent`.
  - `sentiment_pattern` — ≥ `count` feedbacks of `sentiment` from the **same customer**
    within `days`.
  Port the logic from `backend-api/src/services/automation_engine.py`
  (`_trigger_feedback_category`, `_trigger_sentiment_pattern`) — do not re-derive it.
- **W3** — Implement four actions: `auto_assign`, `change_status`, `send_notification`,
  `draft_response`. **Any unimplemented action type must record an explicit `error`, never
  a silent skip** (same loudness principle as aspect 1). `run_playbook` is out of scope
  here and must therefore produce that error rather than being ignored.
- **W4** — `send_notification` in the mirror supports `dashboard`, `email` and `slack`,
  consistent with aspect 1. Worker has `Notification` in `src/models/__init__.py:355`,
  `src/email.py::_send_with_template`, and Slack senders in `src/tasks/alerts.py`.
  **Note the contract difference:** worker's `send_slack_message_webhook` **raises** on
  failure (unlike backend's, which returns a status dict). Wrap accordingly.
- **W5** — Cooldown semantics **byte-identical** to the backend engine so a cooldown set by
  either process is honoured by both: Redis **DB 1**, key
  `automation_cooldown:{rule_id}:{customer_email}`, TTL `cooldown_hours * 3600`.
- **W6** — Replace the dead import at `analysis.py:175`. The replacement must **not** be
  wrapped in a bare `except Exception` that hides an import error — that is the exact
  failure mode being fixed. Let an import error surface; keep a narrow try/except only
  around evaluation itself.
- **W7** — Alembic migration setting `mode='shadow'` on existing rules where
  `mode='active'` **and** `trigger_type IN ('feedback_category_match','sentiment_pattern')`.
  Every other rule untouched. One-time data migration; it must **not** change template
  defaults, so rules created after the fix start `active` as normal.
- **W8** — Cross-reference comments: in the new mirror pointing at the backend engine, and
  in the backend engine pointing at the mirror, so the next person to change a trigger
  finds both.

## Out of scope

- `run_playbook` in this mirror (the other two mirrors own it) — but see W3: it must error
  loudly, not be silently dropped.
- Touching `automation_churn_trigger.py` or `automation_usage_trend_trigger.py`.
- Any backfill suppression beyond shadow mode (PRD R9).
- A UI prompt telling operators that rules were moved to shadow.

## Acceptance criteria (testable)

1. Analysing a feedback item matching a `feedback_category_match` rule writes an
   `AutomationExecution` row. (Today: none, ever.)
2. A rule in `mode='shadow'` logs `status="shadow"` with empty `actions_executed` and
   executes **no** actions.
3. `sentiment_pattern` fires only at ≥ `count` matching feedbacks from the same customer
   inside `days`; `count-1` does not fire.
4. Cooldown written by the mirror is honoured by the backend engine's key scheme and
   vice-versa (assert the exact key string and TTL).
5. Each of the four actions executes and is recorded in `actions_executed`.
6. An action type the mirror does not implement yields a non-null `error` in
   `actions_executed`, and the row is `partial_failure`.
7. Migration: an `active` rule on `feedback_category_match` becomes `shadow`; an `active`
   rule on `health_score_threshold` stays `active`; an already-`off` rule stays `off`.
8. `analysis.py` no longer swallows an `ImportError` from the trigger module.

## Testing notes (traps)

- Worker suite: `cd services/worker-service && ./venv/bin/pytest tests/ -v`.
- No autouse Slack/email stub in the worker suite either — mock explicitly at source
  modules (`src.email._send_with_template`, `src.tasks.alerts.send_slack_message_webhook`).
- Alembic is **single-head** and CI asserts it. Get the parent from a live
  `alembic heads` — do **not** grep version files for `down_revision`, and do not invent a
  revision id.

## Dependencies & sequencing

Land **after** aspect 1, so the mirror's `send_notification` can mirror a Slack
implementation that already exists and is tested rather than inventing one in parallel.
