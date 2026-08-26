# Card: Complete the seeded playbook action types

**Type:** feat (freeform, no GitHub issue)
**Slug:** `playbook-action-types`
**Branch:** `feat/playbook-action-types`
**Source:** `rereflect-next` recommendation (2026-08-26), verified against code

## Brief

The churn-playbook executor implements only 5 of the 11 action types the seeder declares valid.
6 of the 7 seeded playbook templates therefore contain actions that fail with
`"unsupported action type"` on every execution — the same inert-template disease class as the
P0 `automation-worker-triggers-dead` fix, but for the playbook engine.

## Verified facts (from code)

- `services/backend-api/src/services/playbook_seeder.py:24-36` — `VALID_ACTION_TYPES` includes
  `assign, notify, draft_response, send_email, tag, schedule_task, create_task, trigger_automation,
  auto_assign, change_status, send_notification`.
- `services/worker-service/src/services/playbook_engine.py:171-186` — `_dispatch_action` supports
  only `assign, change_status, send_notification, draft_response, send_email`. Everything else
  returns `ok=False, error="unsupported action type: '<type>'"`.
- Seeded templates with unsupported actions (`playbook_seeder.py`):
  - **Critical Save** — `notify` (line 57) → fails
  - **Churn Prevention** — `schedule_task` (line 96) → fails
  - **At-Risk Outreach** — `tag` (line 115) → fails
  - **Light-Touch Nudge** — `tag` + `create_task` (lines 138, 142) → fail
  - **Power-User Recovery** — `notify` + `create_task` (lines 161, 173) → fail
  - **New-Customer Save** — `trigger_automation` (line 192) → fails
  - **Silent-Churn Watch** — `create_task` (line 219) → fails (send_email part works)
- Executions complete `status="done"` with failed actions buried in `action_log`
  (`worker-service/tests/test_playbook_engine.py:574-600` pins this "loud entry" behavior).
- The repo names this as the next card: `docs/planning/customer-outreach-email-actions/prd.md:247-255`
  — "Fixing the other 5 unimplemented seeded playbook action types (`notify`, `tag`, `schedule_task`,
  `create_task`, `trigger_automation`) — separate card; noted."

## Shipped seams to reuse

- `tag` → `customer_health_scores.tags` (segment-actions, `AI-TRACKING.md:345`)
- `notify` → `notification_dispatch` (Slack/Discord/dashboard channels)
- `create_task` / `schedule_task` → Jira / Asana / Linear integration clients already shipped
- `trigger_automation` → M4.4 `AutomationEngine` (`backend-api/src/services/automation_engine.py:416-432`)

## Known caveats (must be resolved in PRD/plan)

1. `trigger_automation` needs a recursion guard (rule → playbook → rule loops) and a cooldown story.
2. `create_task` needs a decided target-provider policy — seeded configs name no provider
   (Jira vs Asana vs Linear vs internal queue).
3. Consider surfacing failed actions in the playbook-run UI, since executions currently
   complete "done" with failures only in the action log.