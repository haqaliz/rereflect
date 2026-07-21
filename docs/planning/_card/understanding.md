# Understanding — usage-trend-churn-signal (Phase 2 dig synthesis)

Synthesis of three read-only digs (usage subsystem, churn/health recompute path, frontend
surfaces) plus direct verification by the integrator. All paths are relative to the worktree
`.claude/worktrees/feat-usage-trend-churn-signal/`. This note is input to the requirements
interview.

## What the feature is really asking

Detect that a customer's **product usage has fallen** and turn that into a churn signal at the
**customer level**, so a customer who goes quiet is caught even though they file no feedback.

The brief's own framing — "add a usage factor to the 9-factor churn scorer"
(`docs/planning/product-usage-enrichment/prd.md:67`, `:126`) — is **the wrong shape**, and the
dig confirms why. `FeedbackItem.churn_risk_factors` is produced per feedback item and
aggregated for display in `api/routes/customers.py:1191-1259`. A silent customer produces no
feedback, so a per-feedback factor can never fire for the exact population this feature exists
to catch. The signal must attach to the customer-level path.

## The blocker, precisely characterised

`AI-TRACKING.md:432` rules out product-usage drop as an M5.3 label source: "blocked —
`customer_usage` keeps no history to detect a drop against."

That is **true of the rollup and false of the raw log**:

- `customer_usage` is one mutable row per `(organization_id, customer_email)`
  (`models/customer_usage.py:81-86`) — no history. Correct.
- `usage_event` retains **every** event. The documented "rolling 90 days (raw)" retention
  (`product-usage-enrichment/prd.md:91`) is **never implemented** — there is no prune task
  anywhere, while the beat has purges for webhook deliveries, automation executions, playbook
  executions, calibration models and notifications (`worker-service/src/celery_app.py:170-212`).
  `prd.md:118` still lists the retention default as an open question.
- `GET /api/v1/customers/{email}/usage?days=30|60|90` already builds a daily-bucketed time
  series live from `usage_event` (`api/routes/customers.py:1345-1370`).

So trend is derivable **today** — but resting on a table with an unbounded-growth defect.

## Four pre-existing defects sitting in this feature's path

All verified directly, not merely reported.

### D1 — Rolling-window fields never re-window (highest impact)

`_compute_rollup_from_events` (`worker-service/src/tasks/usage_metrics.py:39-89`) computes
`active_days_7d/30d` and `login_count_7d/30d` against `now`. It has **exactly one call site**,
on the event-processing path (`:208`). The daily `recompute_usage_scores` (`:306-355`) only
calls `compute_usage_score(row, now)` — it never re-derives the window fields.

Consequence: for a customer who stops sending events, the frequency fields **freeze at their
last-event values forever**. Only the recency band moves with time.

- `usage_score`'s frequency term (weight 0.30, `usage_score_service.py:80-82`) stays inflated
  indefinitely.
- **`silent_churner` becomes unreachable.** That segment gates on `active_days_30d <
  FREQUENCY_LOW_MOD_DAYS` (=5) (`segment_service.py:120-130`) — the segment purpose-built to
  catch silent customers can never fire for one. `dormant` (`:133-137`) still works because it
  reads `last_active_at`, which is time-relative.
- The existing regression test passes only because its fixture hand-sets `active_days_30d=0`
  (`worker-service/tests/test_usage_metrics.py:359`), presupposing the very re-windowing that
  does not happen. Green test, wrong production behaviour.

**Fixing D1 delivers a meaningful share of this feature's value on its own.**

### D2 — No retention + O(lifetime) reprocessing

No `usage_event` pruning exists (above). Meanwhile `_do_process_usage_event` re-reads **all**
events for the customer on **every** event, with no time bound
(`usage_metrics.py:202-206`), and full-re-aggregates. That is O(lifetime events) per single
event against an unbounded table — the cost compounds with tenure.

### D3 — Celery enqueue failure is swallowed

`api/routes/usage_webhooks.py:172-180` logs a warning and still counts the event `accepted`
when `send_task` fails. Nothing ever re-scans `usage_events` for un-rolled-up rows, so a Redis
blip silently and permanently drops events from the rollup. The inline comment claims "worker
can retry"; no such retry path exists.

### D4 — The usage opt-in is unreachable, and destroyed if weights are ever saved

- Backend accepts six weights, `usage` and `crm` as `Field(default=0)`, sum-to-100 validated
  (`api/routes/categories.py:145-158`), persisting `config.health_weight_usage = data.usage`
  (`:201`).
