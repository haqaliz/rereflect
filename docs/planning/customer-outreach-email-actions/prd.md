# PRD — Customer Outreach Email Actions

**Slug:** `customer-outreach-email-actions`
**Branch:** `feat/customer-outreach-email-actions`
**Status:** Draft for review
**Date:** 2026-08-12
**Traces to:** `segment-actions/prd.md:170` (deferred "Trigger outreach campaign"),
`churn-triggered-playbooks/prd.md:247-249` (deferred email/outreach actions),
`playbook_seeder.py:109-113, 213-217` (shipped-but-broken `send_email` steps),
`AI-TRACKING.md:5` (killer feature: churn prediction with actionable reasons).

---

## Problem Statement

The flagship loop — churn prediction with **actionable** reasons — dead-ends inside the
app. Churn-triggered playbooks auto-run (M4.1.5), but every playbook/automation action is
internal-only: assign, change status, notify the team, draft a response. The customer is
never reachable.

Worse, the shipped product already *pretends* otherwise: the playbook seeder ships two
templates with `send_email` steps — **"At-Risk Outreach"** (`playbook_seeder.py:109-113`,
step 1: `send_email` to `cs_assignee`) and **"Silent-Churn Watch"** (`:213-217`, step 1:
`send_email` to `customer`) — and the playbook engine rejects every `send_email` step with
`{"ok": False, "error": "unsupported action type: 'send_email'"}` (`playbook_engine.py:
177-182`). **Those template steps fail on every run today** while the UI presents them as
active playbook steps — the same delivery-integrity trap class as the automations P0 bug
(`docs/planning/automations-delivery-integrity/`).

Two shipped plans deferred customer-facing email as a deliberate "separate slice"
(`segment-actions/prd.md:170`; `churn-triggered-playbooks/prd.md:247-249`). This feature
picks that slice up, grounded in what already shipped.

For whom: founders/CS leads self-hosting Rereflect who want the churn loop to end in a
customer who is contacted and retained, not a dashboard badge.

## Goals & Success Metrics

Success (honest, test-pinned — no fabricated user metrics):

1. The two seeded templates' `send_email` steps **execute with `ok=True`** on a qualifying
   run (currently they always fail). Measured by: pinned engine tests + execution
   `action_log` entries.
2. **"Trigger outreach campaign"** on `/customers` sends a templated or AI-drafted message
   to a cohort with a per-recipient result record. Measured by: campaign send test +
   `BulkActionSummary`-style response.
3. **Opt-out is honored on every send path** (playbook step + bulk): an opted-out customer
   is never emailed, and the skip is loud (recorded in the result, never silent).
4. **No silent drops**: no `RESEND_API_KEY` ⇒ every send attempt records a loud
   `skipped/error: email not configured` — never a false `success`.

## User Personas & Scenarios

- **CS lead (admin/owner)** at a self-hosted SaaS. Sees a churn-risk cohort on
  `/customers`, selects "all N matching this filter", clicks **Bulk Actions → Trigger
  outreach campaign**, drafts with AI or picks a template, reviews the count preview, and
  sends. Expects a per-recipient result and honest "skipped" reasons.
- **Same CS lead** activates the seeded **"Silent-Churn Watch"** playbook. A
  `churn_probability_threshold` rule fires it for a quiet customer; the first step now
  actually emails the customer (template, no LLM content in the auto path) and logs the
  outcome.
- **End customer** receives an outreach email with a `List-Unsubscribe` link; clicking it
  opts them out. Future sends skip them.

## Requirements

### Must-have

1. **Playbook `send_email` step (playbook engine, worker)** — implement the action the
   seeder already ships config for: `{type: "send_email", config: {template, recipient}}`
   with `recipient ∈ {"customer", "cs_assignee"}`.
   - `customer` → the playbook execution's `customer_email`.
   - `cs_assignee` → the email of the CS owner assigned to the customer
     (`customer_health_scores.cs_owner_user_id` → user email); missing assignee ⇒ loud
     per-step failure (not silent).
   - A built-in outreach **template registry**: at minimum keys `re_engagement` and
     `weekly_digest_entry` (the two the seeds reference), each with subject + body
     (plain-text or minimal HTML), placeholders `{{{CUSTOMER_NAME}}}` / `{{{PRODUCT_NAME}}}`
     — registry exposed via an endpoint for the UI.
   - Opt-out check before send; opted-out ⇒ per-step result `skipped: opted out` (loud).
   - No-key (`RESEND_API_KEY` unset) ⇒ per-step result `error: email not configured`
     (loud), never success.
   - Sends carry a `List-Unsubscribe` header with a tokenized unsubscribe URL.
   - **Cross-path dedupe/cooldown (gap-1 fix from critique):** a shared per-recipient
     cooldown `outreach_cooldown:{org_id}:{customer_email}` (Redis DB 1, TTL
     `OUTREACH_COOLDOWN_HOURS`, default 24, env-configurable) set by **both** send paths
     (playbook step + bulk task) — the automation-cooldown pattern, so a customer can
     never receive a playbook outreach and a bulk campaign in the same window. Checked
     before send; an in-cooldown send records a loud `skipped: in cooldown`.
