# Spec: worker-dispatch

## Problem slice

The worker can deliver Teams cards on every notification pipe, with the same
per-process raise-on-failure contract and org-wide gating Slack/Discord use.

## In-scope

- `send_teams_message_webhook(webhook_url, title, text, summary)` sibling in
  `services/worker-service/src/tasks/alerts.py:226-284` (httpx POST, 10s timeout,
  raise-on-failure, returns response dict).
- `notification_dispatch.py`:
  - `dispatch_health_drop_alert` — `_dispatch_teams_health_alert` (:148-177 shape),
    gated like `_dispatch_discord_health_alert` (:436-470 flags), invoked once per org
    (:493-504 branch).
  - `dispatch_alert` — Teams branch beside the slack/discord selection
    (:675-763 / :766-829 shape).
  - Counts keys gain `"teams"` in both return dicts (:361, :607) — **added, not
    renamed** (existing keys are contract).
- Integration-selection queries mirror `Integration.type == "discord"` patterns;
  per-integration error capture + `error_count`/`last_error` bookkeeping unchanged.

## Out-of-scope

Per-user preference gating (see `channel-preference`); automations mirrors (see
`automations-notify`); playbook engine (see `playbook-notify`); P7 refactor.

## Acceptance criteria

- Health-drop with an active Teams integration and any user's `channel_teams` on posts
  one card per org; counts dict contains `"teams": 1`.
- Generic alert posts to Teams alongside slack/discord per existing gating.
- Failed Teams send increments `error_count`, never raises out of the dispatch.
- Slack/Discord dispatch behavior byte-identical (existing tests green, counts keys
  unchanged for those providers).

## Dependencies / sequencing

Depends on `backend-connector` only for the URL-validator shape (worker validates via
stored config; no hard dependency — can run parallel after `backend-connector`).

## Open questions

None blocking. MessageCard text/title mapping for each pipe (health alert text vs
generic alert text) follows the Slack text/block split precedent.