# PRD — Usage-Trend Timeline Event & Automation Trigger (N1 + N2)

**Slug:** `usage-trend-automation-trigger`
**Branch:** `feat/usage-trend-automation-trigger`
**Type:** feat (freeform; no GitHub issue)
**Status:** Draft for review gate
**Author:** Rereflect (via `rereflect-begin-fast`)
**Date:** 2026-07-23

---

## Problem Statement

M3.2b (`usage-trend-churn-signal`, shipped 2026-07-22, merge `6270adc`) detects that a
customer's product usage is declining and classifies it into
`insufficient_history | stable | declining | sharp_decline`
(`services/worker-service/src/services/usage_score_service.py:239-242`).

That signal currently terminates in exactly one place: a bounded penalty on the **usage health
component** (`health_score_service.py:107` via `apply_trend_penalty`). And the usage component's
weight defaults to **0** (`health_score_service.py:25-32`). So for every operator who has not
explicitly opted in, a customer going quiet is detected, classified, stored — and then changes
nothing anyone can see or act on.

**Who has this problem:** self-hosting operators running the usage-events receiver who want a
declining customer to trigger the same save motion that a high churn probability already
triggers (M4.1.5 churn-triggered playbooks, shipped 2026-07-19).

**Evidence it's real:** the gap is a documented, deliberate deferral. M3.2b's own PRD lists
**N1** (`usage_trend_change` timeline event) and **N2** (a `usage_trend` automation trigger
composing with churn-playbook auto-run) as explicit v2, describing N2 verbatim as *"the natural
follow-on that reconnects the signal to the action loop"*
(`docs/planning/usage-trend-churn-signal/prd.md:158-160`). `AI-TRACKING.md:223` repeats it in
M3.2b's honest-deferral list.

**Cost of the status quo:** the detection half of the feature is built and the action half is
missing, so M3.2b's value is latent. An operator who notices a decline must find it by opening
a Customer 360 page one customer at a time.

---

## Goals & Success Metrics

### Success metrics (observable after launch)

- **SM1 — The addressable population is non-zero and measurable.** An operator can see how many
  of their customers currently hold a real (non-`insufficient_history`) trend state, i.e.
  whether this trigger *can* fire for them at all.
  - *Why this is the first metric:* the entire feature is downstream of an unvalidated
    dependency (A1 below). This number is the honest answer to "is this firing into an empty
    room?", and it is the only metric here that can falsify the feature. Precedent: the M5.0
    AI-readiness card (`GET /api/v1/analytics/ai-readiness`) reports per-org counts with honest
    ready/not-ready flags rather than asserting readiness.
- **SM2 — Operators discover the trigger without being told it exists.** Measured by the
  pre-built template (M10) being enable-able from the existing template picker, rather than the
  trigger being reachable only by an operator who already knows to look for it.

### Exit criteria (branch is done when these pass)

These are build-completion checks, not evidence of value — labeled as such deliberately.

- **E1 — A decline can drive an action without a human noticing it first.** An end-to-end test
  drives a real `stable → declining` transition through the daily recompute and asserts a
  `ChurnPlaybookExecution` row is created and the playbook task dispatched.
- **E2 — A trend change is visible in the customer's history.** `usage_trend_change` events
  appear in `GET /api/v1/customers/{email}/timeline`, correctly ordered and cursor-paginated,
  asserted by tests mirroring the `TestTimelinePhase6` pattern.
- **E3 — Nothing fires spuriously during the warm-up.** A test drives
  `insufficient_history → sharp_decline` and asserts zero executions.
- **E4 — The churn stack stays byte-identical.** The existing
  `tests/test_usage_trend_churn_boundary.py` stays green, **unmodified**.

### Assumptions (stated, not validated)

- **A1 — Someone has instrumented usage events.** The whole feature requires an operator to
  have wired their product into `POST /api/v1/webhooks/usage`, accumulated 14+ days of
  snapshots, and to have customers clearing the ≥5 active-day baseline floor (R4). We have **no
  evidence** about how many operators clear the first condition — it requires deliberate
  engineering on their side. SM1 exists to measure this rather than assume it.

