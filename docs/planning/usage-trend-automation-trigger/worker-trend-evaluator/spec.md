# Aspect — `worker-trend-evaluator`

**Slice:** N2's engine — capture transitions at the daily seam and fire `usage_trend` rules
after the commit.

**PRD requirement:** M1, M5.

---

## Problem slice & outcome

A customer entering `declining`/`sharp_decline` during the nightly recompute causes matching
active rules to run their playbook, and matching shadow rules to log a would-have-run.

## In scope

1. **Seam capture** in `services/worker-service/src/tasks/usage_metrics.py`:
   - capture `old_trend_state` into a local **before** the overwrite at `:591` (the value is
     already live at `:589`)
   - accumulate `(organization_id, customer_email, old_state, new_state)` for rows whose state
     changed
   - **drain after `db.commit()`** (`:611-612`) — never inside the loop
2. **New module** `services/worker-service/src/services/automation_usage_trend_trigger.py`,
   modeled on `automation_churn_trigger.py`:
   - query the worker's lightweight `AutomationRule` mirror for
     `trigger_type == "usage_trend"`, `mode.in_(["shadow","active"])` (`off` excluded in SQL)
   - severity check mirroring `trigger-registration`'s helper
   - per-(rule, customer) Redis cooldown — **Redis db=1**, key
     `automation_cooldown:{rule_id}:{customer_email}` (`automation_churn_trigger.py:49,88,101`)
   - `mode == "shadow"` → log an `AutomationExecution(status="shadow")`, execute nothing, still
     consume the cooldown
   - `mode == "active"` → execute **`run_playbook` only**, creating
     `ChurnPlaybookExecution(triggered_by=...)` and dispatching the existing task
   - per-rule exception isolation — a failure must never break the daily recompute

## `triggered_by` value

`ChurnPlaybookExecution.triggered_by` currently uses `"auto_probability"` for M4.1.5. This
aspect needs a distinct value (e.g. `"auto_usage_trend"`).

**Check before choosing:** `_fetch_playbook_runs`
(`services/backend-api/src/services/customer_timeline_service.py:455-459`) filters
`triggered_by == "auto_probability"` to build `playbook_auto_run` timeline events. A new value
will **not** appear on the timeline unless that filter is widened. Decide deliberately: either
widen the filter so usage-trend auto-runs also surface as `playbook_auto_run`, or accept that
they don't. Widening is strongly preferred — an auto-run invisible on the timeline is exactly
the "action with no visible cause" problem this feature exists to fix.

## Out of scope

- Trigger registration/validation (`trigger-registration`).
- Any action type other than `run_playbook` — matching M4.1.5's deliberately narrow mirror.
  Do **not** grow this into a general engine (`automation_churn_trigger.py:16-21` warns against
  exactly that).
- `seed_churn_cooldowns` — unnecessary under edge-triggering (PRD M2).
- Real-time firing on usage-event ingest.

## Acceptance criteria

- **AC1** — A `stable → declining` transition in the daily run creates a
  `ChurnPlaybookExecution` and dispatches the playbook task (PRD E1).
- **AC2** — `insufficient_history → sharp_decline` creates **zero** executions (PRD E3).
- **AC3** — A customer staying `declining` across two consecutive runs fires **once**, on the
  first — proving edge semantics without relying on the cooldown.
- **AC4** — Firing happens **after** commit: a test asserting the trend value is committed and
  visible before any execution row is created (guards the F2 ordering defect).
- **AC5** — `mode="shadow"` writes an `AutomationExecution(status="shadow")` with no
  `ChurnPlaybookExecution` and no task dispatch.
- **AC6** — `mode="off"` rules are never selected.
- **AC7** — A cooldown set by the backend engine suppresses this evaluator, and vice versa
  (shared key scheme).
- **AC8** — A raising rule is isolated: the other rules still evaluate and the task still
  completes.
- **AC9** — Cross-org: a rule only ever fires for customers in its own organization.
- **AC10** — `tests/test_usage_trend_churn_boundary.py` unchanged and green.

## Dependencies & sequencing

**Depends on `trigger-registration`** (config shape + severity helper). Independent of the
snapshot/timeline aspects — they can proceed in parallel.

Test precedent: `services/worker-service/tests/test_automation_churn_trigger.py` — in-memory
SQLite + `StaticPool`, patched `run_playbook.delay`, patched `_get_redis`, so neither a broker
nor a live Redis is needed.

## Risks / open questions

- Third copy of the mode/cooldown/logging shape (PRD R5). Accepted for consistency with M4.1.5.
- The daily cadence caps action latency at ~24h (PRD R2) — inherent, not fixable here.
