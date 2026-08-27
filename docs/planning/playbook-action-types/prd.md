# PRD — Complete the seeded playbook action types

**Slug:** `playbook-action-types` · **Branch:** `feat/playbook-action-types`
**Type:** feat (freeform) · **Author:** rereflect-begin-fast pipeline · **Date:** 2026-08-26
**Status:** Draft (pending review gate)

---

## Problem Statement

The churn-playbook engine implements 5 of the 11 action types the seeder declares valid,
so **6 of the 7 seeded playbook templates contain steps that fail on every execution**
with `"unsupported action type: '<type>'"`, and runs still complete `done` — the failures
are buried in an `action_log` the frontend never renders.

- `services/worker-service/src/services/playbook_engine.py:171-186` — `_dispatch_action`
  supports only `assign, change_status, send_notification, draft_response, send_email`.
- `services/backend-api/src/services/playbook_seeder.py:24-36` — `VALID_ACTION_TYPES`
  additionally declares `notify, tag, schedule_task, create_task, trigger_automation`.
- Seeded templates using the unimplemented types (`playbook_seeder.py`): **Critical Save**
  `notify` (:57), **Churn Prevention** `schedule_task` (:96), **At-Risk Outreach** `tag`
  (:115), **Light-Touch Nudge** `tag` + `create_task` (:138, :142), **Power-User Recovery**
  `notify` + `create_task` (:161, :173), **New-Customer Save** `trigger_automation` (:192),
  **Silent-Churn Watch** `create_task` (:219).

This is the same inert-template defect class as the P0 `automation-worker-triggers-dead`
fix (`DEV-TRACKING.md:47`) — the automations delivery-integrity project made the *triggers*
fire, but the playbook *actions* those auto-runs execute are still half-built. The repo
already names this as the next card: `docs/planning/customer-outreach-email-actions/prd.md:247-255`
— "Fixing the other 5 unimplemented seeded playbook action types (`notify`, `tag`,
`schedule_task`, `create_task`, `trigger_automation`) — separate card; noted."

**Who has the problem:** the self-hosting operator / CS manager running churn playbooks —
especially auto-executed ones (`churn_probability_threshold` → `run_playbook`), where the
template's Slack alert, tag, or follow-up task silently never happens.

**Evidence it's real:** the seeder ships these templates as ready-to-use
(`is_template=True`, `is_active=True`); worker tests pin the failure loudly
(`tests/test_playbook_engine.py:574-600` — "loud entry" while the run completes `done`);
the frontend execution list has no action-log column (`PlaybookExecutionsList.tsx:39-47`)
so the failures are invisible to operators.

## Goals & Success Metrics

- **G1 — All 7 seeded templates fully execute.** No seeded template step hits
  `"unsupported action type"`; each new action performs its documented side effect.
- **G2 — Honest, loud failure.** Every unimplemented/unconfigured path returns
  `ok: False` with a specific reason, and per-action results are visible in the UI
  (executions no longer "complete done" with invisible failures).
- **G3 — No automation loops.** `trigger_automation` is recursion-safe via the shared
  Redis cooldown scheme; a rule → playbook → rule cycle terminates.
- **G4 — Zero regressions** to the 5 shipped action handlers and the worker automation
  mirrors. **Hard gate:** the existing suites
  `tests/test_automation_churn_trigger.py`, `tests/test_automation_usage_trend_trigger.py`,
  and `tests/test_usage_trend_churn_boundary.py` pass **unmodified** after the single-rule
  evaluation seam extraction (R2).

**Measurable acceptance (capability-verified + regression-free — self-hosted, no runtime
telemetry):** iterate all 7 seeded templates through `playbook_engine.execute` and assert
zero `unsupported action type` entries; each handler's side effect asserted by TDD tests
(tag written, task row created, Slack/Discord/notification dispatch called, rule fired or
cooldown-skipped); backend `pytest tests/ -v`, worker `pytest tests/ -v`, frontend
`npm run lint` + `npm run test` all green.

