# Spec — bulk-campaign-api

**Feature:** `customer-outreach-email-actions`
**PRD:** `../prd.md` (approved 2026-08-12)
**Aspect boundary:** the bulk "Trigger outreach campaign" send path — queue-time cohort
resolution with loud skips, campaign + per-recipient audit rows, the per-recipient
Celery send task, the campaign list + retry endpoints, and the AI draft endpoint.
Consumes outreach-core (migration, models, `send_outreach_email`) — **outreach-core
contracts are authoritative and fixed; nothing here modifies them.**

## Problem slice

The playbook `send_email` step reaches one customer at a time. The operator-facing bulk
path — select a cohort on `/customers`, send a templated or AI-drafted message to all of
them, and keep a per-recipient audit trail — does not exist. Without this aspect the
flagship "churn prediction → actionable outreach" loop still dead-ends in the dashboard.

## Dependencies (fixed contracts from outreach-core)

- Migration: `outreach_campaigns` (`id, organization_id, created_by_user_id, subject,
  body, recipient_count, status, created_at`), `outreach_campaign_recipients` (`id,
  campaign_id FK CASCADE, customer_email, status, error, created_at`, unique
  `(campaign_id, customer_email)`), `customer_health_scores.outreach_opt_out`
  (outreach-core/plan_20260812.md:46-54).
- Worker sender: `send_outreach_email(db, org_id, customer_email, subject, body, *,
  product_name, template_key=None) -> {ok, status, reason}` with check order
  opt-out → cooldown → no-key → send (outreach-core/spec.md:28-40). Cooldown Redis DB 1,
  key `outreach_cooldown:{org_id}:{customer_email}` — **set/checked only by the sender;
  this aspect never touches the cooldown scheme.**
- Token helpers `make/verify_unsubscribe_token`, template registry, unsubscribe endpoint,
  opt-out PATCH — out of scope here (consumed, not touched).

## In-scope requirements

### R1. `POST /api/v1/customers/bulk/outreach` (admin/owner)

Body `{cohort: Cohort, subject: str, body: str}`, `?count_only=true` preview query flag.

**Validation (all 422, before any mutation):**
- `subject` required, `1..200` chars; `body` required, `1..20000` chars;
  schema `ConfigDict(extra="forbid")` (precedent `feedback_issue_draft.py:37-42`).
- `Cohort` exactly-one-of-`emails`/`filter` validator → 422 (`schemas/cohort.py:33-41`).
- Cohort size > 500 → 422 "cohort of N exceeds batch cap of 500; narrow the filter"
  (run-batch precedent `playbooks.py:77, 611-622`). **count_only returns before the cap
  check** (run-batch precedent `playbooks.py:608-609`) — the preview shows the true count
  and the real run 422s.
- Real run with `matched == 0` → 422 "cohort is empty" (no empty campaign rows; the
  preview already told the operator nothing will send).

**Resolution + skips (queue time, loud):** `resolve_cohort(db, org, cohort)`
(`cohort_service.py:18-65`). Then classify each resolved `CustomerHealth` row:

| skip reason | condition | counted in `skipped` | recipient row |
|---|---|---|---|
| invalid email | `email = row.customer_email.strip().lower()`; empty or no `"@"` | yes | `skipped`, error `"invalid email"` |
| opted out | `row.outreach_opt_out is True` | yes | `skipped`, error `"opted out"` |
| archived | `row.is_archived is True` | yes | `skipped`, error `"archived"` |

Archived semantics by mode (verified `customers.py:258-298`): filter mode with default
`include_archived=false` excludes archived at resolve time (`customers.py:280-281`), so
they never enter `matched` and are not counted — identical to the customers list UI.
Filter mode with `include_archived=true`, and emails mode (which never filters
`is_archived`, `cohort_service.py:39-46`), match archived rows and skip them loudly here.
Cooldown is **not** checked at queue time — the sender re-checks at send time
(outreach-core/plan_20260812.md:203-204).

