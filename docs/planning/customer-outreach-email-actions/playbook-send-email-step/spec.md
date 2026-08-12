# Spec — playbook-send-email-step

**Feature:** `customer-outreach-email-actions`
**PRD:** `../prd.md` (approved 2026-08-12)
**Foundation:** `../outreach-core/spec.md` + `../outreach-core/plan_20260812.md` (contracts fixed
and authoritative — consumed, never reimplemented)
**Aspect boundary:** make the seeded playbooks' `send_email` steps actually work. Everything is
worker-service: the `_dispatch_action` branch, the `_handle_send_email` handler, two worker-model
mirror columns, tests, and a CHANGELOG line. **Zero backend-api changes, zero migrations.**

## Problem slice

The playbook seeder ships two templates with `send_email` steps — "At-Risk Outreach"
(`services/backend-api/src/services/playbook_seeder.py:109-113`, step 1:
`{type: "send_email", config: {template: "weekly_digest_entry", recipient: "cs_assignee"}}`) and
"Silent-Churn Watch" (`playbook_seeder.py:213-217`, step 1:
`{type: "send_email", config: {template: "re_engagement", recipient: "customer"}}`) — but the
playbook engine rejects every such step with
`{"ok": False, "result": None, "error": "unsupported action type: 'send_email'"}`
(`services/worker-service/src/services/playbook_engine.py:177-182`). Every qualifying run of
either playbook fails that step today while the UI presents it as an active step — the same
delivery-integrity trap class as the automations P0 (`docs/planning/automations-delivery-integrity/`,
`CLAUDE.md` automations section). PRD must-have #1 fixes exactly this.

## Consumed contracts (outreach-core, FIXED — do not redesign)

1. **Worker sender** — `services/worker-service/src/services/outreach_sender.py`
   `send_outreach_email(db, org_id, customer_email, subject, body, *, product_name,
   template_key=None) -> dict` returning `{ok, status, reason}`, `status ∈
   {sent, skipped, failed}` (`outreach-core/spec.md:28-35`). It owns opt-out check
   (`skipped: opted out`), cooldown check (`skipped: in cooldown`, Redis DB 1,
   `outreach_cooldown:{org_id}:{customer_email}`, TTL `OUTREACH_COOLDOWN_HOURS`), loud no-key
   failure (`failed: email not configured`), the `List-Unsubscribe` header, and the cooldown
   **set** on success (`outreach-core/spec.md:31-40`, AC3-AC6 at `spec.md:70-76`). It never
   raises (`outreach-core/plan_20260812.md:208`). **The engine calls it; it does not touch
   Redis or Resend itself.**
2. **Template registry mirror (worker)** — `services/worker-service/src/services/outreach_templates_mirror.py`,
   registry data duplicated verbatim from backend, keys `re_engagement` and `weekly_digest_entry`
   (`outreach-core/plan_20260812.md:90-91`; keys must match the seeder's `template:` values
   verbatim — `playbook_seeder.py:112,216`), with a pure
   `render_outreach_template(key, customer_name, product_name)` that substitutes
   `{{CUSTOMER_NAME}}` / `{{PRODUCT_NAME}}` (`outreach-core/spec.md:22-27`).
3. **Worker `email.py` `_send_email`** already extended with `extra_headers`/`text`
   (`outreach-core/spec.md:36-37`) — the engine never calls it directly.

## Verified facts (checked in this worktree; the implementing agent should re-verify at the line)

- **Engine dispatch structure** — `_dispatch_action` at `playbook_engine.py:152-182`: an
  `if/elif` chain over `assign`, `change_status`, `send_notification`, `draft_response`
  (169-176), else the unsupported-action dict (177-182). Handlers all share the signature
  `(config, customer_email, health, db) -> {"ok": bool, "result": ..., "error": ...}` and are
  defined after the dispatch (185-376).