**Explicit non-goal:** we are not claiming this improves churn *prediction*. It changes what
happens when an already-computed signal changes state. The trend does not enter the churn
model, by design (E4).

---

## User Personas & Scenarios

**Persona: self-hosting CS/ops operator.** Runs Rereflect on their own infra, has wired their
product's usage events into `POST /api/v1/webhooks/usage`, and already uses churn playbooks.

*Scenario 1 — arming the rule.* Creates an automation rule: trigger `usage_trend`, target
states `declining` + `sharp_decline`, action `run_playbook` → "At-Risk Outreach". It defaults
to **shadow**, so for the first two weeks they watch the execution log fill with
would-have-run entries without anything being sent. Once the log looks right, they flip it to
active.

*Scenario 2 — the save.* Customer's 14-day active-days drops from 9 to 4. The nightly recompute
classifies `sharp_decline`; the rule fires; the playbook runs; a `playbook_auto_run` event and
a `usage_trend_change` event both land on the customer's timeline, so the operator opening the
profile sees *why* the outreach happened.

---

## Requirements

### Must-have

**M1 — Capture the transition at the daily seam, act after the commit.**
`recompute_usage_scores` already computes `trend_state_changed` at
`services/worker-service/src/tasks/usage_metrics.py:589`, while the old value is still live,
and discards it on the next line. Capture `old_trend_state` into a local, accumulate
`(organization_id, customer_email, old_state, new_state)` tuples during the loop, and **drain
them after `db.commit()`** (`usage_metrics.py:611-612`).

Rationale: the loop scans every `customer_usage` row across **all orgs** with no per-org filter
(`:532`) and commits **once** after the loop. Firing actions inside the loop would execute
against uncommitted state — the existing in-loop `_call_update_health` hook (`:604-609`) is not
a valid precedent, because it recomputes a score rather than executing an external action.

**M2 — Edge-triggered semantics, with `insufficient_history` as a baseline seed.**
The trigger fires **only on a transition into a strictly worse state**, over the severity
ordering `stable (0) < declining (1) < sharp_decline (2)`.

- `stable → declining`, `stable → sharp_decline`, `declining → sharp_decline` → **fire**
- `declining → declining` (no transition) → silent
- `sharp_decline → declining`, `declining → stable` (recovery) → **never fires** in v1
- **Any transition involving `insufficient_history`, in either direction, never fires.**

`insufficient_history` has no severity rank — it means "we don't know yet", not "healthy".
Treating a customer's *first* real classification as a change would fire for every customer who
lands in `declining`/`sharp_decline` on the same day the snapshot history matures — a
warm-up stampede. Instead the first observation **seeds a baseline silently**, matching the
non-destructive first-observation baseline-seed already shipped for Jira, Zendesk and Asana
status-sync (`AI-TRACKING.md:59-61`).

Consequence worth stating plainly: **edge-triggering makes activation-time cooldown seeding
unnecessary.** `seed_churn_cooldowns` exists because `churn_probability_threshold` is
*level-based* and re-fires while the level persists (`automation_engine.py:701-711`). An
already-`declining` customer produces no transition, so there is nothing to stampede. The
per-(rule, customer) cooldown is retained as a safety net, not as the primary guard, and
`seed_churn_cooldowns` stays churn-only.

**M3 — Persist trend state on the daily snapshot.**
Add `usage_trend_state` (String(30), nullable) and `usage_trend_pct` (Float, nullable) to
`customer_usage_history` (`services/backend-api/src/models/customer_usage_history.py:48-55`),
with an additive Alembic migration and a matching update to the worker's mirror model
(`services/worker-service/src/models/__init__.py:1004-1032`). The existing column-parity test
`test_worker_and_backend_customer_usage_history_columns_match` must stay green.

**Ordering defect to fix as part of this:** the snapshot payload is currently assembled at
`usage_metrics.py:563-573`, **before** trend classification at `:583-593`. Written naively, the
snapshot would record the *previous* trend state. The payload must be built (or amended) after
classification.

