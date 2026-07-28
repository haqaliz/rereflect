# PRD — Automations Delivery Integrity

**Slug:** `automations-delivery-integrity` · **Branch:** `bug/automation-slack-channel`
**Type:** bug (two compounding defects) · **Created:** 2026-07-29
**Source:** post-1.0.0 user feedback triage. No GitHub issue. See `docs/planning/_card/card.md`.

---

## Problem Statement

Rereflect's automations surface tells users it is doing things it is not doing. Two
independent, **verified** defects compound on the same code path.

### Defect A — two trigger types have never fired, in any deployment

`services/worker-service/src/tasks/analysis.py:175` does:

```python
try:
    from src.services.automation_engine import AutomationEngine
    engine = AutomationEngine(db)
    ...
    engine.evaluate(feedback.organization_id, "feedback_category_match", context)
    engine.evaluate(feedback.organization_id, "sentiment_pattern", context)
except Exception as exc:
    logger.warning("Automation engine dispatch failed after analysis for feedback %s: %s", ...)
```

`src.services.automation_engine` **does not exist in worker-service**
(`services/worker-service/src/services/` holds only `automation_churn_trigger.py` and
`automation_usage_trend_trigger.py`), and the worker image never receives backend-api's
package — `services/worker-service/Dockerfile:47,51,54` copies only `worker-service/src`
and `analysis-engine/src/analyzer` under `PYTHONPATH=/app`. The `ImportError` is therefore
raised on every single analysis, caught by the bare `except Exception`, and reduced to a
warning line.

Nothing else dispatches these two triggers. **`feedback_category_match` and
`sentiment_pattern` have never executed in production.** **Four** of the six shipped
templates are inert while the UI reports them as enabled:

| Template | Trigger | Actions it needs | Status |
|---|---|---|---|
| Critical Bug Escalation | `feedback_category_match` | `auto_assign`, `change_status`, `send_notification` | **inert** |
| Feature Request Triage | `feedback_category_match` | `change_status`, `auto_assign` | **inert** |
| Negative Sentiment Alert | `sentiment_pattern` | `send_notification`, `draft_response` | **inert** |
| Positive Feedback Follow-up | `feedback_category_match` | `draft_response` | **inert** |
| Churn Prevention | `health_score_threshold` | — | works (backend path) |
| Usage Decline Outreach | `usage_trend` | — | works (worker mirror), ships in shadow |

Only **two** templates work, and one of those ships disabled by default. The union of
actions the four inert templates require is `auto_assign`, `change_status`,
`send_notification` **and** `draft_response` — i.e. every action type except
`run_playbook`. See R2 and Risk 6.

This was known internally and deliberately deferred — `automation_churn_trigger.py`'s
docstring names it "a pre-existing dead import … that has silently never fired," and warns
that mirroring the full engine would "silently activate those triggers, an unintended
behaviour change." That warning is respected here (see R3).

### Defect B — the `slack` notification channel is silently dropped, and the log lies

`AutomationEngine._execute_notify` (`services/backend-api/src/services/automation_engine.py:485-571`)
implements only `dashboard` and `email`:

```python
if "dashboard" in channels: ...
if "email"     in channels: ...
```

There is no `slack` branch and no `else`. But `src/config/automation_templates.py:72`
(Critical Bug Escalation) ships `"channels": ["dashboard", "email", "slack"]`, with a
description that reads *"notifies all channels"*.

Worse, the action returns `{"error": None}` unconditionally (`automation_engine.py:567-571`).
A rule whose only channel is `slack` therefore records `status="success"` with
`notifications_created: 0`. **The execution log does not merely omit the failure — it
reports success.**

`SendNotificationConfig` (`src/api/routes/automations.py:171-174`) has no validator on
`channels` (unlike `ChangeStatusConfig.status` and `DraftResponseConfig.tone`, which do
validate), so an undeliverable channel passes the API cleanly.

### Evidence this is real

A v1.0.0 user asked to be pinged in Slack when incoming feedback crosses a sentiment
threshold. The natural answer — "enable the Negative Sentiment Alert template" — points at
a rule that cannot fire, and whose Slack channel would be dropped even if it did. Both
defects sit directly between a real user and the thing they asked for.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| The two dead triggers actually evaluate | An analysed feedback item matching a rule produces an `AutomationExecution` row. Today: zero rows, ever. |
| No surprise activation | Every pre-existing rule on the two repaired triggers is in `mode="shadow"` after upgrade; zero actions execute on first deploy. |
| Slack is delivered | A rule with `channels:["slack"]` and an active Slack integration produces a Slack post. |
| The execution log stops lying | An undeliverable channel yields `status="partial_failure"` with a non-null `error`, never `success`. |
| No regressions | Backend + worker suites green; the currently-working `health_score_threshold` / `churn_risk_level_change` paths behave identically. |

