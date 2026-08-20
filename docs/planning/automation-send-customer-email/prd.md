# PRD — Automations `send_customer_email` action

**Slug:** `automation-send-customer-email` · **Branch:** `feat/automation-send-customer-email`
**Type:** feat (freeform) · **Author:** rereflect-begin-fast pipeline · **Date:** 2026-08-19
**Status:** Draft (pending review gate)

---

## Problem Statement

Automation rules — the heart of the churn → health → playbook → automations loop
(`AI-TRACKING.md:5`) — can only act *inside* the app. The four action types
(`auto_assign`, `change_status`, `send_notification`, `draft_response`;
`AI-TRACKING.md:415`) plus `run_playbook` never reach the customer: `draft_response`
writes a canned-tone draft to the clipboard channel (`automation_engine.py:683-725`),
and `send_notification` with channel `email` alerts **org users**, not the customer.
The killer use case — "a rule fires when churn risk crosses a threshold, and the
at-risk customer gets a message" — dead-ends.

This is a **named deferral**, not invented. `docs/planning/customer-outreach-email-actions/prd.md:239-241`
explicitly scoped out: *"Automations-engine `send_customer_email` action type — deferred
v2 (the two worker churn/usage mirrors silently skip unknown actions; adding it there is
its own delivery-integrity project)."* The unblocking half (per-customer opt-out,
tokenized unsubscribe, shared Redis cooldown, worker email helper, template registry,
AI draft) shipped 2026-08-12 with the outreach feature. The remaining gap is the action
type across the four automation evaluators.

**Who has the problem:** the self-hosting operator / CS manager who wants "when X
happens, email the customer" without manually running a playbook or a bulk campaign.

**Evidence it's real:** the deferral line above; the seeded playbook send_email steps
("At-Risk Outreach", "Silent-Churn Watch" — `playbook_seeder.py:109-113,213-217`) prove
the demand but are manual/playbook-initiated only; the `usage_decline_outreach` and
`churn_prevention` automation templates stop at `send_notification` (org users), never
the customer.

## Goals & Success Metrics

- **G1 — Complete the action loop.** An automation rule on *any* trigger can email the
  customer (or their CS owner), reusing the shipped outreach protections verbatim.
- **G2 — Uniform semantics across every evaluator.** The same action behaves identically
  whether evaluated by the backend engine (health triggers) or the three worker mirrors
  (feedback / churn / usage). No "works on one mirror, inert on another" — the exact
  delivery-integrity bug class `docs/planning/automations-delivery-integrity/` exists to
  prevent.
- **G3 — Honest delivery, honest failure.** Every send is auditable (delivery row:
  `queued → sent|skipped|failed` + reason). No-key and opt-out are loud, never silent
  success.
- **G4 — Zero regressions** to shipped automation/outreach/playbook behavior
  (characterization-gated).

**Measurable acceptance (capability-verified + regression-free — this is a self-hosted
product with no runtime telemetry):** the action works end-to-end on all four evaluators
with TDD tests; opt-out / cooldown / no-key / unsubscribe honored on every path; delivery
table accurate; frontend editor round-trips create → edit → save with the exact config
keys the backend reads; backend `pytest tests/ -v`, worker `pytest tests/ -v`, frontend
`npm run lint` + `npm run test` all green.

**Documentation is a deliverable:** `docs/SELF_HOSTING.md` + `docs/API.md` (+ OpenAPI
docstrings), CHANGELOG, `AI-TRACKING.md` / `DEV-TRACKING.md` rows updated, and the
deferral at `customer-outreach-email-actions/prd.md:239` marked closed.

## User Personas & Scenarios

- **CS manager (operator):** creates a rule "when a customer's churn probability crosses
  0.6, email them the `re_engagement` template" — the rule runs in **shadow** first
  (evaluates + logs, sends nothing), then flips to active. The at-risk customer receives
  the outreach email; an opted-out customer is silently skipped (never emailed), and the
  execution log says so.
- **Support lead:** a `feedback_category_match` rule on critical-bug feedback emails the
  customer's **CS owner** (recipient `cs_assignee`) so the right person reaches out.
- **Operator without Resend configured:** enables a template using the action; every
  execution records `skipped: email not configured` loudly (never a false success), and
  the docs explain why.

## Requirements

### Must-have

- **M1 — `send_customer_email` action type** in the automations taxonomy (backend
  `VALID_ACTION_TYPES`, `automation_engine._execute_actions`, worker mirrors). Config:
  `{template: str, recipient: "customer" | "cs_assignee"}`.
  - `template` validated against the outreach template registry keys
    (`re_engagement`, `weekly_digest_entry` — `services/outreach_templates.py:29`).
  - `recipient` defaults to `"customer"`.
  - Config model `SendCustomerEmailConfig` with `extra="forbid"` (unknown keys → 422),
    unlike the lax existing config models.
