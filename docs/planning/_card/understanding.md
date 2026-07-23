# Understanding — usage-trend-automation-trigger (Phase 2 dig)

**Date:** 2026-07-23
**Method:** 4 parallel read-only agents over the trend compute path, the automation engine,
the customer timeline, and the automations UI. Paths are relative to the worktree
`.claude/worktrees/feat-usage-trend-automation-trigger/`. Every claim below is cited.

---

## What the task is really asking

Reconnect the M3.2b usage-decline signal to the action loop, via two deferred items:

- **N1** — a `usage_trend_change` customer-timeline event.
- **N2** — a `usage_trend` automation trigger that composes with `run_playbook` (M4.1.5).

Both are additive. Neither may touch `churn_risk_component`, `churn_probability`, or the
isotonic calibration.

---

## Affected services

| Service | What changes |
|---|---|
| `worker-service` | The firing seam in `recompute_usage_scores`; a new isolated trigger evaluator (mirror pattern) |
| `backend-api` | Trigger registration (whitelist + Pydantic config + engine checker), timeline assembly, likely a model/migration |
| `frontend-web` | Trigger-type union + label + two duplicated config forms; timeline icon; (candidate) shadow-badge fix |
| `analysis-engine` | Unaffected |

---

## Key findings that shape the design

### F1 — Transition detection is nearly free, but the old value is thrown away

`recompute_usage_scores` (`services/worker-service/src/tasks/usage_metrics.py:543-609`) already
computes the transition boolean **before** overwriting:

```python
trend_state_changed = new_trend_state != row.usage_trend_state   # :589  (old value still live)
if trend_state_changed or new_trend_pct != row.usage_trend_pct:
    row.usage_trend_state = new_trend_state                       # :591  (old value now gone)
```

The old state is in memory at line 589 but never captured into a variable, and **is not
persisted anywhere** — there is no `previous_trend_state` column, no trend history table, and
`customer_usage_history` has **no trend columns**
(`services/backend-api/src/models/customer_usage_history.py:48-55`). Capturing
`old_trend_state` into a local at the seam is a one-line change.

### F2 — The loop is all-orgs and commits once, in bulk

Line 532 loads `db.query(CustomerUsage).all()` with **no org filter**; all mutations commit
once after the loop (`usage_metrics.py:611-612`). `row.organization_id` is available per
iteration (used at :583-584, :609), so org scope is free — but a hook fired *inside* the loop
would act on uncommitted state. Transitions must be **collected during the loop and drained
after the commit**. The existing `_call_update_health` hook (`usage_metrics.py:604-609`) is
called inside the loop and is the local precedent — but it is a health recompute, not an
action-executing trigger, so its placement is not automatically the right precedent for us.

### F3 — The worker cannot import the backend's AutomationEngine