**M4 — `usage_trend_change` timeline event, derived at read time.**
Add a `_fetch_usage_trend_changes` source to `customer_timeline_service.py` that reads the
customer's `customer_usage_history` rows (bounded: 180-day retention,
`usage_metrics.py:46`) and emits one event per state change between consecutive snapshots.
Wire it into `build_timeline` (`:637-730`), and extend `ActivityEvent`
(`api/routes/customers.py:186-203`), `_timeline_event_to_activity` (`:930-948`) and the
hand-maintained public mirror `PublicActivityEvent` (`api/routes/public_api.py:1044-1065`).

Unlike the trigger, the timeline event **reports every state change in both directions**,
including recovery and the first exit from `insufficient_history` (rendered as the customer's
trend becoming measurable). The timeline is a record, not an actuator; suppressing recoveries
there would make the history misleading.

**M5 — Worker-side trigger evaluator (mirror pattern).**
The worker cannot import the backend's `AutomationEngine`. Add
`services/worker-service/src/services/automation_usage_trend_trigger.py`, modeled directly on
`automation_churn_trigger.py`: the worker's lightweight `AutomationRule` mirror, `mode` gating
(`off` excluded at SQL level, `shadow` logs without executing), `AutomationExecution` logging,
and **only** the `run_playbook` action. It must reuse Redis `db=1` and the identical key scheme
`automation_cooldown:{rule_id}:{customer_email}` (`automation_churn_trigger.py:49,88,101`) so
cooldowns are honored across both processes. Per-rule exceptions stay isolated and must never
fail the daily recompute.

Do **not** grow the mirror into a general engine — the existing module docstring
(`automation_churn_trigger.py:16-21`) explicitly warns against exactly that.

**M6 — Register the trigger type everywhere it must be registered.**
Backend: `VALID_TRIGGER_TYPES` (`api/routes/automations.py:49-55`); a `UsageTrendConfig`
Pydantic schema + branch in `TriggerSchema.validate_trigger` (`:74-127,180-201`); a
`_trigger_usage_trend` checker + dispatch branch (`automation_engine.py:208-225`); and the
context-shape docstring (`:76-81`).
Frontend: `TriggerType` union and `TRIGGER_TYPE_LABELS` (`lib/api/automations.ts:5-10,134-140`);
config form + defaults in **both** `new/page.tsx:98-194,343-350` and the duplicated
`[id]/page.tsx:78-236,611-619` (with `disabled={!isAdminOrOwner}` wiring); and the hand-copied
`TRIGGER_TYPE_LABELS` mock in **every** affected test file.

Trigger config shape: `{ states: ["declining", "sharp_decline"] }` — a non-empty subset of the
two ranked at-risk states. `insufficient_history` and `stable` are rejected as target states
(422), since neither can be entered as a worsening transition.

**M7 — `usage_trend` rules default to shadow.**
A new rule of this trigger type defaults to `mode: "shadow"`, diverging from the global
`active` default (`new/page.tsx:319`). This requires a per-trigger-type default in both the
create and edit forms. Every other trigger type keeps defaulting to `active` — no change to
existing behavior.

**M8 — Fix shadow-mode rendering in the execution log.**
`AutomationExecution.status` is typed `'success' | 'partial_failure' | 'failed'`
(`lib/api/automations.ts:50`) but the backend writes `'shadow'`
(`automation_engine.py:85-86,163-165`), and `StatusBadge`
(`app/(dashboard)/settings/automations/[id]/page.tsx:59-67`) falls through to a red
`destructive` "failed" badge for it. Add `'shadow'` to the union and a distinct, non-destructive
badge branch.

This is a **pre-existing M4.1.5 defect, not one this feature introduces**, pulled in
deliberately: M7 makes shadow the default for this trigger, and shipping a default mode that
the execution log reports as failure would be self-defeating.

**M9 — The churn fence holds.**
`tests/test_usage_trend_churn_boundary.py` must stay green **unmodified**. Nothing in this
branch may read from or write to `churn_risk_component`, `churn_probability`,
`churn_probability_low/high`, `calibration_model_id`, `time_to_churn_bucket`, or
`churn_calibrator.py`.

