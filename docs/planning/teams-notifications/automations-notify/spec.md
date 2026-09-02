# Spec: automations-notify

## Problem slice

Automation rules can notify a Teams channel — the `send_notification` action gains
Teams in both the backend engine and the worker's mirror evaluator.

## In-scope

- Backend `services/backend-api/src/services/automation_engine.py`:
  - `KNOWN_NOTIFY_CHANNELS` gains `"teams"` (:35).
  - `_execute_notify` (:510-683) — org-wide Teams branch mirroring the Slack branch
    (:611-667): select `Integration.type == "teams", is_active`, decrypt/read
    `config.webhook_url`, call the backend sender, append `teams: ...` errors.
  - Result shape (:679-683) gains a parallel `teams_sent` count; `slack_sent` and the
    error-join contract unchanged.
- Worker mirror `services/worker-service/src/services/automation_feedback_trigger.py`:
  - `KNOWN_NOTIFY_CHANNELS` gains `"teams"` (:87).
  - Teams branch beside the slack branch (:763-811) using the worker sender; same
    raise/status contract.
- Unknown channel stays a loud error (:671-677 backend; mirror equivalent).
- Seeded templates: no change (none declare `teams`; `Critical Bug Escalation` keeps
  `["dashboard","email","slack"]`).

## Out-of-scope

Channels editor (does not exist); per-rule channel UI; playbook `notify` (see
`playbook-notify`); P7 refactor.

## Acceptance criteria

- Rule with `channels: ["teams"]` and an active Teams integration → one card per org
  per firing, `teams_sent == 1` in the execution result.
- No Teams integration → clean skip, no error, no card.
- Unknown channel still produces the loud error path (existing test class).
- Backend automation suite + worker suite green; existing Slack channel behavior
  byte-identical.

## Dependencies / sequencing

Depends on `backend-connector` (sender) and `worker-dispatch` (worker sender).