M4.1.5 hit this exact wall and solved it with a deliberate, narrow mirror:
`services/worker-service/src/services/automation_churn_trigger.py` implements **only** the
`churn_probability_threshold` trigger + `run_playbook` action, with its own lightweight
`AutomationRule` mirror model (no FKs, since the worker doesn't own migrations), sharing
**Redis db=1** and the identical key scheme `automation_cooldown:{rule_id}:{customer_email}`
so cooldowns are honored across both processes (`automation_churn_trigger.py:22-26,49,88,101`).
Our trigger fires from a worker task, so it inherits this constraint and should follow the
same mirror pattern rather than growing the mirror into a general engine — the module docstring
at `automation_churn_trigger.py:16-21` explicitly warns against that.

### F4 — Registering a new trigger type is a known, enumerated checklist

Backend (`services/backend-api/`):
1. `src/api/routes/automations.py:49-55` — `VALID_TRIGGER_TYPES` frozenset
2. `src/api/routes/automations.py:74-127,180-201` — a new `*Config` Pydantic class + a branch in `TriggerSchema.validate_trigger`
3. `src/services/automation_engine.py:208-225` — a `_trigger_*` checker + dispatch branch
4. `src/services/automation_engine.py:76-81` — context-shape docstring parity

Frontend (`services/frontend-web/`):
5. `lib/api/automations.ts:5-10` — `TriggerType` union
6. `lib/api/automations.ts:134-140` — `TRIGGER_TYPE_LABELS`
7. `app/(dashboard)/settings/automations/new/page.tsx:98-194` + `:343-350` — config form + defaults
8. `app/(dashboard)/settings/automations/[id]/page.tsx:78-236` + `:611-619` — the **duplicated** config form + defaults (with `disabled={!isAdminOrOwner}` wiring)
9. Every test file that mocks `TRIGGER_TYPE_LABELS` — the mock is hand-duplicated per file, so a new option is invisible in mocked renders until each is updated

The list page needs no change — `TriggerBadge` is label-driven and generic.

### F5 — Cooldown seeding on activation is route-driven and currently churn-only

`seed_churn_cooldowns(db, rule)` (`automation_engine.py:697-747`) is called from three route
sites in `automations.py` (`create_rule` :571-586, `update_rule` :640-654, `toggle_rule`
:695-708), each guarded on an `old_mode != active → active` transition and each wrapped in
try/except so seeding failure never fails the request. It hard-returns 0 for any trigger type
other than `churn_probability_threshold` (`automation_engine.py:716`).

**The stampede rationale applies to us only conditionally.** Its docstring (`:701-711`) explains
the churn trigger is *level-based* — it re-fires as long as probability stays ≥ threshold.
Whether our trigger is level-based or edge-based is the central design question (Q2): an
**edge-triggered** (fire-on-transition) design is inherently stampede-resistant, because an
already-`declining` customer produces no transition on the next pass. If we go edge-triggered,
seeding may be unnecessary — a simplification, not a gap.

### F6 — The timeline has no events table; N1 has no natural backing row

`services/backend-api/src/services/customer_timeline_service.py` assembles all 13 event types
**at read time** by unioning existing source tables (`build_timeline`, :637-730). Every
existing event type is derived from a durable row that already exists for another reason
(`FeedbackItem`, `CustomerHealthHistory`, `ChurnPlaybookExecution`, `CrmEnrichment`, …).

A trend *change* has no such row: `customer_usage` holds only the current state (F1), and
`customer_usage_history` snapshots carry no trend columns. So **N1 requires new persistence** —
a real design decision, not an implementation detail. See Q1.

### F7 — Shadow mode is misrendered as a failure in the UI

`AutomationExecution.status` is typed `'success' | 'partial_failure' | 'failed'`
(`lib/api/automations.ts:50`) — it is **missing `'shadow'`**, which the backend does write
(`automation_engine.py:85-86,163-165`). `StatusBadge`
(`app/(dashboard)/settings/automations/[id]/page.tsx:59-67`) branches only on
`success`/`partial_failure` and falls through to `destructive` / "failed".

Net effect, verified in code: a shadow evaluation renders with an **empty "Actions Taken"
column and a red "failed" badge** — indistinguishable from a genuine failure.
`trigger_snapshot` is never displayed anywhere in the frontend.

This collides directly with making shadow the sensible default for a trigger that cannot fire
for ~2 more weeks: the one screen that would show it working currently reports it as broken.
Carried as a **candidate must-have**, flagged rather than silently fixed. It is a pre-existing
M4.1.5 defect, not one this feature introduces.

### F8 — The churn fence is already enforced by a load-bearing test

`services/backend-api/tests/test_usage_trend_churn_boundary.py` drives a real
`stable → sharp_decline` transition through two `update_customer_health()` calls and asserts
`churn_risk_component`, `churn_probability`, `churn_probability_low/high`,
`calibration_model_id`, `time_to_churn_bucket` are byte-unchanged — with a paired non-vacuity
test proving `usage_component`/`health_score` *do* move. Keeping this green is the scope fence.

### F9 — Cold start is structural, and there is no "improving" state

`classify_usage_trend` (`usage_score_service.py:288-331`) returns `insufficient_history` unless
an in-band (12–16 day) snapshot exists **and** the baseline clears
`TREND_MIN_BASELINE_ACTIVE_DAYS = 5`. Snapshots began 2026-07-22.

Note the floor guard is **permanent, not merely a warm-up effect**: a low-activity customer
whose 14-day baseline is under 5 active days is never eligible for a trend state at all, so a
decline-triggered playbook structurally cannot fire for light users. That is a real coverage
limit worth stating honestly in the PRD.

There are only four states, and increases classify as `stable`
(`usage_score_service.py:307,326-329`) — so "recovery" can only mean `declining → stable`, and
there is no way to trigger on growth.

---

## Contradictions / corrections to the brief

1. **"fire it from the daily `recompute_usage_scores` seam"** — correct, but the brief implies
   an in-loop hook like `_call_update_health`. F2 shows the bulk commit makes in-loop action
   execution wrong; transitions must be drained post-commit.
2. **"same cooldown-seeding-on-activation so an already-declining cohort doesn't stampede"** —
   may be unnecessary rather than required. Seeding exists because the churn trigger is
   level-based (F5); an edge-triggered usage trend has no such failure mode. Decide
   deliberately instead of copying.
3. **N1 is not "just a timeline event."** F6 shows it needs new persistence, so it is not the
   cheap half of this feature — it may be the larger half.

---

## Open questions for the interview

- **Q1 (N1 storage):** the timeline is read-time-assembled and a trend change has no backing
  row. Add trend columns to the existing `customer_usage_history` snapshot and derive
  transitions by comparing consecutive snapshots at read time (no new table, forward-only), or
  write a dedicated trend-change row from the daily task?
- **Q2 (trigger semantics):** edge-triggered (fire on entering a worse state) or level-based
  (fire while state is bad, cooldown-gated)? Does `usage_trend_pct` enter the condition, or is
  it state-only? Is `declining → stable` recovery fireable?
- **Q3 (default mode):** should a `usage_trend` rule default to `shadow` given the ~2-week
  warm-up, diverging from the current `active` default for all rules (`new/page.tsx:319`)?
- **Q4 (scope):** fix the shadow "failed" badge (F7) on this branch, or leave it and file it?
- **Q5 (N1 breadth):** does the timeline event fire on every state change including recovery
  and the first exit from `insufficient_history`, or on declines only?