**Documentation is a deliverable:** `docs/SELF_HOSTING.md` if new env/config surface
appears, CHANGELOG, `AI-TRACKING.md` / `DEV-TRACKING.md` rows, and the deferral at
`customer-outreach-email-actions/prd.md:247` marked closed.

## User Personas & Scenarios

- **CS manager (operator):** a `churn_probability_threshold` rule auto-runs **Critical
  Save** on a 92%-probability customer. Today: `notify` fails silently in the log. After:
  the Slack alert lands in the org's configured channel, admins get an in-app
  notification, and the execution log shows each action's result.
- **CS lead:** manually runs **Light-Touch Nudge** on a cohort. Today: `tag` + `create_task`
  fail. After: the customer gets the `monitor` tag and a follow-up task is persisted with
  a due date, visible in the run's action results.
- **Support lead building a custom playbook:** the editor now offers all 5 new action
  types with config forms (channel/message, tag name, task fields, automation picker).
- **Operator with no Slack/Discord connected:** a `notify` step reports
  `ok: False, reason: no slack integration connected` loudly; the run's other actions
  still execute.

## Requirements

### Must-have

- **M1 — `tag` action.** Config `{tag: string}`. Adds the tag to
  `customer_health_scores.tags` (JSON array, sorted), honoring the bulk-tag constraints
  (≤50 chars, ≤20 tags/customer; over-cap → `ok: False` with reason, customer unchanged —
  mirroring `customers.py:689-729` semantics). Result: `{tags: [...]}`.
