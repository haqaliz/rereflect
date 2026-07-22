# Card — usage-trend-automation-trigger (freeform feat, no GitHub issue)

**Type:** feat
**Slug:** usage-trend-automation-trigger
**Branch:** `feat/usage-trend-automation-trigger`
**Source:** Freeform task selected via `rereflect-next` on 2026-07-23. No GitHub issue.

## Brief (from rereflect-next handoff, verbatim)

> Build N1+N2 from `docs/planning/usage-trend-churn-signal/prd.md:158-160` — the deferred
> follow-on to M3.2b (merged `6270adc`): a `usage_trend_change` customer-timeline event plus a
> new `usage_trend` automation trigger that composes with churn-playbook auto-run. Model it
> directly on M4.1.5 `churn-triggered-playbooks` (`AI-TRACKING.md:260-273`, commits
> `9aa6650`..`f133ccf`): same `AutomationRule.mode` off/shadow/active, same per-(rule, customer)
> Redis cooldown, same cooldown-seeding-on-activation so an already-declining cohort doesn't
> stampede — fire it from the daily `recompute_usage_scores` seam instead of the
> churn-probability recompute. Do NOT let this touch `churn_risk_component`,
> `churn_probability`, or the isotonic calibration; the trend stays a usage-health-component
> signal. Caveat to design around, not discover: the `customer_usage_history` snapshot only
> began 2026-07-22, so most customers are `insufficient_history` for ~2 more weeks — that state
> must be an explicit non-fire, and shadow should be the sensible default mode. Out of scope:
> D2 (`usage_event` retention / O(lifetime) re-read) and D3 (swallowed enqueue) — those get
> their own branch.

## Why this was picked (citations)

- `docs/planning/usage-trend-churn-signal/prd.md:158-160` — deferred **N1** (`usage_trend_change`
  customer-timeline event) and **N2** (a `usage_trend` automation trigger composing with
  churn-playbook auto-run), with N2 described verbatim as "the natural follow-on that
  reconnects the signal to the action loop."
- `AI-TRACKING.md:216-223` — M3.2b `usage-trend-churn-signal` COMPLETE (shipped 2026-07-22);
  its deferred list names "a `usage_trend` automation trigger + timeline event (N1/N2)".
- `AI-TRACKING.md:260-273` — M4.1.5 `churn-triggered-playbooks` COMPLETE (2026-07-19): the
  exact pattern to reuse (new trigger type, `run_playbook` action, `AutomationRule.mode`,
  per-(rule, customer) Redis cooldown, cooldown seeding on activation).
- `services/backend-api/src/models/automation_rule.py:59` — `trigger_type` comment enumerates
  the 5 existing triggers; **no `usage_trend`**.
- `services/backend-api/src/services/automation_engine.py:221,693-716` — the
  `churn_probability_threshold` evaluation branch and the activation-time cooldown seeding
  guarded on `rule.trigger_type != "churn_probability_threshold"`.

## Moat rationale

The trend signal currently terminates in the usage **health component** only
(`AI-TRACKING.md:220`), and usage weight defaults to 0 — so for most operators it ships
dormant and nothing acts on it. Wiring it into the automation engine reconnects it to the
already-shipped churn → health → playbook → automation loop without touching the calibrated
churn math. Fits OSS/self-hosted (no plan gate, no SMTP requirement — `run_playbook` is
already SMTP-free per `AI-TRACKING.md:273`).

## Known caveats to resolve in the dig / PRD

1. **Cold start is the default state, not an edge case.** `customer_usage_history` began
   accumulating 2026-07-22, so most customers sit in `insufficient_history` for ~2 more weeks.
   That state must be an **explicit non-fire** (never coerced to `stable`), or the trigger
   looks broken on day one.
2. **Fire on *change*, not on every daily pass.** The dig must confirm whether a previous
   `usage_trend_state` is persisted; without it, a naive evaluator re-fires daily for every
   declining customer (the cooldown mitigates but does not fix the semantics).
3. **Scope fence.** `churn_risk_component`, `churn_probability`, and the isotonic calibration
   are out of bounds — M3.2b's guarantee that they are "provably untouched"
   (`AI-TRACKING.md:220`) must survive this branch.
4. **Shadow as the sensible default.** `AutomationRule.mode` already supports
   `off`/`shadow`/`active`; operators should be able to watch the trigger before arming it.
5. **Stampede on activation.** M4.1.5 seeds per-customer cooldowns when a rule activates
   (`automation_engine.py:693-716`); the same guard is needed here or an already-declining
   cohort all fires at once on the first recompute.

## Open questions for the interview

1. What is the trigger's *condition* surface — fire on entering `declining` / `sharp_decline`,
   on any state worsening, on a `usage_trend_pct` threshold, or a combination?
2. Should recovery (declining → stable) be a fireable transition too, or is this
   decline-only?
3. Does N1's `usage_trend_change` timeline event write on **every** state change (including
   improvements and the first transition out of `insufficient_history`), or only on declines?
4. Where does the evaluator run — inline in the daily `recompute_usage_scores` task, or as a
   separate task fanned out after it?
5. Does the automations UI need a new config form for the trigger, and what are the field
   labels/defaults?

**NOTE:** `CLAUDE.md`'s billing / plan-gating / Stripe / Resend sections are STALE
(pre-OSS-pivot). All features are unlocked (MIT, self-hosted, BYOK). Do not gate this feature
behind a plan tier.
