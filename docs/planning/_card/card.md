# Card — automation Slack channel silently dropped

**Type:** bug · **Slug:** `automation-slack-channel` · **Branch:** `bug/automation-slack-channel`
**Source:** freeform — post-1.0.0 user feedback triage on 2026-07-29. No GitHub issue.

> Replaces the prior `local-embedding-quality` card on this branch only; that card
> remains in `master` history. `_card/card.md` is per-worktree by design.

---

## Brief (as given)

Fix the silently-dropped `"slack"` notification channel in the automations engine.

`AutomationEngine._send_notification` (`services/backend-api/src/services/automation_engine.py`,
~L502–560) only implements the `"dashboard"` and `"email"` channels. But
`services/backend-api/src/config/automation_templates.py:72` (the **Critical Bug
Escalation** template) declares:

```python
"channels": ["dashboard", "email", "slack"],
```

So a user who enables that template expects a Slack ping on every critical bug /
security breach and silently gets nothing. No log line, no execution-log entry, no
error — the channel string is simply never matched by an `if`.

Requested outcome:

1. Wire the `slack` channel through the existing Slack integration
   (`Integration` rows with `type="slack"`; `send_slack_message()` in
   `services/backend-api/src/api/routes/integrations.py`).
2. Make an unknown or unroutable channel **loud** rather than silent.

## Origin — post-1.0.0 user feedback

Surfaced while drafting replies to four pieces of 1.0.0 feedback. The relevant one:

> "Honestly the bring your own key setup is really nice, but it would be great if
> you could plug in a Slack or Discord webhook to get pinged whenever a batch of new
> feedback crosses a certain sentiment threshold. Would make triaging way faster for
> our team."

Investigating that request is what exposed the dropped channel. The user's ask is
**broader** than this bug — see *Explicitly out of scope*.

## Verified facts (checked against the `v1.0.0` tree)

- `automation_engine.py` `_send_notification`: `if "dashboard" in channels` (~L536)
  and `if "email" in channels` (~L550). No `slack` branch, no `else`, no warning.
- Its own docstring under-declares the contract:
  `channels: ["dashboard"] | ["email"] | ["dashboard", "email"]` — so the code and
  the template disagree about what a valid channel even is.
- `automation_templates.py:72`: Critical Bug Escalation declares `slack` in channels.
- Slack **is** otherwise supported: `POST /api/v1/integrations/slack/webhook` accepts an
  incoming-webhook URL (validated to start with `https://hooks.slack.com/`), plus a
  Slack OAuth flow and a `/slack/test` endpoint.
- Slack alerts **do** fire today, but from a different path:
  `services/worker-service/src/notification_dispatch.py::_dispatch_slack_health_alert`
  (customer-health / churn alerts) — not from the automations engine.
- `require_feature("slack_integration")` gates the Slack routes, but is inert under
  `SELF_HOSTED=true` (returns `True`), so this is **not** a plan-gating issue and no
  plan gate may be added.

## Explicitly out of scope (track separately in AI-TRACKING/DEV-TRACKING)

These came from the same feedback but are **not** this bug:

- **Batch-level sentiment trigger.** Today's `sentiment_pattern` trigger fires on
  *N negative feedbacks from one customer within D days*. The user asked for a
  threshold across an incoming **batch**. That's a new trigger type.
- **Discord support.** Not supported. Discord's webhook API requires `{content}` or
  `{embeds}`; the custom-webhook dispatcher posts Rereflect's own JSON envelope, so
  pointing it at a Discord URL returns 400. Needs a native formatter.

## Open questions for the dig

- Which Slack integration does an automation use when an org has more than one?
- Should the org-wide Slack post happen once per rule firing, or once per recipient
  user (recipients resolve to user ids; Slack channels are org-wide)?
- "Loud" for an unroutable channel — log warning only, or also record it on the
  `AutomationExecution` row so it surfaces in the execution-log UI?
- Does the frontend automations editor let a user select `slack` today?
- Is `send_slack_message` safely importable from the service layer, or does importing
  a route module from a service create a circular import?