**M10 — Ship a pre-built template so the trigger is discoverable.**
Add a "Usage Decline Outreach" entry to `AUTOMATION_TEMPLATES`
(`services/backend-api/src/config/automation_templates.py`), so the trigger appears in the
existing template picker on the automations list page rather than only to operators who already
know to look for it.

*Rationale:* M3.2b's own PRD named discoverability as its primary risk — usage weight defaults
to 0, so *"for most operators this ships dormant"* — and it promoted the weights-editor field
from polish to must-have for exactly this reason. This feature has the same shape and needs the
same treatment. The machinery already exists (`GET /automations/templates`,
`POST /automations/templates/{id}/enable`, `TemplatePicker`), so the cost is one config dict
plus the two fixes below.

Two constraints found in the code that this requires:

- **Templates must be able to carry a `mode`.** `enable_template`
  (`api/routes/automations.py:490-501`) sets `is_active=True` and never sets `mode`, which the
  `@validates` hook promotes to `active` (`models/automation_rule.py:117-136`). As written, the
  template path would arm a rule immediately and silently bypass M7. Add an optional `mode` key
  to the template dict, honored by `enable_template`, defaulting to today's behavior when absent
  so the five existing templates are unaffected.
- **The template cannot use `run_playbook`.** `playbook_id` is a per-install autoincrement
  integer that a static config file cannot know. The template therefore ships with a
  `send_notification` action; the operator adds a playbook action themselves. Stating this
  plainly because it means the template demonstrates the trigger, it does not fully wire the
  save motion.

### Should-have

- **S0** — Surface the SM1 count (customers with a non-`insufficient_history` trend state) on an
  existing operator-facing surface, so the metric is real rather than aspirational. The M5.0
  readiness card is the precedent for the honest-count pattern.
- **S1** — Operator documentation in `docs/SELF_HOSTING.md`: what the trigger fires on, the
  baseline-seed rule, the ~14-day warm-up, the light-user coverage limit (R4), and why shadow
  is the default.
- **S2** — Timeline icon + color for `usage_trend_change` in `eventIconMap`
  (`components/customers/ActivityTimeline.tsx:46-116`); `CustomerTimeline` imports the same map,
  so one entry covers both surfaces. Unknown types already degrade to a muted dot, so this is
  polish rather than a crash guard.
- **S3** — `AI-TRACKING.md` + `CHANGELOG.md` entries recording N1/N2 as shipped and the M4.1.5
  shadow-badge fix.

### Nice-to-have (explicit v2)

- **V1** — Recovery (`declining → stable`) as a fireable transition, for automated
  "customer recovered" follow-ups.