- **M2 — `notify` action.** Config `{channel: "slack"|"discord"|"dashboard",
  target?: string, message: string}`. Slack/Discord → send the message via the org's
  connected integration (worker `tasks/alerts` senders, never raising — failure mapped to
  `ok: False`); `target` is advisory in v1 (the integration's configured channel is used)
  and is recorded in the result. Dashboard → `Notification` rows for admins. Unknown
  channel → loud error. No integration connected → `ok: False`, specific reason.
- **M3 — `create_task` and `schedule_task` actions → internal task table.** New
  `playbook_tasks` table (backend model + worker mirror + one Alembic migration).
  Config: `{description, due_in_days?, priority?}` (schedule_task: no priority).
  `due_at = now + due_in_days` calendar days. Result: `{task_id, description, due_at}`.
- **M4 — `trigger_automation` action.** Config `{automation_name: string}`. Resolves an
  `AutomationRule` by name within the org (first match by `created_at, id` — the model has
  no unique constraint; the chosen rule id is reported in the result) and **fires only
  trigger type `churn_probability_threshold`** — the one customer-level type evaluable from
  the playbook context (the customer's `churn_probability` on the `CustomerHealth` row).
  **`usage_trend` rules are not evaluable from a playbook** (the trigger is a transition
  observed at the daily recompute seam; a playbook cannot reconstruct old→new) → loud error
  `trigger type 'usage_trend' fires only from the daily recompute seam`. Any other trigger
  type → loud error. Firing **reuses the existing single-rule entry**
  `_evaluate_rule(rule, org_id, customer_email, probability, db)` in
  `automation_churn_trigger.py:164` — which already checks the rule's own Redis cooldown
  key (`automation_cooldown:{rule_id}:{customer_email}`, DB 1) and sets it before
  committing, so a rule → playbook → rule cycle terminates across the async boundary.
  **Recursion guard (belt):** rules with `cooldown_hours < 1` are refused
  (`setex` TTL 0 would never hold). Lookup outcomes are all loud with distinct reasons:
  unknown name → `no rule named 'X'`; rule found but `mode != "active"` →
  `rule 'X' found but mode=off/shadow — not fired`; no probability on the customer →
  `no churn probability available for customer`. `_evaluate_rule` commits mid-run — the
  playbook execution finalizes correctly after it (characterization-tested).
- **M5 — Seeder fixes + upgrade path.** Seeder's **New-Customer Save** `trigger_automation`
  config points at `"onboarding_playbook"`, which no seeder creates — retarget it to a real
  seeded automation (`At-Risk Customer Outreach`, which ships in shadow mode; per M4 the
  step will report `mode=off/shadow — not fired` until the operator activates it — loud,
  by design). The seeder must **update existing template rows** when a seed's
  `action_sequence` changes (today it skips existing rows by name) so existing installs
  converge. **Update predicate — pristine seeded rows only:** `organization_id IS NULL AND
  is_template = true AND name == seed name` and the stored `action_sequence` differs from
  the seed; any row with `source_template_id` set (operator-cloned) or any org-owned row
  is never touched. Idempotent: after the first convergent run, no further updates.
- **M6 — Frontend editor coverage.** `ACTION_TYPE_LABELS` + `PlaybookAction.type`
  (`lib/api/playbooks.ts:11-20,171-177`) gain the 5 types; `PlaybookEditor.tsx` gains
  config forms: `notify` (channel select + message; target optional), `tag` (tag input),
  `create_task` / `schedule_task` (description, due_in_days, priority), `trigger_automation`
  (automation picker from the existing automations list API).
- **M7 — Execution surfacing.** `PlaybookExecutionsList.tsx` rows gain an expandable
  per-action view rendering `action_log` entries with ok/error badges (automations-log
  precedent `automations/[id]/page.tsx:1060-1119`). Execution status semantics unchanged
  in v1 (`done` = at least one action ok) — the per-action view is the loud surface.

### Should-have

- **S1 — `schedule_task` / `create_task` visible in the customer profile.** A minimal
  "Playbook tasks" card (open tasks for the customer) on `/customers/[email]`, backed by a
  small read endpoint. *(Droppable if the execution-log surface suffices.)*

### Nice-to-have

- **N2 — `trigger_automation` for other trigger types** (`usage_trend` from a playbook,
  and the per-feedback types `sentiment_pattern`, `feedback_category_match`) — needs
  context the engine lacks (transitions, feedback items); v2.
- **N3 — A "partial failure" execution status** distinct from `done`/`failed` — status
  semantics change with UI ripple; revisit if operators ask.
- **N4 — Provider task creation** (Jira / Asana / Linear) as the eventual target of
  `create_task` — explicitly out of scope here (see Out of Scope).

## Technical Considerations

- **Services touched:** `services/worker-service` (engine handlers — the only executor),
  `services/backend-api` (model mirror + migration + seeder), `services/frontend-web`
  (editor + executions list). Analysis-engine untouched. No new backend routes required
  for must-haves (S1 would add one read endpoint).
- **Worker cannot import backend-api code** — the engine, the new handlers, and the
  single-rule automation evaluation seam all live in `worker-service/src`, mirroring the
  established pattern (e.g. `outreach_templates_mirror`, `automation_*_trigger.py`).
- **Data model:** `PlaybookTask` — `id, organization_id, customer_email, description,
  due_at (nullable), priority (low|medium|high, default medium), status (open|done|
  cancelled, default open), playbook_execution_id, created_at`. Backend model in
  `src/models/`, worker mirror in worker `src/models/__init__.py`, one Alembic migration
  (alembic heads must stay single — CI asserts).
- **Cooldown contract:** `automation_cooldown:{rule_id}:{customer_email}` Redis DB 1,
  TTL `cooldown_hours * 3600` — identical to the backend engine and both worker mirrors
  (`automation_engine.py:384-401`); the key scheme must not drift.
- **Mirror behavior preservation:** extracting the single-rule evaluation seam from
  `automation_churn_trigger.py` / `automation_usage_trend_trigger.py` must leave their
  per-recompute behavior byte-identical (characterization tests).
- **Multi-tenancy:** every new write is org-scoped via the execution's `organization_id`;
  no cross-org paths.
- **Notification senders raise** (`tasks/alerts.py`) — the `notify` handler wraps them
  into the `{ok, result, error}` contract like `_handle_send_email` does for
  `send_outreach_email`.

## Risks & Open Questions

- **R1 — `trigger_automation` name ambiguity.** `AutomationRule.name` is not unique; two
  rules named the same resolve to the first match. Mitigation: deterministic order
  (created_at), documented in the action result.
- **R2 — Single-rule evaluation.** The seam already exists: `_evaluate_rule` in
  `automation_churn_trigger.py:164` is a faithful per-rule entry (threshold, cooldown
  check+set, shadow/active, execution row, commit). The real risk is its **mid-run
  `db.commit()`** inside the playbook execution's session (the run row commits as
  `running` before finalizing as `done`). Characterization-tested, not refactored.
- **R3 — Slack channel resolution for `notify`.** OAuth sends need a `channel_id`; the
  seeder's `target` ("#cs-leads") is a name. v1 sends to the integration's configured
  channel and records `target` as advisory — stated in the result, documented in the UI
  form helper text.
- **R4 — Seeder convergence.** Existing installs already have the 7 templates seeded with
  today's configs; the update-existing path must be idempotent and must not overwrite
  operator-cloned or edited copies (`is_template=False` rows are never touched).
- **R5 — New table on both processes.** The worker must not write columns the backend
  model lacks (mirror drift) — the existing mirror-discipline tests cover this pattern.
- **OQ1 — Should `create_task` also support an explicit due datetime?** Seeder uses
  `due_in_days` only; v1 supports `due_in_days` (+ optional `due_at` ISO), over-constrained
  otherwise.
- **OQ2 — `notify` dashboard recipient semantics — SETTLED (v1):** reuse the worker
  `dispatch_alert` path for the dashboard channel, which honors `UserAlertPreference`
  per-user filtering; the handler reports `{notifications_created: N}`. Not open at plan
  time.

## Out of Scope

- **Provider task creation** (Jira/Asana/Linear) — the worker has no create-capable
  clients and backend routes are feedback-linked/admin-only/dup-guarded, not
  worker-importable; building them is a vendor-client project (N1).
- **`trigger_automation` for per-feedback trigger types** (`sentiment_pattern`,
  `feedback_category_match`, `health_score`, `churn_risk_level`) — needs feedback-item
  context the engine doesn't have (N2).
- **Changes to the 5 shipped handlers** (assign/change_status/send_notification/
  draft_response/send_email) — unless a bug in their interplay with the new types forces
  it, characterization-locked.
- **Playbook execution status semantics** (`done` = any-ok stays; no new statuses in v1).
- **Automations-side action taxonomy** (`automations.py:62-69` list) — untouched.
- **No new plan gates, no billing surface** — OSS self-hosted, all unlocked.

## Decision Records

- **D1 — `create_task`/`schedule_task` target = internal `playbook_tasks` table** (user
  decision, 2026-08-26). Self-host native, offline, worker-native. Provider dispatch v2.
- **D2 — `trigger_automation` = name lookup, customer-level trigger types only, shared
  cooldown as recursion guard** (user decision). Seeder config retargeted to a real
  automation.
- **D3 — UI scope = editor options + execution action-log surfacing** (user decision).
- **D4 — `notify` = external channels** (Slack/Discord per org integration + dashboard
  notifications), matching the seeder's channel/target/message intent (user decision).

## Aspect Decomposition (proposed)

1. **`tag-notify-actions`** — M1 + M2: `tag` and `notify` handlers in the worker engine
   with TDD tests. No schema change. First slice, fully internal.
2. **`playbook-tasks`** — M3: `PlaybookTask` model (backend + worker mirror) + Alembic
   migration + `create_task`/`schedule_task` handlers. (S1/N1 depend on this.)
3. **`trigger-automation`** — M4: name lookup + `_evaluate_rule` reuse (existing seam) +
   mode/cooldown guards, characterization-tested against the churn mirror's suites.
4. **`seeder-and-ui`** — M5 + M6 + M7: seeder update path + New-Customer Save retarget,
   frontend editor types/config forms, executions action-log surfacing. Depends on 1–3.