**count_only=true** → 200, zero mutation, zero task dispatch:
`{matched, queued: 0, skipped, errors: []}`. `matched` = resolved rows
(includes skipped); `skipped` = queue-time skip count computed with the same
classification above; `queued` is present and 0 (additive over the PRD's
two-shape sketch, run-batch precedent `playbooks.py:609`).

**Real run** → 202 (202 precedent `customers.py:1025-1028`):
1. Create `OutreachCampaign` row (`organization_id=current_org.id`,
   `created_by_user_id=current_user.id`, subject/body as given,
   `recipient_count=len(rows)`, `status="queued"`).
2. Create one `OutreachCampaignRecipient` per resolved row: `queued` (error None) for
   sendable rows, `skipped` + error for skip rows.
3. Set campaign `status="in_progress"` if `queued > 0`; if `queued == 0` set
   `status="done"` immediately (all recipients terminal — no task will ever run).
4. Dispatch one Celery task per `queued` recipient: `app.send_task(
   "tasks.outreach.send_outreach_email", args=[campaign_id, recipient_id])`
   via `get_celery_app()` (`playbooks.py:221-226` pattern). Dispatch failure per
   recipient → log + append to `errors` (run-batch precedent `playbooks.py:656-660`
   catches and logs; the retry endpoint recovers).
5. Respond 202 `{matched, queued, skipped, errors}`.

**Response schema (single, exact — the UI aspect consumes this):**
```python
class BulkOutreachResponse(BaseModel):
    matched: int   # resolved cohort rows (== recipient rows created)
    queued: int    # tasks dispatched (== matched - skipped on real run; 0 on count_only)
    skipped: int   # queue-time skips (invalid email | opted out | archived)
    errors: List[str] = []
```

### R2. Worker task — `services/worker-service/src/tasks/outreach.py`

`@shared_task(bind=True, name="tasks.outreach.send_outreach_email")` — name + dispatch
string identical (churn_playbooks precedent `churn_playbooks.py:24`,
`playbooks.py:226`). Registered via `include` in `celery_app.py:45-69` (`src.tasks.outreach`).

`send_outreach_email(campaign_id: int, recipient_id: int) -> dict`, session opened
internally with `get_db_session()` (`churn_calibration.py:76` pattern):
1. Load recipient; missing → log, return `{"status": "error", "error": "recipient not found"}`.
2. **Idempotence guard:** recipient already terminal (`sent|skipped|failed`) → return
   early (duplicate dispatch from retry racing a live task is a no-op).
3. Load campaign (org_id, subject, body) + org `product_name_display`; missing → mark
   recipient `failed`, log, return.
4. Re-check opt-out via the sender — call `send_outreach_email(db, org_id,
   customer_email, subject, body, product_name=..., template_key=None)`
   (outreach-core owns opt-out/cooldown/no-key ordering).
5. Map result: `ok` → status `sent`; `skipped` → status `skipped` + error=reason;
   `failed` → status `failed` + error=reason. Update recipient row, commit.
6. **Campaign transition:** if campaign `status == "queued"` → `in_progress`
   (defensive; the route normally sets it). If **no** recipient of this campaign is left
   in `queued|in_progress` → `status = "done"`.
7. Catch-all: any exception → recipient `failed` with `str(exc)`, log, return
   `{"status": "error", "error": ...}` — never re-raise (`churn_playbooks.py:43-62`).

Imports must be worker-local only (`test_worker_import_sweep.py` pins this — no
`src.api`, no backend packages).

### R3. `GET /api/v1/outreach/campaigns` (admin/owner)

Pagination `page` (≥1), `page_size` (1..100, default 20 — `customers.py:334-335`
convention). Org-scoped, newest first. Per-campaign recipient status counts from one
GROUP BY on `outreach_campaign_recipients` (no N+1).

```python
class CampaignRecipientCounts(BaseModel):
    queued: int; sent: int; skipped: int; failed: int

class CampaignSummary(BaseModel):
    id: int; subject: str; status: str            # queued|in_progress|done|failed
    recipient_count: int
    counts: CampaignRecipientCounts
    created_at: datetime

class CampaignListResponse(BaseModel):
    items: List[CampaignSummary]; total: int; page: int; page_size: int
```
(Paginated shape per `customers.py:89-94` / `playbooks.py:292-298`.)