- **M2 — Uniform dispatch on all four evaluators:**
  - Backend engine (`automation_engine.py:407-438`): `_execute_send_customer_email`
    validates config, resolves recipient email + subject/body, checks
    `email_service._is_email_enabled()` at enqueue time (loud skip when unset), creates a
    delivery row (`queued`), enqueues `tasks.outreach.send_automation_email` via
    `send_task`. Returns `{status: "queued", delivery_id}`.
  - Worker feedback mirror (`automation_feedback_trigger._execute_actions`, 477-517):
    same, via `send_automation_email.delay(delivery_id)`.
  - Worker churn mirror (`automation_churn_trigger.py:210-282`) and usage mirror
    (`automation_usage_trend_trigger.py:260-331`): **extend** the action loop to handle
    `send_customer_email` in addition to `run_playbook`. Other unknown action types keep
    their current silent-skip contract (pinned by
    `test_non_run_playbook_actions_are_ignored`).
  - One worker task, one sender: `outreach_sender.send_outreach_email` is the **only**
    place that sends (opt-out + cooldown + no-key + `List-Unsubscribe` live there —
    `worker-service/src/services/outreach_sender.py:139`). Backend never copies it.
- **M3 — Delivery audit table** `automation_email_deliveries`:
  - Columns (Integer PK — the codebase convention; the PRD's earlier "BigInt" guess was
    wrong): `id`, `organization_id`, `rule_id`, `customer_email`, `to_email`,
    `template_key`, `subject`, `body`, `status` (`queued|sent|skipped|failed`),
    `reason` (nullable), timestamps. (No `automation_execution_id`: the execution log is
    written *after* actions run on every evaluator, so it can never be known at row
    creation — the deliveries endpoint is scoped by `rule_id` instead.)
  - Written `queued` by the evaluator; the worker task loads the row, calls
    `outreach_sender`, maps `sent|skipped|failed` + reason, terminal-guard (already
    terminal → no-op). One Alembic migration, chained to the live single head.