- **V2** — `usage_trend_pct` magnitude in the trigger condition (e.g. "fire only if the drop
  exceeds 40%"), rather than state-only.
- **V3** — Per-org configurable decline thresholds (this is M3.2b's own deferred N4).
- **V4** — Surfacing the trigger's `trigger_snapshot` in the execution log UI (never rendered
  today for any trigger).

---

## Technical Considerations

**Services touched:** `worker-service` (seam capture, snapshot payload ordering, new evaluator
module, mirror model column), `backend-api` (migration + model, trigger registration, timeline
source, API schemas), `frontend-web` (trigger type + config forms, timeline icon, shadow badge).
`analysis-engine` unaffected.

### Two derivations of "a transition happened"

This design deliberately has two, and they are not the same mechanism:

| | Trigger (M1/M2) | Timeline (M4) |
|---|---|---|
| Source | in-memory old-vs-new during the daily loop | comparing consecutive `customer_usage_history` snapshots |
| Timing | same run as the classification | read time |
| Scope | worsening transitions only | all state changes |

They can disagree, because the snapshot write (`usage_metrics.py:625`) happens in a **separate,
later transaction** than the trend commit (`:611`), and is caught-and-logged on failure without
rolling back the trend update (`:627-633`). So a snapshot-write failure yields a fired trigger
with no corresponding timeline event.

**Decision: accept this, don't paper over it.** Making them share one source would mean either
writing the timeline event transactionally from the worker (a new table — rejected in favor of
the snapshot approach) or deriving the trigger from snapshots (delaying the action by a day).
The divergence is rare, bounded, and fails in the safe direction: the action still happens, and
only its history entry is missing. It must be documented, not hidden.

### Multi-tenancy

`row.organization_id` is available per iteration (`usage_metrics.py:583-584,609`) with no extra
query. Rules are org-scoped by the evaluator's query; timeline reads are already org-scoped and
cross-org isolation is covered by existing tests.

### Data model

Additive only — two nullable columns on `customer_usage_history`. No new table, no data
migration, no backfill. Existing rows get `NULL` trend state, which the timeline derivation must
treat as "unknown" and skip rather than as a transition.

### Performance

The timeline derivation reads up to 180 snapshot rows per customer per profile view — bounded
and comparable to the existing per-customer fetches. The trigger evaluator adds one rule query
per org that has `usage_trend` rules, plus one Redis check per (rule, customer) transition —
only for customers who actually transitioned, which is a small fraction of the daily scan.

---

## Risks & Open Questions

- **R1 — Trigger/timeline divergence.** Described above. Accepted, documented; safe-direction
  failure.
- **R2 — The daily cadence caps latency at ~24h.** The trigger rides the 04:00 UTC recompute
  (`celery_app.py:225-228`). A decline detected at 04:00 acts at 04:00; there is no real-time
  path. This is inherent to a 14-day-window trend and should be stated honestly rather than
  implied to be real-time.
- **R3 — The warm-up means near-zero firing for ~2 weeks.** Snapshots began 2026-07-22. M2's
  baseline-seed rule makes this quiet rather than noisy, and M7's shadow default makes it
  observable. Still, an operator arming this in week 1 sees nothing happen, and the docs (S1)
  must say so.
- **R4 — Light users are permanently ineligible, not just during warm-up.**
  `classify_usage_trend` requires the baseline to clear `TREND_MIN_BASELINE_ACTIVE_DAYS = 5`
  (`usage_score_service.py:288-331`). A customer whose 14-day baseline is under 5 active days
  **never** receives a trend state, so a decline trigger structurally cannot fire for the
  lightest-usage segment — arguably a segment operators care about. This is inherited from
  M3.2b, not introduced here, and is not in scope to change; it must be documented (S1) so
  nobody concludes the trigger is broken.
- **R5 — Mirror drift.** This adds a third copy of the mode/cooldown/execution-logging shape
  (backend engine, churn mirror, usage-trend mirror), and `usage_score_service.py` is already
  duplicated between backend and worker with a "keep in sync" comment. Accepted to stay
  consistent with M4.1.5's deliberate architecture; a shared-core refactor is a separate branch.
- **R6 — Frontend duplication tax.** The trigger config form must be written twice
  (create + edit pages) and the label mock updated in up to five test files. Mechanical, but a
  known source of "works on create, broken on edit" bugs — the plan must test both pages.
- **Q1 (open)** — Should `sharp_decline → declining` (partial recovery) emit a timeline event
  but remain non-firing? Current answer: yes, timeline records it, trigger ignores it. Cheap to
  revisit if it reads oddly in practice.

---

## Out of Scope

- **D2 / D3** — `usage_event` retention, the O(lifetime) per-event re-read, and the swallowed
  Celery enqueue (`docs/planning/usage-trend-churn-signal/prd.md:254-262`). Their own branch,
  per that PRD.
- **Anything touching churn probability or calibration** (M9).
- **Retroactive backfill** of trend state onto existing snapshot rows.
- **Recovery-triggered automations** (V1), magnitude conditions (V2), per-org thresholds (V3).
- **Real-time firing** on usage-event ingest — the trend is a 14-day-window signal; per-event
  evaluation would be meaningless and expensive.
- **Any plan-tier gating.** Rereflect is MIT/self-hosted with all features unlocked;
  `CLAUDE.md`'s billing sections are stale pre-pivot.
- **Refactoring the worker mirrors into a shared core** (R5).
