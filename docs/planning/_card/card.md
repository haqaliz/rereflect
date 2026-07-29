# Card — batch sentiment threshold trigger

**Type:** feat · **Slug:** `batch-sentiment-trigger` · **Branch:** `feat/batch-sentiment-trigger`
**Source:** direct v1.0.0 user request. No GitHub issue. **DEV-TRACKING P1.**

---

## The user's words

> "Honestly the bring your own key setup is really nice, but it would be great if you could
> plug in a Slack or Discord webhook to get pinged whenever **a batch of new feedback crosses
> a certain sentiment threshold**. Would make triaging way faster for our team."

Two asks in one sentence. The delivery half (Slack) and the Discord half are handled
separately (Slack shipped in `52c763dd`; Discord is DEV-TRACKING P2). **This card is the
trigger half only.**

## Why today's triggers don't cover it

`sentiment_pattern` fires when **one customer** sends ≥ `count` feedbacks of a given
sentiment within `days`. It is a *per-customer* signal — "this account is souring".

The user is asking about *aggregate* sentiment — "our incoming feedback as a whole just got
worse". A spike of angry feedback from 30 different customers trips nothing today, because no
single customer crosses the per-customer count. That is precisely the triage case they
describe.

## Decisions already made (do not re-litigate)

- **Rolling time window, not per-import.** Evaluate the org's feedback over a configurable
  trailing window. "A batch" is undefined for streaming sources — Zendesk, Intercom, email
  forwarding, the public API all arrive continuously — so a per-import trigger would silently
  never fire for most ingestion paths. That silent-never-fires failure mode is the exact class
  of bug fixed twice already this session, and is not worth reintroducing deliberately.
- **Threshold configurable on both axes** — negative *share* (percentage) and *absolute
  count* — rather than picking one for the user. This was the open question in the reply
  draft; making it configurable answers it by design.
- Delivery reuses the existing notification channels. No new delivery code.

## Prior art to follow

- `sentiment_pattern` in `services/worker-service/src/services/automation_feedback_trigger.py`
  (the worker mirror that actually evaluates feedback triggers in production).
- The `usage_trend` trigger is the closest structural precedent for a *state* trigger with a
  config object and a frontend checkbox group.
- `usage_decline_outreach` template ships in `mode="shadow"` — good precedent for a new
  trigger whose firing rate is unknown on real data.

## Open questions for the PRD

- **Cooldown identity.** Every existing cooldown key is
  `automation_cooldown:{rule_id}:{customer_email}`. A batch trigger is org-wide with no single
  customer. What goes in that slot, and does an empty string collide with anything?
- **Evaluation cadence.** Evaluate on every analysed feedback item (cheap per item, but the
  window query runs constantly), or on a Celery beat schedule (fewer queries, coarser
  latency)? Latency matters for a triage alert.
- **Minimum sample size.** 2 negative out of 3 total is 67% and almost certainly noise. Does
  the trigger need a floor before a percentage threshold is meaningful?
- **What does `feedback_id` mean in the execution log** for a trigger that is about many items?
- Should it ship in `shadow` by default, like `usage_decline_outreach`?