- **Handler lazy-import style** — handlers import models inside the function
  (`playbook_engine.py:197`, `260`, `287`, `338`). The new handler imports worker-local
  outreach modules lazily the same way. **No bare `except` around any import** — that is a
  defect on sight (`CLAUDE.md`; `tests/test_worker_import_sweep.py:16-22`, banned paths at
  `test_worker_import_sweep.py:39-45` — worker may not import `src.api` or backend modules).
- **action_log contract** — `_run_actions` at `playbook_engine.py:121-149` wraps each dispatch
  in try/except (136-148) and records `{"type", "ok", "result", "error"}` per step (137-142);
  a raised handler records `{"ok": False, "result": None, "error": str(exc)}` (148). The log is
  persisted via `_finalize_execution` (`playbook_engine.py:379-395`, `execution.action_log =
  action_log` at 391) onto `ChurnPlaybookExecution.action_log` (JSON,
  `services/worker-service/src/models/__init__.py:943`).
- **Run status derivation** — `any_ok = any(entry.get("ok") ...)` → `done` if any step ok,
  else `failed` (`playbook_engine.py:90-94`). **Do not change it.** The send_email step
  contributes `ok=True` only when the sender reports `status == "sent"` (see mapping below).
- **Health row already loaded** — `execute` loads `CustomerHealth` by
  `(organization_id, customer_email)` and passes it into `_run_actions`/`_dispatch_action`
  (`playbook_engine.py:74-88`). `health.organization_id` (models/__init__.py:424),
  `health.customer_name` (models/__init__.py:426).
- **Worker `CustomerHealth` mirror LACKS `cs_owner_user_id`** — the worker model
  (`models/__init__.py:419-479`) has no such column; backend has it
  (`services/backend-api/src/models/customer_health.py:72` FK, `:88` relationship). The DB
  column already exists (migration `a6b703d7a303`, added on master) — the worker mirror just
  needs the plain nullable `Integer` column, no FK, no migration (mirror precedent:
  `calibration_model_id`, `models/__init__.py:467`).
- **Worker `Organization` mirror LACKS `product_name_display`** — (`models/__init__.py:34-51`).
  Backend has it (`services/backend-api/src/models/organization.py:32`; migration `o4p5q6r7s8t9`)
  with fallback `org.product_name_display or "Rereflect"` (`issue_drafter.py:57`,
  `response_sender.py:174`). Same mirror fix, no migration.
- **Owner-email resolution precedent** — backend: `db.query(User.id, User.email).filter(User.id
  == record.cs_owner_user_id).first()` (`services/backend-api/src/api/routes/customers.py:811-812`).
  Worker `User` has `id`, `email`, `organization_id` (`models/__init__.py:16-31`).
- **Seeder config is the contract** — `{type: "send_email", config: {template, recipient}}`,
  `recipient ∈ {"customer", "cs_assignee"}` (`playbook_seeder.py:109-113, 213-217`). Do not
  change it.
- **Sender is worker-local** — outreach-core's sender is in `worker-service/src/services/`, so
  the engine can import it (the worker image ships `worker-service/src`; backend-api is not
  importable — `CLAUDE.md` automations section).
- **Test infrastructure** — `tests/test_playbook_engine.py` has in-memory SQLite wiring
  (`test_playbook_engine.py:30-48`), builders `_make_org/_make_playbook/_make_execution/_make_health`
  (55-119), and monkeypatches `playbook_engine._dispatch_action` for isolation (213-233).
  Celery-task-level tests live in `tests/test_run_playbook_task.py` (`_patch_db_session`,
  111-120). Redis mocking precedent: `@patch("..._get_redis", return_value=fake_redis)` with
  `fake_redis = MagicMock()` (`tests/test_automation_feedback_trigger.py:316-335`) — not needed
  here because the sender is mocked whole.

## In-scope requirements