### R4. `POST /api/v1/outreach/campaigns/{id}/retry` (admin/owner)

Dead-worker recovery (PRD risk note `prd.md:231-233`). Org-scoped 404 if the campaign
belongs to another org. Count recipients with `status == "queued"`; dispatch one task
per queued recipient (same task name/args as R1); campaign `queued→in_progress` when ≥1
dispatched. Respond `BulkOutreachResponse` with `matched` = queued-found count,
`queued` = dispatched, `skipped = 0`, `errors` = dispatch failures. All-terminal
campaign → 200 with zeros (no-op). Re-enqueues only `queued` — terminal rows are never
reset (audit trail is immutable in v1).

### R5. `POST /api/v1/customers/bulk/outreach/draft` (admin/owner)

Body `{cohort?: Cohort, tone?: str}`, `extra="forbid"` (validated by `Cohort` when
present). New service `src/services/outreach_drafter.py` following the issue_drafter
pattern verbatim (`issue_drafter.py`):
- Gate: `resolve_generation_llm(org.id, db)` (`issue_drafter.py:29,214`); `not
  cfg.is_configured` → `LLMNotConfiguredError` (`issue_drafter.py:46-48,216-219`) →
  route maps to **409** (`feedback_issue_draft.py:93-98`). Parse/provider errors →
  `OutreachDraftError`/catch-all → **502** (`feedback_issue_draft.py:99-110`).
- Tone: `payload.tone or org.default_tone or "professional"` (`issue_drafter.py:221`;
  org fields `organization.py:30-32`).
- Prompt inputs — **all trusted/derived, none raw**: product name
  (`org.product_name_display or "Rereflect"`), brand voice + tone, and cohort context =
  resolved-row count + dominant segment (most common non-null `row.segment`; segment
  values are `SEGMENT_SLUGS`, `segment_service.py:44-51`, stored on
  `customer_health_scores.segment`, `customer_health.py:34`). Never feed cohort emails
  or filter `search` text to the LLM. Brand voice wrapped in a delimited block labelled
  "data, not instructions" (`issue_drafter.py:63-78` hardening).
- Caps: `MAX_TOKENS` ~700, 60 s timeout (`issue_drafter.py:41-42`); output parsed
  defensively (plain/fenced JSON, `issue_drafter.py:121-160`); subject trimmed to 200,
  body to 20,000 (the R1 send caps).
- Usage log: `LLMUsageLog(task_type="outreach_draft", ...)` (`issue_drafter.py:163-196`;
  `task_type` `String(30)`, `llm_usage_log.py:13`), logging failure never fails the
  draft.
- Response 200 `{subject: str, body: str}`. **Never sends, never creates campaign or
  recipient rows.**

### R6. Where the routes live + registration

- `POST /customers/bulk/outreach` and `POST /customers/bulk/outreach/draft` in
  `src/api/routes/customers.py`, in the bulk section beside `/bulk/tags` +
  `/bulk/assign-owner` (`customers.py:639-758`), **before** the `/{email}` parametric
  routes — static-paths-first ordering note `customers.py:449-452`.
- `GET /outreach/campaigns` + `POST /outreach/campaigns/{id}/retry` appended to the
  outreach router (`src/api/routes/outreach.py`, prefix `/api/v1/outreach` — created by
  outreach-core; no `main.py` change needed).
- All three endpoints `dependencies=[Depends(require_admin_or_owner)]`
  (`dependencies.py:255`; precedent `customers.py:680,723`). **No plan gates** (PRD
  `prd.md:170`).

## Out-of-scope boundaries

