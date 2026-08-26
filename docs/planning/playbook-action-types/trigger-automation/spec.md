# Aspect — `trigger-automation`

**Slice:** M4 — the `trigger_automation` playbook action, scoped (PRD amendment, 2026-08-27)
to **churn_probability_threshold rules only**; `usage_trend` is transition-based and not
reconstructable from the playbook context.

**PRD requirements:** M4 (as amended), R1, R2, G3.

---

## Problem slice & outcome

A seeded step `{"type": "trigger_automation", "config": {"automation_name": "..."}}` fires a
named `churn_probability_threshold` automation rule for the customer — respecting the rule's
own mode, cooldown, and threshold — instead of failing with `unsupported action type`.
Firing reuses the **existing** single-rule entry `_evaluate_rule` in
`automation_churn_trigger.py:164`, so no mirror refactor is needed and the recursion guard
is the rule's own shared Redis cooldown key.

## In scope

1. **`_handle_trigger_automation(config, customer_email, health, db)`** in
   `worker-service/src/services/playbook_engine.py`:
   - config `{automation_name: str (required, non-empty)}`
   - lookup: `AutomationRule` where `organization_id == health.organization_id` and
     `name == automation_name`, ordered `created_at, id` (no unique constraint — first
     match wins, chosen id reported)
   - outcomes, all loud with distinct reasons:
     - none found → `ok: False`, `no rule named '<name>'`
     - `mode != "active"` → `ok: False`, `rule '<name>' found but mode=off/shadow — not fired`
     - `trigger_type != "churn_probability_threshold"` → `ok: False`,
       `trigger type '<type>' fires only from <seam>` (`usage_trend` → "the daily recompute
       seam"; others → "its native evaluator")
     - `cooldown_hours < 1` → `ok: False`, `rule '<name>' has cooldown_hours < 1 — refused`
       (setex TTL 0 would never hold — the recursion belt)
     - `health.churn_probability is None` → `ok: False`,
       `no churn probability available for customer`
   - fire: call `_evaluate_rule(rule, org_id, customer_email, float(health.churn_probability), db)`
     (it checks the rule's threshold + Redis cooldown, sets the cooldown before commit,
     writes the `AutomationExecution`, and enqueues the playbook via `.delay` — async, so
     no in-process recursion); return `{"ok": True, "result": {"fired": True, "rule_id":
     rule.id, "automation_name": ...}}`
2. **`_dispatch_action` branch** for `trigger_automation`.
3. **Characterization gate:** `tests/test_automation_churn_trigger.py` and
   `tests/test_usage_trend_churn_boundary.py` pass **unmodified** (G4).
4. **Mid-run commit interaction:** `_evaluate_rule` calls `db.commit()` inside the
   playbook execution's session — the run must still finalize correctly (`done` +
   `action_log`); pinned by a test.

## Out of scope

- `usage_trend` and per-feedback trigger types from a playbook (PRD N2 — v2).
- Any change to `automation_churn_trigger.py` or the usage-trend mirror.
- Firing shadow/off rules (mode guard is strict `active`).
- Cooldown-key scheme changes (must not drift: `automation_cooldown:{rule_id}:{customer_email}`, DB 1).

## Acceptance criteria

- **AC1** — an active `churn_probability_threshold` rule whose threshold the customer's
  probability breaches → `_evaluate_rule` called, `ok: True, fired: True`, `AutomationExecution`
  row written, cooldown set.
- **AC2** — probability below the rule threshold → `ok: True` but `fired: False` with the
  rule's own reason (`_evaluate_rule` returns without firing; the action executed
  correctly).
- **AC3** — rule already in cooldown for the customer → `ok: True, fired: False,
  reason: cooldown`.
- **AC4** — unknown name / mode off / mode shadow / cooldown_hours < 1 / missing
  probability / non-churn trigger type → each `ok: False` with the exact reason strings
  above (one test per branch).
- **AC5** — rule with `trigger_type == "usage_trend"` → `ok: False` with the seam reason.
- **AC6** — a run containing `trigger_automation` (which commits mid-run) finalizes
  `done` with the full `action_log` intact.
- **AC7** — cross-org: a rule from another org is never resolved (name lookup is
  org-scoped).
- **AC8** — `tests/test_automation_churn_trigger.py` + `tests/test_usage_trend_churn_boundary.py`
  + the full playbook-engine suite pass **unmodified**.

## Dependencies & sequencing

Depends on nothing from the other aspects. Runs in parallel with `playbook-tasks`.

Test precedent: `tests/test_automation_churn_trigger.py` (patched `_get_redis` /
`.delay` — no broker or live Redis needed).

## Risks / open questions

- `_evaluate_rule` commits the session mid-run (R2) — pinned by AC6 rather than refactored.
- Name lookup ordering `created_at, id` is a documented tie-break (R1); the result reports
  the chosen `rule_id` so ambiguity is visible.
- The seeded `At-Risk Customer Outreach` rule ships in **shadow** — until an operator
  flips it active, the retargeted New-Customer Save step reports the loud
  `mode=off/shadow — not fired` (by design, PRD M5).