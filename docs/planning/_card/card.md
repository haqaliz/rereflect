# Card — feat/automation-send-customer-email (freeform, no GitHub issue)

Source: `rereflect-next` recommendation (2026-08-19 session). Branch
`feat/automation-send-customer-email`, worktree
`.claude/worktrees/feat-automation-send-customer-email`.

## Task

Add a `send_customer_email` **action type** to the automations engine so an
automation **rule** (e.g. `churn_probability_threshold`, `usage_trend`,
`sentiment_pattern`, `feedback_category_match`) can email the customer directly —
reusing the shipped customer-outreach plumbing (opt-out, tokenized unsubscribe,
shared Redis cooldown, worker email helper, template registry, AI draft).

## Traces (the candidate is a named deferral, not invented)

- `docs/planning/customer-outreach-email-actions/prd.md:239-241` — Out of Scope:
  *"Automations-engine `send_customer_email` action type — deferred v2 (the two
  worker churn/usage mirrors silently skip unknown actions; adding it there is its
  own delivery-integrity project). Playbook steps + bulk campaign only in v1."*
- `docs/planning/_card/understanding.md` (2026-08-12 dig) — the open-questions
  list that is the ready-made PRD skeleton:
  - OQ1 (`:77-81`): action-type naming — seeder reserves `send_email` with
    `{template, recipient}` config; engines would need a `send_customer_email`-style
    type. Align with seeded `send_email` taxonomy or rename the seeds.
  - OQ2 (`:83-84`): **auto-send vs draft** — product norm is human-confirmed
    (draft_response, response suggestions, churn-label review queue). An automation
    `send_customer_email` firing automatically is a behaviour change the PRD must
    bless, or the action must produce a draft in a review surface.
  - OQ3 (`:85-86`): email channel — Resend BYO-key first slice; SMTP explicitly v2.
  - OQ4 (`:87-90`): customer opt-out — NO unsubscribe/suppression state for
    `customer_email` existed at dig time. **Resolved by the shipped outreach
    feature** (per-customer opt-out flag + tokenized `List-Unsubscribe`, honored on
    every send path).
  - OQ5 (`:91-94`): which triggers get the action — feedback mirror only, or also
    churn/usage mirrors (which silently skip non-`run_playbook` actions today)?
  - OQ6 (`:95-96`): loudness — email failures currently log-only (never
    `channel_errors`); customer-facing send must be honest (loud result,
    `partial_failure` semantics).
  - OQ7 (`:97-98`): no-key behaviour — `RESEND_API_KEY` unset ⇒ skip with warning;
    the action result must say "skipped: no email key" loudly, not silently succeed.
  - OQ8 (`:99-101`): bulk endpoint shape — already shipped with outreach; not
    relevant here.
- `docs/planning/automations-delivery-integrity/prd.md` — the worker-mirror
  duplication discipline: worker-service cannot import backend-api; a bare
  `try/except` around a worker import = defect on sight. Cooldowns shared across
  processes via Redis DB 1, key `automation_cooldown:{rule_id}:{customer_email}`,
  TTL `cooldown_hours * 3600`.

## What shipped before this (the unblocking half)

`customer-outreach-email-actions` (2026-08-12, merged PR #13) delivered:
- Playbook `send_email` step (`playbook_engine._handle_send_email`,
  `services/worker-service/src/services/playbook_engine.py:179-180,391+`) with
  `{template, recipient}` config, recipient ∈ `cs_assignee | customer`.
- Bulk campaign API `POST /customers/bulk/outreach` + `?count_only` preview,
  campaign + per-recipient audit rows, per-recipient Celery send task, campaign
  list + `queued` retry endpoint, AI-draft endpoint that never sends.
- Per-customer opt-out + tokenized `List-Unsubscribe` honored on every send path;
  shared per-recipient cooldown (Redis DB 1, `outreach_cooldown` key) — both send
  paths must write the same key.
- Built-in template registry; worker email-helper parity (`src/email.py`).
- `docs/planning/customer-outreach-email-actions/` full PRD + aspect specs.

See `DEV-TRACKING.md:1369` (decisions row) and the PRD for details.

## The gap this feature closes

Automations rules today stop at internal actions (`auto_assign`, `change_status`,
`send_notification`, `draft_response` — `AI-TRACKING.md:415`). `draft_response`
drafts but never reaches the customer. The outreach feature covers playbook steps +
bulk campaigns only. A rule like "churn probability crossed threshold" cannot yet
email the at-risk customer automatically; the churn → health → playbook →
automations loop dead-ends inside the app.

## Known caveats (carried into the PRD — the dig must confirm)

1. **Two worker mirrors silently `continue` past unknown action types** —
   `automation_churn_trigger.py` + `automation_usage_trend_trigger.py` are
   run_playbook-only (`_card/understanding.md:56-59`). A `send_customer_email`
   action added only to the backend engine + feedback mirror would be inert on the
   churn/usage paths. PRD must decide: add to those mirrors too, or document +
   test that they skip loudly. The `run_playbook` action pattern is the precedent
   for reaching those mirrors.
2. **Auto-send vs draft-review (OQ2)** — product norm is human-confirmed. If
   auto-send: require the opt-out check to fail the action, keep the shared
   cooldown, honor unsubscribe. If draft: needs a review surface (new UI) — bigger.
3. **No-key behaviour (OQ7)** — loud skip ("skipped: no email key"), never silent
   success; `RESEND_API_KEY` unset is the default state of a $0 local install.
4. **Delivery-integrity discipline** — worker mirrors must be byte-consistent;
   cooldown key scheme must not drift; cross-process contract pinned by tests.
5. **Loudness (OQ6)** — failures must produce `partial_failure`/error on the
   execution log, never a false `success` (the `_execute_notify` class of bug).

## Out of scope (guardrails)

- SMTP transport (v2 — Resend BYO-key only in this slice).
- Fixing the other 5 unimplemented seeded playbook action types (`notify`, `tag`,
  `create_task`, `schedule_task`, `trigger_automation`) — separate card; noted.
- Churn/health computation, churn probability, calibration, M5.3 — untouched.
- Plan gates — none (OSS, all unlocked).
- No telemetry / no cross-tenant data.

## Deliverables (proposed, refine in PRD)

1. `send_customer_email` action type in backend `automation_engine` (config
   validation + execution via the shared outreach send path / worker dispatch).
2. Worker feedback-mirror (`automation_feedback_trigger.py`) + decision on
   churn/usage mirrors, pinned by cross-mirror tests.
3. Frontend automation action editor branch (template picker, recipient = customer,
   opt-out/cooldown copy).
4. Docs: `docs/API.md`, `docs/SELF_HOSTING.md`, CHANGELOG; `AI-TRACKING.md` /
   `DEV-TRACKING.md` rows updated; the deferral at
   `customer-outreach-email-actions/prd.md:239` marked closed.