2. **Bulk "Trigger outreach campaign"** — `POST /api/v1/customers/bulk/outreach`
   (admin/owner, `require_admin_or_owner`):
   - Body: `{cohort: Cohort, subject: str, body: str}` + optional `?count_only=true`
     preview (run-batch precedent).
   - Cohort resolution reuses `resolve_cohort` (`cohort_service.py:18-65`); blank emails,
     opted-out customers, and archived (filter-mode) excluded into `skipped` with counts.
   - Server-side 500 cap, 422 over cap (run-batch precedent `RUN_BATCH_MAX_CUSTOMERS`).
   - Sends enqueued to the worker (per-recipient Celery task) — request returns a summary,
     not a blocking send. A `count_only` run mutates nothing.
   - Every send/attempt recorded (see Data Model) with status and error — the audit trail
     is the product of record for "who did we email".
   - **Input validation (gap-2 fix):** `subject` required, ≤ 200 chars; `body` required,
     ≤ 20,000 chars (422 otherwise); cohort 500-cap 422 (run-batch precedent); the shared
     outreach cooldown is honored per recipient (skipped, loud).
3. **Audit trail** — `OutreachCampaign` + `OutreachCampaignRecipient` tables (see Data
   Model). Campaigns listable/filterable; recipients carry status
   `queued|sent|skipped|failed` + error string. A small campaign list surfaces in the UI
   (must: recent campaigns + per-recipient status).
4. **Opt-out state** — `outreach_opt_out` on `customer_health_scores` (default false),
   set via (a) tokenized in-app unsubscribe endpoint, (b) per-customer toggle on the
   Customer 360 profile (admin/owner). Honored by both send paths.
5. **AI draft for the bulk composer** — `POST /api/v1/customers/bulk/outreach/draft`
   (admin/owner): LLM-drafts `{subject, body}` from org context (product name, brand
   voice, tone — the `issue_drafter` pattern: `resolve_generation_llm`, `<feedback>`
   injection-hardening, `LLMUsageLog(task_type="outreach_draft")`, 409 when no LLM
   configured). Optional `cohort` in the body adds honest context (cohort count + dominant
   segment) to the prompt. **Draft populates editable fields — the human clicks Send.**
6. **Frontend** — `BulkOutreachDialog` on `/customers` (mount beside the existing bulk
   dialogs; dropdown item after "Run playbook"): subject + body fields, tone selector +
   "✨ Draft with AI", count-only preview showing `matched`/`skipped (opted out or no
   email)`, Send with confirm. Playbook editor gains per-step config for `send_email`
   (template + recipient selects) — the editor's first per-step config fields
   (`PlaybookEditor.tsx:23-69` is type-select-only today).
7. **Release & docs (gap-3 fix)** — CHANGELOG entry; `docs/SELF_HOSTING.md` email-section
   update (outreach sends, `OUTREACH_COOLDOWN_HOURS`, unsubscribe link, Resend-only
   boundary); roadmap-hygiene markers: the `segment-actions/prd.md:170` and
   `churn-triggered-playbooks/prd.md:247-249` deferral notes marked shipped on this
   branch (`DEV-TRACKING.md:497` rule — correct the marker in the same commit).

### Should-have

7. Campaign list page/section (recent campaigns, recipient counts by status) — or a
   minimal inline list on Settings; exact surface in tech-plan.
8. `send_email` step available on the *single-customer* run path
   (`/playbooks/{id}/run`, `RunPlaybookDropdown`) with the same semantics (it inherits
   them — mostly a test-coverage item).
9. Per-recipient send retry affordance (re-run failed recipients) — lean v1: documented,
   not built.

### Nice-to-have (v2)

- SMTP channel; org-customizable outreach templates (template CRUD UI); cohort-aware
  drafting beyond count/segment; automations-engine `send_customer_email` action type;
  scheduled campaigns; opened/clicked tracking; suppression-list management UI.

