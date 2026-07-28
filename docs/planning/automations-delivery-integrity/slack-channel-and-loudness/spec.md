# Spec — `slack-channel-and-loudness`

**Parent PRD:** `../prd.md` · **Aspect 1 of 2** · Service: **backend-api only**

## Problem slice

`AutomationEngine._execute_notify` (`services/backend-api/src/services/automation_engine.py:485-571`)
silently drops any channel it does not implement, and reports the resulting no-op as a
success. A rule configured for Slack delivers nothing and leaves an execution row saying
it worked.

**User outcome:** a rule with `channels:["slack"]` posts to the org's Slack; a rule with an
undeliverable channel produces a visibly failed execution instead of a false success.

## In scope

- **S1** — `slack` branch in `_execute_notify`, posting via the org's active
  `Integration` rows with `type="slack"`. Must work webhook-only (no `SLACK_CLIENT_ID`).
- **S2** — Post to **all** active Slack integrations for the org, matching the existing
  precedent in `worker-service/src/notification_dispatch.py::_dispatch_slack_health_alert`.
  `integrations` has no unique constraint on `(organization_id, type)` — multiple rows are
  legitimate.
- **S3** — Reuse the existing backend sender `send_slack_message()`
  (`src/api/routes/integrations.py:216`). It returns `{"success": bool, ...}` and **never
  raises**. Do **not** add a new sender. Note the worker's sender (`tasks/alerts.py:207`)
  has the opposite contract (raises) — do not import it here.
- **S4** — Slack is **org-wide, once per rule firing**, not once per recipient user.
  Recipients resolve to user ids for dashboard/email; a Slack channel has no user identity.
  Posting per-recipient would produce N duplicate messages.
- **S5** — Set a real `error` string on the returned action dict when a requested channel
  could not be delivered, so `_evaluate_rule` computes `partial_failure` instead of
  `success`. Preserve `error: None` when everything succeeded.
- **S6** — `logger.warning` for any unrecognised channel string (the missing `else`),
  matching the email branch idiom at `automation_engine.py:550-565`.
- **S7** — A Slack failure must not abort the dashboard/email channels or subsequent
  actions. Per-channel `try/except`, same as email.

## Out of scope

- Write-time validation on `SendNotificationConfig` (`src/api/routes/automations.py:171-174`)
  — declined explicitly in favour of loud runtime failure.
- Any frontend channel selector (none exists today).
- Refactoring the three duplicated Slack integration-selection loops or the two duplicated
  sender pairs.
- `SlackAlertLog` writes. Neither existing `_dispatch_slack_*` function writes one; staying
  consistent.

## Acceptance criteria (testable)

1. Rule with `channels:["slack"]`, one active Slack integration → `send_slack_message`
   called exactly once; result `error is None`.
2. Rule with `channels:["slack"]`, **two** active Slack integrations → called twice.
3. Rule with `channels:["slack"]`, **no** Slack integration → result has a non-null
   `error`; execution row status is `partial_failure`, not `success`.
4. Rule with `channels:["dashboard","slack"]` where Slack send fails → dashboard
   `Notification` row still created; `error` non-null.
5. Rule with `channels:["carrier_pigeon"]` → `logger.warning` emitted and `error` non-null.
6. Rule with `channels:["dashboard"]` → byte-identical behaviour to today; `error is None`.
7. Slack posted **once** for a rule with 3 admin recipients, not 3 times.

## Testing notes (traps)

- `_execute_notify` lazily imports `send_alert_email` **inside** the method. Mock at the
  source module (`patch("src.services.email_service.send_alert_email")`), never at
  `src.services.automation_engine`. Apply the same rule to the new Slack import.
- `conftest.py` has an autouse `_disable_emails` fixture but **nothing for Slack** — an
  unmocked test will attempt a real network call.
- House style: local helpers `_make_rule` / `_make_feedback` in
  `tests/test_automation_engine.py`, plus the `test_organization` fixture.
- Run: `cd services/backend-api && ./venv/bin/pytest tests/test_automation_engine.py -v`

## Dependencies & sequencing

None. Fully independent of aspect 2 and safe to land first — it changes only a code path
that currently runs (the backend `health_score_threshold` route into `_execute_notify`).