**Explicit non-goal:** no claim about how *useful* the newly-live triggers are. This
restores advertised behaviour; it does not argue the behaviour is well-designed.

---

## Requirements

### Must-have

- **R1 — Worker-side trigger mirror.** Add
  `services/worker-service/src/services/automation_feedback_trigger.py` implementing only
  the `feedback_category_match` and `sentiment_pattern` triggers, following the precedent
  of `automation_churn_trigger.py` / `automation_usage_trend_trigger.py`. Replace the dead
  import at `analysis.py:175`.
  - Cooldown semantics **identical** to the backend engine — Redis DB 1, key
    `automation_cooldown:{rule_id}:{customer_email}`, TTL `cooldown_hours * 3600` — so a
    cooldown set by either process is honoured by both.
  - Writes `AutomationExecution` rows in the same shape as `_log_execution`.
- **R2 — Action support in the mirror. ⚠️ AMENDED after self-critique.** The first draft
  said "must support `send_notification`". That was **wrong**. The four inert templates
  between them require `auto_assign`, `change_status`, `send_notification` **and**
  `draft_response` — every action type except `run_playbook`. Supporting only
  `send_notification` would leave Feature Request Triage (which has no notification action
  at all) and Positive Feedback Follow-up still completely inert.
  - **Consequence to accept openly:** this is no longer a "narrow" mirror in the sense the
    existing two are. `automation_churn_trigger.py` and `automation_usage_trend_trigger.py`
    each mirror *one* trigger and *one* action. This mirrors two triggers and four actions
    — effectively the whole engine minus `run_playbook`. See Risk 6; this is the strongest
    argument for revisiting the architecture decision.
  - Worker already has `Notification`, `AutomationRule` and `AutomationExecution` models,
    `src/email.py`, and Slack senders in `src/tasks/alerts.py`. It also has
    `run_playbook` support already (in the other two mirrors) if it is ever wanted here.
  - **Alternative if the duplication is judged unacceptable:** support the actions the
    templates need, and have the mirror record an explicit `error` for any action type it
    does not implement — never a silent skip. That is the same loudness principle as R5.
- **R3 — Shadow-on-repair migration.** A data migration sets `mode="shadow"` on existing
  **active** rules whose `trigger_type` is `feedback_category_match` or `sentiment_pattern`.
  Rules on every other trigger are **untouched** — they have been firing correctly via the
  backend and must not be disturbed. Operators opt each rule back into `active` after
  reviewing shadow entries.
- **R4 — Slack channel in `_execute_notify`.** Add a `slack` branch that posts via the
  org's active `type="slack"` integrations. Must work **webhook-only**, with no Slack OAuth
  app configured (`SLACK_CLIENT_ID` unset) — that is the common self-hosted case.
- **R5 — Loud failure.** Two parts, both chosen explicitly:
  - Set a real `error` on the action result so the execution row becomes
    `partial_failure` rather than a false `success`.
  - Emit `logger.warning` for any unrecognised channel string (the missing `else`),
    matching the idiom the email branch already uses.
- **R6 — Slack failure must not break the rule.** A Slack post that fails is logged and
  recorded as a channel error; it must not abort the dashboard/email channels or the
  remaining actions. This mirrors the existing per-channel `try/except` on email
  (`automation_engine.py:550-565`).

### Should-have

- **R7 — Reuse, don't add a fourth sender.** Slack sending is already implemented twice
  (`backend-api/src/api/routes/integrations.py:216` returns a status dict and never raises;
  `worker-service/src/tasks/alerts.py:207` raises), and the integration-selection loop three
  times. Reuse the existing sender appropriate to each process; do not write a new one.
- **R8 — Multi-integration behaviour.** An org may legitimately have **several** active
  `type="slack"` rows — both indexes on `integrations` are non-unique. Follow the existing
  precedent in `_dispatch_slack_health_alert`: post to **all** active Slack integrations.

### Nice-to-have (not this branch)

- **R9** — Backfill suppression beyond shadow mode (e.g. ignoring feedback older than the
  deploy) if shadow review proves noisy.

---

## Technical Considerations

**Architecture decision (settled):** narrow worker-side mirror, not a shared package.
There is no Python sharing seam — `shared/` is a pnpm UI package (`@rereflect/ui`), and
nothing in Python imports it. The alternative (promoting the engine into a directory copied
into both images, as `analysis-engine/src/analyzer` already is) was rejected as too large a
blast radius for a bug fix. **Accepted cost: a third copy of engine logic that can drift.**
Mitigate with a pointer comment in both directions.