## Data Model (SQLAlchemy + Alembic — one migration, single head)

- `customer_health_scores.outreach_opt_out` — `Boolean NOT NULL DEFAULT false`
  (existing table; the playbook engine already reads this table in the worker).
- `outreach_campaigns` — `id`, `organization_id` (FK, indexed), `created_by_user_id`,
  `subject`, `body`, `tone`?, `recipient_count`, `status`
  (`queued|in_progress|done|failed`), `created_at`.
- `outreach_campaign_recipients` — `id`, `campaign_id` (FK, indexed), `customer_email`,
  `status` (`queued|sent|skipped|failed`), `error` (nullable), `created_at`, unique
  `(campaign_id, customer_email)`.
- Unsubscribe token: **signed, stateless** (HMAC over `{org_id}:{email}` with
  `LLM_ENCRYPTION_KEY`) — no token table; verified at the endpoint.

## API Contracts (FastAPI)

| Method/Path | Auth | Body/Query | Response |
|---|---|---|---|
| `POST /api/v1/customers/bulk/outreach` | admin/owner | `{cohort: Cohort, subject, body}` + `?count_only` | 202 `BulkActionSummary`-style `{matched, queued, skipped, errors[]}`; count_only: `{matched, skipped, errors[]}`, 0 mutation |
| `POST /api/v1/customers/bulk/outreach/draft` | admin/owner | `{cohort?, tone?}` | `{subject, body}`; 409 no LLM; 422 bad input |
| `GET /api/v1/outreach/templates` | any authed role | — | `[{key, label, description}]` (registry for the UI) |
| `GET /api/v1/outreach/campaigns` | admin/owner | page/page_size | campaign list + recipient status counts |
| `GET /api/v1/outreach/unsubscribe?token=` | none (public) | — | sets `outreach_opt_out=true`, renders "you're unsubscribed" page |
| `PATCH /api/v1/customers/{email}` (or profile route) | admin/owner | `{outreach_opt_out: bool}` | updated customer profile |

RBAC: all mutations `require_admin_or_owner` (customers-router precedent
`customers.py:680,723`). **No plan gates.**

## Technical Considerations

- **Worker cannot import backend-api** — the send helper exists in the worker
  (`src/email.py` — add/confirm a plain `_send_email` there, mirroring
  `backend-api/src/services/email_service.py` semantics: BYO-key, bool return, loud log),
  and the opt-out check is a worker-local helper reading `customer_health_scores`. A bare
  `try/except` around a worker import = defect on sight (`CLAUDE.md`, automations section).
- **Playbook engine** (`worker-service/src/services/playbook_engine.py`): extend
  `_dispatch_action` (152-182) with the `send_email` branch. Its existing guards apply:
  60-min (playbook, customer) rate limit; requires a `CustomerHealth` row; per-action
  `ok/error` results drive run status — keep that contract, add the `send_email` step's
  results to `action_log` loudly.
- **Bulk send path**: backend route resolves the cohort (loud skips) → creates campaign +
  recipient rows → enqueues one Celery task per recipient (run-batch dispatch precedent
  `playbooks.py:656-660`) → worker task does the opt-out re-check + send + row update.