- Frontend `HealthWeightsEditor` is a **four-key** form (`components/settings/HealthWeightsEditor.tsx:10-29`),
  mounted only at Settings → AI (`app/(dashboard)/settings/ai/page.tsx:378`), and
  `updateHealthWeights` sends only those four keys (`lib/api/categories.ts:65-68`).

Two consequences. The usage weight is **editable nowhere in the product** — M3.2's opt-in is
reachable only via the API. And because the PUT model defaults the omitted keys to 0, **any
operator who saves health weights in the UI silently zeroes their usage and CRM weights**,
wiping an API-configured opt-in. This is silent data loss affecting two shipped features (M3.2
usage, M3.1 CRM component).

In-product copy compounds it: `settings/usage-events/page.tsx:208-216` and
`ComponentProgressBars.tsx:32` both direct operators to Settings → Preferences to raise the
usage weight; that page has no weight editor (`settings/preferences/page.tsx`).

## The central architectural constraint (calibration trap)

`churn_probability` is **not** derived from the health score. `probability_updater.update`
computes it from `health.churn_risk_component` **alone**
(`worker-service/src/services/probability_updater.py:75`), then applies the org's isotonic
calibration model and a bootstrap CI, and derives `time_to_churn_bucket` from probability ×
sentiment trend (`:76-85`).

`churn_risk_component` is the inverted average of feedback-level `churn_risk_score`
(`health_score_service.py:190`) — **purely feedback-derived**. Usage does not feed churn
probability at all today, even at a non-zero usage weight: usage moves `health_score`, not
`churn_risk_component`.

Therefore:

1. **Naively folding usage into `churn_risk_component` would silently corrupt every org's
   calibration.** The isotonic model was fitted against the distribution of the feedback-only
   score; changing what that input means invalidates the fitted mapping without any error
   surfacing. Any such change needs an explicit refit/versioning story.
2. **The hysteresis guard hides silent customers.** `_should_skip` returns True when
   `churn_risk_component` moved < 2 points versus the latest history snapshot
   (`probability_updater.py:118-141`). A customer with no new feedback has an unchanged
   component → skip → **probability frozen**. Same theme as D1: the silent customer is
   structurally invisible.

## Useful existing seams

- **Daily scan hook.** `recompute_usage_scores` already iterates every `customer_usage` row
  daily at 04:00 UTC (`celery_app.py:216-219`) and calls `update_customer_health` when the
  score moves ≥ 2 points (`usage_metrics.py:346-347`). A durable daily snapshot, or a
  re-windowing fix, lands here cheaply.
- **Drop-detection precedent.** `_check_health_drop_alert` (`health_score_service.py`, called
  from `update_customer_health`) is an existing drop-alert pattern to mirror. Note it passes
  only the four base components and omits `usage`/`crm`.
- **History-table precedent.** `customer_health_history` is the shape a durable
  `customer_usage_history` would mirror.
- **Automation trigger seam.** Trigger types are centralized: engine dispatch at
  `automation_engine.py:221-222`, worker-side evaluator `automation_churn_trigger` fired from
  `probability_updater.py:95-96`, per-(rule, customer) Redis cooldown, and `mode`
  off/shadow/active. Frontend adds a type via `TRIGGER_TYPE_LABELS` (`lib/api/automations.ts:134-140`)
  plus a config branch in both the new and edit pages — and three existing automations specs
  mock `TRIGGER_TYPE_LABELS` inline, so they need updating too.
- **Timeline event seam.** Add to the `ActivityEvent['type']` union (`lib/api/customers.ts:212-226`)
  and `eventIconMap` (`components/customers/ActivityTimeline.tsx:46-116`); copy is
  server-generated and rendered verbatim. `playbook_auto_run` is the worked example.

## Open questions for the interview

1. **Scope of the defects.** D1 is arguably a prerequisite (a drop detector built on frozen
   frequency fields is built on sand) and may be the best first slice on its own. D4 decides
   whether the signal is reachable by an operator at all. D2/D3 are adjacent reliability debt.
   Which are in scope?
2. **Where the signal lands.** Health score only (safe, but usage weight defaults to 0 and is
   uneditable — see D4), or churn probability (high value, but the calibration trap above)?
3. **Storage.** Derive trend from raw `usage_event` (works today, unbounded table) vs. a
   durable `customer_usage_history` snapshot written by the existing daily task (bounded, but
   starts empty — no retroactive history)?
4. **Drop definition.** Relative decline vs. inactivity streak vs. both; comparison window;
   and the cold-start guard (minimum history before the signal may fire) — a new customer with
   two days of data must not read as a "drop".
5. **Byte-stability.** M3.2 guaranteed unchanged scores at usage weight 0. Does a D1 fix
   count as an acceptable break of that guarantee? It *will* change existing scores for orgs
   that opted in — correctly, but visibly.