1. **Dispatch branch** — add `send_email` to the `_dispatch_action` chain
   (`playbook_engine.py:169-176`) routing to a new `_handle_send_email(config, customer_email,
   health, db)`; update the dispatch docstring (162-168).
2. **`_handle_send_email`** (new, placed after `_handle_draft_response`, ~line 376):
   a. **Validate config** — `template` and `recipient` keys present; `recipient ∈
      {"customer", "cs_assignee"}`; else loud per-step failure (ok=False, error set).
   b. **Resolve recipient email** —
      - `customer` → the `customer_email` argument (the execution's,
        `playbook_engine.py:88`).
      - `cs_assignee` → `health.cs_owner_user_id` (mirror column from req 4); `None` ⇒ loud
        failure; else `db.query(User.email).filter(User.id == cs_owner_user_id).first()`
        (backend precedent `customers.py:811-812`); user row missing ⇒ loud failure.
   c. **Render** — `render_outreach_template(template, customer_name, product_name)` from the
      worker registry mirror, where `customer_name = health.customer_name or
      customer_email.split("@")[0]` and `product_name = (org.product_name_display if org and
      org.product_name_display else "Rereflect")` with `org = db.query(Organization).filter_by(
      id=health.organization_id).first()`. Unknown/missing template key ⇒ loud per-step failure
      (catch the renderer's missing-key signal; error must contain the key).
   d. **Send** — call `send_outreach_email(db, health.organization_id, to_email, subject,
      body, product_name=product_name, template_key=template)`. No opt-out/cooldown/Resend
      logic here — the sender owns it.
   e. **Map result** — engine outcome per the table below. Only `sent` is `ok=True`.
3. **Result/action_log mapping (keeps `playbook_engine.py:90-94` untouched):**

   | sender returns | engine entry `ok` | engine entry `result` | engine entry `error` |
   |---|---|---|---|
   | `{ok: True, status: "sent", ...}` | `True` | `{"status": "sent", "reason": ..., "to": to_email, "template": template}` | `None` |
   | `{ok: False, status: "skipped", reason: "opted out"}` | `False` | `{"status": "skipped", "reason": "opted out", "to": ..., "template": ...}` | `None` |
   | `{ok: False, status: "skipped", reason: "in cooldown"}` | `False` | `{"status": "skipped", "reason": "in cooldown", "to": ..., "template": ...}` | `None` |
   | `{ok: False, status: "failed", reason: "email not configured"}` | `False` | `{"status": "failed", "reason": "email not configured", "to": ..., "template": ...}` | `None` |
   | pre-send validation/resolution failure | `False` | `None` | descriptive error string |

   The skip is **loud in the action_log** (status + reason visible), and the run-status
   derivation is unchanged: a skipped/failed email leaves the run `failed` only if no other
   step succeeded (both seeded playbooks have later steps, so they still finish `done` with a
   loudly-failed email step — the PRD's "never false success" property).
4. **Worker model mirrors** — `CustomerHealth.cs_owner_user_id` (nullable Integer) and
   `Organization.product_name_display` (nullable String(200)) added to
   `services/worker-service/src/models/__init__.py`, matching backend column types
   (`customer_health.py:72`, `organization.py:32`). No migration — both DB columns already
   exist on master; worker models are read-only mirrors (no FK constraints).
5. **Tests** — extend `tests/test_playbook_engine.py`: recipient resolution (both values,
   missing owner, missing owner-user), template rendering via the real mirror (placeholders
   substituted; unknown key → loud failure), sender mocking for sent/skipped-opted-out/
   skipped-cooldown/failed-no-key, action_log entry shape, run-status consistency (send_email
   alone skipped ⇒ run `failed`; send_email sent ⇒ `done`; seeded-playbook shape ⇒ `done` with
   loud email entry).
6. **Seeded templates pinned green** — a test running both seed action_sequences through the
   real engine (sender mocked to `sent`) asserting: both `send_email` steps dispatch with the
   seeded `template`/`recipient` config, log `ok=True`, and the run is `done`. This is PRD
   goal #1's honest pin.
7. **CHANGELOG** — one Unreleased line (feature already ships the seeds; this makes them work).

## Out-of-scope boundaries

- No backend-api changes, no migrations, no Alembic work (`alembic heads` must stay at exactly
  one head — CI asserts).
- No Redis/cooldown/opt-out/List-Unsubscribe code in the engine — `send_outreach_email` owns
  those (outreach-core AC3-AC6).
- No changes to `playbook_seeder.py` (seed config is the contract), `automation_engine.py`
  (backend), the worker automation mirrors, or the `automation_cooldown` key scheme.
- No other seeded action types (`notify`, `tag`, `create_task`, `schedule_task`,
  `trigger_automation`) — separate card (PRD Out of Scope).
- No single-customer run-path work (PRD should-have #8 — inherits these semantics; test-only
  item, not this aspect).

## Acceptance criteria (testable)

- AC1: `_dispatch_action("send_email", {"template": "re_engagement", "recipient": "customer"},
  ...)` returns a dict with `ok=True` when the mocked sender returns `sent`; the handler
  receives the execution's customer_email as the recipient.
- AC2: `recipient: "cs_assignee"` resolves via `health.cs_owner_user_id → users.email`; with no
  owner assigned the step returns `ok=False` with an error mentioning the missing owner (never
  silent).
- AC3: `customer_name` null ⇒ falls back to the email local-part; `product_name_display` unset ⇒
  "Rereflect".
- AC4: unknown `template` key in config ⇒ `ok=False` step, error containing the key.
- AC5: unknown/missing `recipient` or missing `template` in config ⇒ `ok=False` step.
- AC6: mocked sender returning `skipped: opted out` / `skipped: in cooldown` / `failed: email
  not configured` produces the exact entries in the mapping table (loud in action_log, `ok=False`).
- AC7: run status: send_email-only playbook with a skipped/failed email ⇒ execution `failed`;
  with a sent email ⇒ `done`; "Silent-Churn Watch" seed (send_email + create_task, sender
  mocked) ⇒ `done` with the send_email entry loud.
- AC8: both seed action_sequences (`playbook_seeder.py:109-126`, `:213-226`) run through the
  real engine with the sender mocked to `sent` — each `send_email` step logs `ok=True`.
- AC9: `test_worker_import_sweep.py` still passes (no backend-api import introduced); worker
  full suite green.
- AC10: no migration touched — `alembic heads` prints exactly one head (unchanged).

## Dependencies & sequencing

Depends on **outreach-core being merged first** (sender, registry mirror, `email.py`
extension, worker `CustomerHealth.outreach_opt_out` mirror). Prerequisite check for the
implementing agent: `services/worker-service/src/services/outreach_sender.py` and
`services/worker-service/src/services/outreach_templates_mirror.py` must exist — if not, STOP
and flag (outreach-core not landed). Bulk-campaign aspect can proceed in parallel; nothing here
is consumed by it.

## Open questions / risks

- **`skipped` → `ok=False` semantics** — a deliberate read of "never false success"
  (PRD goal #4). The run stays `done` in practice because both seeds carry a later ok step;
  the email step's skip is loud in the action_log. Flag to reviewers: a playbook whose ONLY
  action is `send_email` will show `failed` when the customer opted out. Accepted for v1.
- **`send_outreach_email` signature drift** — the engine depends on outreach-core's exact
  signature (`outreach-core/spec.md:29-30`). Checkpoint after Phase 2; if the sender's
  signature changed, fix the call site and flag (outreach-core is authoritative).
- **`product_name` sourcing** — engine uses `Organization.product_name_display` (mirror
  column) with the backend's "Rereflect" fallback (`issue_drafter.py:57`). The registry mirror
  contract renders with product_name passed in — this is the only sensible source in the worker.