- **Email transport**: Resend only, BYO-key (no SMTP — that's the honest v1 boundary).
  `List-Unsubscribe` header via the Resend send payload (the send helpers accept extra
  headers — verify in tech-plan). Existing `_send_with_template` (Resend-managed
  templates) is NOT the right vehicle for outreach (these templates are Python-side);
  use the plain send + rendered HTML/text.
- **No HTML escaping in `_render_template`** (`email_service.py:74-88`): LLM-drafted
  bodies must not be injected into HTML. Decision: outreach sends use **plain-text body**
  in v1 (LLM content, safe by construction); the built-in registry templates may be simple
  HTML with escaped placeholders. State this in the spec.
- **Loudness**: every path records per-recipient/per-step status + error; no
  log-only-failure paths (unlike the current `_execute_notify` email branch).
- **Multi-tenancy**: all new tables org-scoped; cohort resolution is already org-scoped
  (`resolve_cohort`); unsubscribe token binds org+email (cross-org token = no-op).
- **Migration discipline**: one Alembic migration, chained to current head, `alembic
  heads` prints exactly one head (CI asserts).
- **Rough sizing**: 5 aspects (below), medium feature; ~1 migration + 2 small tables, ~2
  backend routes, 1 worker task + engine extension, 2-3 frontend surfaces, test
  infrastructure across backend + worker suites. Sequential dependency: `outreach-core`
  first (everything consumes it); `playbook-send-email-step` and `bulk-campaign-api`
  parallel after; UI aspects last.

## Risks & Open Questions

- **Auto-send semantics (resolved by review)**: playbook `send_email` steps send when the
  run happens — a *manual* run is an operator's explicit act; an *auto* run
  (`churn_probability_threshold`/`usage_trend` rules, shadow-gated) is the operator's
  explicit choice to activate the rule. LLM content never enters the auto path (registry
  templates only). This is the agreed line; the PRD review gate is the sign-off.
- **Template content quality**: `re_engagement` / `weekly_digest_entry` bodies are
  self-authored; no claim of conversion performance is made (honest-OSS brand). The
  registry is data, so content can iterate without code.
- **`cs_assignee` resolution failure** (no owner assigned): loud step failure in v1;
  alternative (skip silently) rejected — silent drops are the bug class this feature
  exists to avoid.
- **Unsubscribe endpoint reliability**: stateless HMAC token — no expiry in v1 (note:
  a leaked token can only unsubscribe one email; acceptable). APP_URL must be configured
  for the link to be valid (already a config var).
- **Dual-path cooldown coupling**: the shared `outreach_cooldown` Redis key must be set by
  both send paths or the dedupe guarantee silently narrows to one path — pin with a test
  asserting both write the same key (automation-cooldown precedent).
- **Worker email helper parity**: worker `src/email.py` may lack a plain send — confirm
  in tech-plan; the mirror must stay in exact agreement on env vars and semantics.
- **Campaign list surface**: must-have #3 says "small surface"; exact page vs section is
  a tech-plan choice — the data model is the commitment.
- **In-progress campaign recovery**: a dead worker mid-campaign leaves recipients
  `queued`; v1 documents a re-run affordance (re-enqueue `queued` recipients of a
  campaign) — cheap, include in `bulk-campaign-api` aspect.
- **Stale `PLAYBOOK_TRIGGER_SOURCES`** (`churn_playbook.py:42-46`, missing
  `auto_usage_trend`): out of scope, but note it for a future cleanup.

## Out of Scope

- ~~**Automations-engine `send_customer_email` action type** — deferred v2 (the two worker
  churn/usage mirrors silently skip unknown actions; adding it there is its own
  delivery-integrity project). Playbook steps + bulk campaign only in v1.~~
  **CLOSED 2026-08-20** by `automation-send-customer-email`: the action ships in the
  backend engine and all three worker mirrors (the churn/usage mirrors now handle it
  explicitly and still silent-skip every other type), with a delivery audit table, a
  per-rule deliveries endpoint and a seeded shadow-mode template. See
  `docs/planning/automation-send-customer-email/`.
- ~~**Fixing the other 5 unimplemented seeded playbook action types** (`notify`, `tag`,
  `create_task`, `schedule_task`, `trigger_automation`) — separate card; noted.~~ **CLOSED
  2026-08-27** — shipped as `playbook-action-types` (worker engine handlers + internal
  `playbook_tasks` table + seeder convergence + editor/execution-log UI). See
  `docs/planning/playbook-action-types/`.
- **SMTP transport**; org-editable templates; campaign scheduling/sequences;
  open/click tracking; segment-aware drafting beyond count/segment; bulk opt-out
  management; suppression-list UI.
- **Churn/health computation, churn probability, calibration, M5.3** — untouched.
- **Automation cooldown scheme** — untouched (playbook 60-min rate limit and Redis
  cooldowns are read, never re-keyed).
- **Plan gates** — none (OSS, all unlocked).

## Proposed Aspects (for tech-plan)

1. `outreach-core` — migration (column + 2 tables), outreach template registry, worker
   send helper (opt-out check, List-Unsubscribe), unsubscribe endpoint + token.
2. `playbook-send-email-step` — `send_email` action in `playbook_engine._dispatch_action`
   (customer + cs_assignee recipients, loud results), seeded templates pinned green.
3. `bulk-campaign-api` — `POST /customers/bulk/outreach` (+ count_only, cap, skips),
   campaign/recipient rows, Celery per-recipient send task, draft endpoint.
4. `bulk-campaign-ui` — `BulkOutreachDialog` + dropdown item + campaign list surface.
5. `playbook-editor-email-config` — per-step config fields (template + recipient) in
   `PlaybookEditor`, templates endpoint client, customer-profile opt-out toggle.