- **M4 — Honest failure + no-key semantics:**
  - `RESEND_API_KEY` unset at enqueue → delivery row `skipped: email not configured`,
    action result error → execution `partial_failure`/`failed`. Never silent success.
  - Opt-out at send time (toggled between enqueue and send) → `outreach_sender` skips →
    row `skipped: opted out`. Honest.
  - Batch-sentiment org-wide trigger (`batch_sentiment_threshold`) has **no customer
  recipient** (org-wide cooldown sentinel `__org__`, `automation_feedback_trigger.py:221`):
  the action skips loudly, keyed on the **trigger type** (the evaluation context always
  carries the pivot feedback's email, so a missing-email check would misfire) —
  `skipped: no customer email (org-wide trigger)`, never sends.
  - Archived customers must not be emailed: the evaluator skips when the
    `CustomerHealth.is_archived` flag is set (`customer_health.py:41`) — mirroring the
    bulk path's archived skip (`customers.py:838-853`). `outreach_sender` does **not**
    check archived (verified), so this lives in the evaluator, not the sender.
  - The task must **never leave a row `queued`**: any exception or unknown outcome is
    caught and mapped to `failed` (mirroring the outreach task's try/except →
    recipient-failed pattern, `tasks/outreach.py:29-64`). A stuck `queued` row would
    mean "promised, unknown"; re-firing the rule creates a fresh row (idempotency note:
    each firing is its own delivery, keyed by execution, not deduped against a previous
    firing).
- **M5 — Frontend editor:** `send_customer_email` in `ACTION_TYPES` (new + [id] pages)
  with an inline editor — template select (`listOutreachTemplates()` +
  `BUILTIN_OUTREACH_TEMPLATES` fallback) + recipient select (`customer` / `cs_assignee`),
  mirroring `PlaybookEditor`'s send_email step config + `SendEmailConfig` type shape.
  `ActionType`, `ACTION_TYPE_LABELS` (automations.ts), `ACTION_ICONS` (list page,
  e.g. `Mail`), and execution-log badges all gain the new type.
- **M6 — Docs + tracking:** `SELF_HOSTING.md` (action type, no-key behavior, opt-out /
  cooldown semantics), `docs/API.md` (action type + deliveries endpoint), CHANGELOG,
  `AI-TRACKING.md` row, `DEV-TRACKING.md` rows, and the deferral at
  `customer-outreach-email-actions/prd.md:239` marked closed.

### Should-have

- **S1 — Seeded template using the action.** "At-Risk Customer Outreach":
  `churn_probability_threshold` (`{threshold: 0.6, direction: above}`) →
  `send_customer_email` (`re_engagement`, recipient `customer`), seeded
  `mode: "shadow"` (the usage-trend precedent) for discoverability and safety. New entry
  in `config/automation_templates.py` (template seeding is already idempotent at
  startup).
- **S2 — Deliveries read surface.** `GET /api/v1/automations/{rule_id}/deliveries`
  (admin/owner), recent rows with status badges; a minimal "Email deliveries" section on
  the rule detail page.

### Nice-to-have

- **N1 — Cooldown column on the rules list** (dig noted the list page has no cooldown
  column) — only if the editor surfaces cooldown for email actions.
- **N2 — CS-owner name in the recipient picker** (resolve owner display name at render).

## Technical Considerations

### Services touched

- **backend-api:** `src/services/automation_engine.py` (new handler + dispatch entry),
  `src/api/routes/automations.py` (`VALID_ACTION_TYPES`, `SendCustomerEmailConfig`,
  deliveries endpoint), `src/models/` (delivery model), `src/api/main.py` (router wiring
  for deliveries if new router), Alembic migration.
- **worker-service:** `src/services/automation_feedback_trigger.py` (new handler),
  `src/services/automation_churn_trigger.py` + `automation_usage_trend_trigger.py`
  (extend action loop), `src/tasks/outreach.py` (new `send_automation_email` task),
  `celery_app.py` includes it.
- **frontend-web:** `lib/api/automations.ts` (type + labels + deliveries client),
  `lib/api/outreach.ts` (template list already exists), both automation editor pages,
  list-page icon map, rule detail page (deliveries section).

### Key design decisions (locked by interview)

1. **Direct send, mode-gated.** Rules already carry `off/shadow/active`; shadow evaluates
   + logs but never executes actions (`automation_engine.py:171-173`). No new gating
   machinery. Templates seeding the action default to `shadow`.
2. **Recipients `customer` + `cs_assignee`**, mirroring the playbook send_email step's
   `{template, recipient}` shape exactly.
3. **Delivery audit table** (M3) — honest queued → outcome trail.
4. **Enqueue-to-worker everywhere** — one sender in the worker, one task
   (`tasks.outreach.send_automation_email(delivery_id)`), uniform `{status: "queued"}`
   action results across all four evaluators. The task-name string is pinned by tests
   (the `run_playbook` / outreach-task precedent — `customers.py:862-864`,
   `tasks/outreach.py:9-13`).

### Cross-process contracts (do not drift)

- Outreach cooldown: `outreach_cooldown:{org_id}:{email}` — **Redis DB 1**, set only on
  success, TTL `OUTREACH_COOLDOWN_HOURS` (default 24). Both the bulk campaign and any
  automation send share it — an automation send and a bulk campaign within the window
  block each other (intended: no double-emailing). Automation rule cooldown
  (`automation_cooldown:{rule_id}:{customer_email}`, DB 1) applies before actions run,
  unchanged.
- Opt-out: `CustomerHealth.outreach_opt_out` (`server_default="false"`). Missing health
  row for a `customer` recipient = not opted out (send). `cs_assignee` requires a health
  row (owner resolution fails loudly without one).
- `RESEND_API_KEY` is read at import time in both processes; the enqueue-time check uses
  each process's own `_is_email_enabled()`.
- Template registry: backend `outreach_templates.py` ↔ worker
  `outreach_templates_mirror.py` already pinned in agreement — used for key validation
  (backend) and subject/body rendering (evaluator side), never re-duplicated.

### Multi-tenancy

All data org-scoped (`organization_id` on the delivery row and every query). Rules,
deliveries, and templates are per-org. No cross-tenant data anywhere.

## Risks & Open Questions

- **R1 — Archived-customer skip**: field confirmed `CustomerHealth.is_archived`
  (`customer_health.py:41`); the evaluator skips archived customers before enqueue
  (M4). Resolved by code read.
- **R2 — Missing-`CustomerHealth` semantics**: confirmed by code — `outreach_sender`
  treats a missing health row as not-opted-out (`outreach_sender.py:167`:
  `if health is not None and health.outreach_opt_out`), so a `customer` recipient with
  no health row sends; `cs_assignee` requires a health row (owner resolution fails
  loudly). Resolved by code read.
- **R3 — Churn/usage mirrors keep silent-skipping other unknown types** (pinned by
  `test_non_run_playbook_actions_are_ignored`). `send_customer_email` is added; making
  all unknown types loud in those two mirrors is a **separate** delivery-integrity
  hardening, out of scope here.
- **R4 — `send_email` naming**: the playbook taxonomy reserves `send_email`; the
  automations taxonomy uses `send_customer_email`. Two separate label maps in two
  modules — both must be updated, and tests must not mix them.
- **R5 — Execution-log audit depth**: the delivery row carries the final outcome, but the
  execution-log entry records the action result at evaluation time (`queued`). The
  deliveries surface (S2) is how an operator sees the outcome; keep that coupling
  documented.
- **R6 — No draft-review surface**: blessed by interview (direct send, mode-gated). A
  customer-facing auto-send is a behavior change; the shadow-default templates and the
  opt-out/cooldown protections are the honest mitigation.
- **R7 — Cooldown burn-on-success only**: a failed send is immediately retryable and
  does not cool down (outreach_sender behavior). Accept as-is (matches bulk path).
- **R8 — Stuck-`queued` deliveries**: if the worker is down or the send task crashes,
  a row could sit `queued` forever with no operator signal. Mitigation (M4): the task
  wraps the send so no exception escapes with the row still `queued`; a re-fire of the
  rule creates a new row (no dedup against prior firings). A stuck-`queued` row after
  the fix means the worker was down — visible via the deliveries surface (S2) and
  worker logs. No background sweep in this slice.

## Out of Scope

- **SMTP transport** (Resend BYO-key only; SMTP is v2).
- **Fixing the other 5 unimplemented seeded playbook action types** (`notify`, `tag`,
  `create_task`, `schedule_task`, `trigger_automation`) — separate card.
- **Making unknown action types loud in the churn/usage mirrors** (R3) — separate
  delivery-integrity hardening.
- **Fixing the `send_notification` email channel's silent-success flaw** (`automation_engine.py:589-604`)
  — pre-existing, tracked separately.
- **Draft-review queue / human-confirmation surface** (rejected in interview).
- **Segment-aware drafting, open/click tracking, suppression-list UI, campaign
  sequences** — outreach v2.
- **Churn/health computation, churn probability, calibration, M5.3** — untouched.
- **Plan gates** — none (OSS, all unlocked).

## Proposed Aspects (for tech-plan)

1. `action-core` — backend action type + config schema + deliveries model/migration +
   enqueue; backend engine handler.
2. `worker-mirrors` — feedback mirror handler + churn/usage mirror extension + the
   `send_automation_email` task + delivery row updates; cross-mirror seam tests.
3. `frontend-editor` — ACTION_TYPES, editor branch (template + recipient pickers),
   labels/icons, deliveries section.
4. `docs-and-templates` — SELF_HOSTING + API docs, seeded shadow template, CHANGELOG,
   tracking rows, deferral closure.

---

## Self-critique (prd-generator pass)

**Scores:** Problem Definition 🟢 · User Understanding 🟢 · Success Metrics 🟢 ·
Scope Clarity 🟢 · Edge Cases & Risks 🟢 · Stakeholder Alignment 🟢 · Feasibility 🟢 ·
Go-to-Market 🟢.

**Gaps closed during this pass:**
- R1 (archived skip) + R2 (missing health row) downgraded from "verify in plan" to
  **resolved by code read** — `CustomerHealth.is_archived` (`customer_health.py:41`) and
  `outreach_sender.py:167` confirmed.
- New R8 (stuck-`queued` deliveries) added with the task-never-leaves-queued mitigation.

**Areas to strengthen before sharing:**
- **Rollout/observability beyond docs:** a self-hoster only discovers the action via
  docs + the seeded template. S1 is the in-product discoverability; keep it in scope.
- **The action's result vs delivery outcome coupling** (R5) needs a one-line note in the
  frontend execution log ("delivered" link → deliveries section) so operators connect
  `queued` to the final state.

**Hard question (the one to answer before greenlighting):** *When the worker is down and
a rule fires, the delivery row stays `queued` — a customer has effectively been promised
a message that may never send. Is accepting a `queued`-until-recovery (no sweep, no
retry) the right honesty bar for this slice, or should a stuck `queued` delivery be
retryable by the operator (bulk campaigns already have a retry)?* — Answer: **accepted
for this slice.** `queued` is the honest "work accepted, outcome unknown" state, the task
guarantees it never gets stuck via an exception, and a re-fire re-attempts. A retry
affordance for `queued` rows is N3 (nice-to-have), not a blocker.