**Services changed:** `worker-service` (new mirror, `analysis.py` import),
`backend-api` (`automation_engine.py` slack branch + error contract, Alembic migration).
**Frontend: unchanged** — see Out of Scope.

**Multi-tenancy:** every query filters `organization_id`; Slack integrations resolve per-org.

**Migration:** one Alembic revision for R3. Repo runs a **single** Alembic head and CI
asserts it — run live `alembic heads` to find the real parent; do not grep version files
for `down_revision`.

**Testing constraints (from the dig — these are traps):**
- `_execute_notify` imports `send_alert_email` **lazily inside the method**. Mock at the
  source module (`patch("src.services.email_service.send_alert_email")`), **not** at
  `src.services.automation_engine`, where the name never exists. Any new Slack branch
  following the same lazy-import idiom must be mocked the same way.
- `conftest.py` has an autouse `_disable_emails` fixture but **no equivalent for Slack**.
  Any test touching the Slack path must mock explicitly or it will attempt a real network
  call.
- Tests use local helper functions (`_make_rule`, `_make_feedback`) plus the
  `test_organization` fixture — not factories.
- This worktree has **no venv**. Create it with `python3.12` explicitly; the system
  `python3` is 3.9.6 and fails on Authlib.

**No plan gates.** `SELF_HOSTED=true` makes `require_feature` inert; adding a tier gate
would be the exact drift that broke ~40 tests before 1.0.0.

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Repairing the import activates rules users configured months ago that have never run. | R3 shadow migration. This is the single largest risk and the reason shadow was chosen over immediate activation. |
| 2 | Mirror drift — a third copy of trigger/action logic. | Accepted, explicitly. Cross-referencing comments in both files; mirror kept deliberately narrow. |
| 3 | Alert storm on first activation if an org has a large backlog of matching feedback. | Shadow mode absorbs the first pass; R9 held in reserve. |
| 4 | Slack posts to *all* active integrations could double-notify an org that configured two. | Matches existing health-alert behaviour; consistency preferred over a new, divergent rule. |
| 5 | Worker's Slack sender **raises** while backend's **returns a status dict**. Mixing them up silently changes failure semantics. | R7 — use the process-appropriate sender; assert the contract in tests. |
| 6 | **The mirror is no longer narrow (see R2).** Four actions + two triggers duplicated into the worker is close to a second engine. Drift risk is materially higher than the two existing one-trigger/one-action mirrors, and the next person to change a trigger has three places to look. | Unresolved. This weakens the architecture choice made before the action set was known. Flagged at the review gate rather than silently absorbed. |

**Post-deploy verification (was missing — added after self-critique)**
1. Deploy, confirm no `AutomationExecution` rows with `status != "shadow"` appear for the
   two repaired triggers.
2. Confirm shadow rows *do* appear as feedback is analysed — that is the proof the import
   is genuinely fixed rather than failing in a new way.
3. Flip one rule to `active` and confirm delivery on each configured channel.

**User-facing communication (was missing — added after self-critique)**
The v1.0.0 reporter was told, in a draft reply, that the "Negative Sentiment Alert"
template fires on 3+ negative feedbacks in 7 days. **That statement is false today.** The
reply must be corrected before it is sent, regardless of when this fix ships.

**Open questions**
- Should shadow-mode entries be surfaced with a UI prompt ("3 rules are in shadow after an
  upgrade — review them"), or is the existing execution log enough? *Leaning: execution log
  for this branch; a prompt is a separate UX change.*
- Does anyone rely on the current false `success` status in the execution log for
  reporting? *Believed no — the status is internal — but worth a grep before shipping.*

---

## Out of Scope

- **Channel-selector UI.** The automations pages have **no** channel selector at all today,
  not even dashboard/email — `channels` is a hardcoded literal
  (`new/page.tsx:265,382`; `[id]/page.tsx:529` sets `config: {}`). Building one is
  net-new UI work, not a bug fix. Users reach Slack via the Critical Bug Escalation template
  or the API. **Tracked as follow-up.**
- **Write-time channel validation** on `SendNotificationConfig`. Considered and explicitly
  declined in favour of loud runtime failure.
- **Batch-level sentiment trigger** (the user's actual feature request — a threshold across
  an incoming batch, versus today's per-customer `sentiment_pattern`). New trigger type;
  DEV-TRACKING P1.
- **Native Discord support.** DEV-TRACKING P2.
- Refactoring the three duplicated Slack integration-selection loops, or the two duplicated
  sender pairs. Real debt, wrong branch.
- The two other worker mirrors (`automation_churn_trigger.py`,
  `automation_usage_trend_trigger.py`) and their `run_playbook`-only scope.