- No migration (outreach-core's); `alembic heads` must stay exactly one.
- No playbook `send_email` step, no automations changes, no cooldown-scheme changes,
  no SMTP, no per-recipient resend of failed rows (only `queued` re-enqueue in v1),
  no org-editable templates, no scheduling/sequences, no open/click tracking.
- No changes to outreach-core files (`outreach_sender.py`, `outreach_tokens.py`,
  `outreach_templates*.py`, the migration).
- The backend route never checks cooldown and never reads `RESEND_API_KEY` — the sender
  owns both (loud `failed: email not configured` per recipient when unset).

## Acceptance criteria (testable)

- AC1: real run 202 with `{matched, queued, skipped, errors}`; one
  `OutreachCampaign` row + one recipient row per resolved email (queued|skipped with
  error); one `send_task` call per queued recipient with
  `name == "tasks.outreach.send_outreach_email"` and `args == [campaign_id,
  recipient_id]`.
- AC2: count_only returns `{matched, queued: 0, skipped, errors: []}` (200) and creates
  zero rows and zero tasks; empty-cohort count_only → 200 zeros.
- AC3: skips counted loudly — blank/non-email, opted-out, archived (emails mode and
  filter `include_archived=true`) each land in `skipped` + a `skipped` recipient row
  with the reason; filter mode default excludes archived from `matched` (no skip count).
- AC4: subject > 200 or body > 20000 or extra body field → 422; `Cohort` with both /
  neither `emails`+`filter` → 422; cohort > 500 on real run → 422; `matched == 0` real
  run → 422.
- AC5: member role → 403 on all three endpoints; unauthenticated → 401.
- AC6: worker task — terminal-guard (already-`sent` recipient is a no-op); sender
  result mapping (`ok→sent`, `skipped→skipped`+reason, `failed→failed`+reason);
  campaign `done` only when all recipients terminal; missing recipient → error dict,
  no raise; task-level exception → recipient `failed`, no re-raise.
- AC7: campaign list returns org-scoped campaigns newest-first with per-status counts
  summing to `recipient_count`; page/page_size respected.
- AC8: retry re-enqueues only `queued` recipients (one dispatch each), 404 for
  cross-org campaign id, no-op 200 zeros when none queued.
- AC9: draft returns `{subject, body}` with the LLM mocked; no LLM configured → 409 and
  no `LLMUsageLog` row; success writes exactly one `LLMUsageLog(task_type=
  "outreach_draft")`; malformed output → 502; `cohort` context (count + dominant
  segment) present in the captured prompt; raw emails never appear in the prompt.
- AC10: worker `test_worker_import_sweep.py` still passes; `alembic heads` == 1;
  backend + worker full suites green.

## Dependencies & sequencing

Runs **after** outreach-core lands in this worktree (Phase-0 gate in the plan). Venv:
outreach-core plan §1 commands (`python3.12 -m venv venv` + `pip install -r
requirements.txt` in `services/backend-api` and `services/worker-service`) — create if
missing (they do not exist in the worktree today, verified 2026-08-12). No new packages,
no new env vars, no new migration.

## Open questions / risks

- **Worker model mirrors:** outreach-core's plan does not list worker mirror columns for
  the campaign tables or `outreach_opt_out` on the worker `CustomerHealth` mirror
  (`worker models/__init__.py:419-479` lacks it today). This aspect needs worker model
  classes for both tables + `product_name_display` on the worker `Organization` mirror
  (`worker models/__init__.py:34-51` lacks it) for the task's campaign-status updates and
  sender `product_name`. Assumed: outreach-core adds `outreach_opt_out` to the mirror
  (its sender reads it); the rest is this aspect's Phase 1 (additive mirror classes, no
  migration). Phase-0 gate verifies and reports.
- **Bulk sends are plain text:** campaign subject/body are final operator/AI-authored
  plain text — no registry rendering on the bulk path (no HTML-escaping exposure,
  PRD `prd.md:192-195`); the sender's `product_name` is only used for the
  `List-Unsubscribe` header composition.
- **Double-submit:** no idempotency key — each POST is a new campaign; the shared
  Redis cooldown (checked in the sender) is the cross-campaign dedupe.
- **`recipient_count`** = recipient rows created (== `matched`), so list counts always
  sum to it.
