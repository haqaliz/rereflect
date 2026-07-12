# PRD — Inbound Zendesk Status-Sync

**Status:** Draft
**Slug:** `zendesk-status-sync`
**Branch:** `feat/zendesk-status-sync`
**Author:** (rereflect-begin-fast)
**Source:** freeform (selected via `rereflect-next`); brief in `docs/planning/_card/card.md`, dig in `docs/planning/_card/understanding.md`

---

## Problem Statement

Rereflect's Zendesk integration is **one-way**: support tickets flow *in* and become feedback items,
but when an agent resolves or progresses a ticket **in Zendesk**, the linked Rereflect feedback's
`workflow_status` stays frozen at whatever it was (usually `new`). For any org whose feedback is
Zendesk-sourced, the workflow status column — which drives the feedback board, filters, and
churn/health surfaces — is therefore quietly unreliable.

This is the **exact loop Jira status-sync closed on 2026-07-12** (`jira-status-sync`). That slice
deliberately factored a provider-agnostic reconcile core and named "Zendesk and Asana inbound-sync"
as the intended reuse (`docs/planning/jira-status-sync/prd.md:193`). Zendesk's own deferred-v2 list
includes "write-back / bidirectional status sync to Zendesk" (`DEV-TRACKING.md:221`). This PRD builds
the **inbound** half for Zendesk.

**Evidence it's real:** the pattern is already shipped and wanted in-repo (Jira status-sync + a
Linear inbound webhook exist); Zendesk is the cleanest next reuse because tickets already link to
feedback and the ingest poller/client/webhook receiver already exist.

## Goals & Success Metrics

**Goal:** A linked Zendesk ticket's status change is reflected onto the feedback's `workflow_status`
— in near-real-time via webhook, with a 15-minute poll as the catch-up/NAT-friendly fallback —
**opt-in per org, off by default, and non-destructive on first enable.**

Success (verifiable, honest — no fabricated metrics):
- With status-sync enabled, moving a ticket to `solved` in Zendesk sets the linked feedback to
  `resolved` within one webhook round-trip (or ≤15 min by poll), emitting exactly one
  `status_changed` timeline event tagged `source=zendesk`.
- On first enable, **no existing feedback is retroactively bulk-changed** (baseline seed): the first
  observation of each ticket records its status without applying a change.
- Re-running the poll with no ticket change is a **no-op** (no duplicate timeline events) — verified
  by a "poll twice, second is a no-op" test.
- Jira status-sync behavior is **byte-identical** after this change (shared reconcile core untouched
  for Jira; characterization-locked).

## User Personas & Scenarios

- **CS lead / support manager (operator-admin):** connects Zendesk, flips on status-sync, and now the
  Rereflect feedback board tracks ticket resolution automatically — no manual status updates.
- **Self-hoster behind NAT:** cannot expose a public webhook → relies on the 15-min poll; still gets
  eventual sync. (Webhook is additive, not required.)
- **Member (non-admin):** sees accurate `workflow_status` on feedback; cannot change sync settings.

## Requirements

### Must-have
1. **Opt-in per org, off by default.** `zendesk_integrations.status_sync_enabled` (Bool, default false).
   Poll and webhook status-reconcile both gated on it (+ `is_active`).
2. **Zendesk status → workflow_status mapping** with a per-org override:
   - Defaults: `new→new`, `open→in_review`, `pending→in_review`, `hold→in_review`, `solved→resolved`, `closed→closed`.
   - Override stored in `zendesk_integrations.status_mapping` (JSON, Zendesk-status-name → workflow_status).
   - Target values validated against `VALID_STATUSES` (`new|in_review|resolved|closed`); keys validated against the Zendesk status set.
3. **Batch ticket-status fetch** — `ZendeskClient.show_many(ids)` → `GET /api/v2/tickets/show_many.json?ids=…`
   returning `{ticket_id: status}`, chunked ≤100 ids/request, reusing existing auth + 429/Retry-After handling.
4. **Poll-first reconcile** — Celery beat every 15 min: `sync_all_zendesk_status` → `sync_zendesk_status_org`
   (two-task fan-out mirroring `jira_sync.py`), over the poll set
   `feedback WHERE source='zendesk' AND source_external_id IS NOT NULL AND organization_id=:org`.
5. **Real-time webhook reconcile** — extend the existing Zendesk webhook receiver
   (`/api/v1/webhooks/zendesk/events`, HMAC-verified) to handle `ticket.updated`/status-change events:
   reconcile that single ticket through the **same shared reconcile function** as the poll.
6. **Change-gate + non-destructive baseline seed** via a new `feedback_zendesk_sync` sidecar table
   (`feedback_id` PK/FK, `last_ticket_status`, `last_status_synced_at`):
   - First observation of a ticket (no sidecar row) → record status, **do not** apply a change (seed).
   - Subsequent observation where fetched status ≠ `last_ticket_status` → apply mapped status, update row.
   - No change → no-op.
7. **Apply via a worker-side writer** mirroring `apply_status_change_worker`: set `feedback.workflow_status`,
   emit exactly one `FeedbackWorkflowEvent(event_type="status_changed", actor_id=None,
   metadata={"source":"zendesk","zendesk_status":…,"zendesk_ticket_id":…})`. No-op if already equal.
8. **Backend routes** (`require_admin_or_owner`): `PATCH /api/v1/integrations/zendesk/status-sync`
   (`{enabled, status_mapping?}`, 422 on invalid mapping) + `POST /api/v1/integrations/zendesk/status-sync/sync`
   manual "Sync now" (202, `send_task`, 502 on broker failure). `GET /status` exposes
   `status_sync_enabled`, `status_mapping`, `last_status_synced_at`, `last_status_sync_error`.
9. **Frontend `ZendeskStatusSyncCard`** (clone of `JiraStatusSyncCard`): toggle, last-synced/error
   indicator, "Sync Now" button; mounted on the Zendesk settings page, admin/owner only.
10. **Dedicated status-sync markers** on `zendesk_integrations` (`last_status_synced_at`,
    `last_status_sync_error`) — **must not** clobber the ingest poller's `last_synced_at`/`last_sync_status`/`last_error`.
11. **Throttle / resilience** parity with Jira/ingest: 429 `Retry-After` sleep → transient → Celery retry;
    401/403 → record `last_status_sync_error`, **do not** disconnect, no retry.

### Should-have
- Manual "Sync now" surfaces a clear 502 message when the worker/broker is unavailable (Jira parity).
- Poll set chunked so a large backlog reconciles over several beats (per-run cap) rather than one huge call.
- Operator setup docs (`docs/SELF_HOSTING.md`) + landing copy updated ("Zendesk status-sync available").

### Nice-to-have (defer)
- Per-status-name mapping editor UI (ship the JSON override + sensible defaults; a rich editor is v2).
- Outbound `feedback.status_changed` webhook fired on a Zendesk-driven change (Jira deferred this too).

## Technical Considerations

- **Services:** worker-service (poller + client method + beat + reconcile), backend-api (migration, models
  ×2 mirrors, routes, webhook-receiver extension), frontend-web (card + api client + tests). analysis-engine: none.
- **Shared reconcile function** used by BOTH poll and webhook — a pure `reconcile_zendesk_status(fetched_status,
  stored_status, mapping) → (action, target_status|None)` where `action ∈ {seed, noop, changed}`. Lives in a
  Zendesk-specific module; **does not modify** `status_sync_core.py`'s Jira category constants (Jira stays
  byte-identical). May reuse `VALID_STATUSES` + the seed/change-gate *shape* from the Jira core.
- **Multi-tenancy:** everything scoped by `organization_id` via the org's `ZendeskIntegration`; cross-org tickets never touched.
- **Model parity:** `ZendeskIntegration` exists in both `backend-api` and `worker-service` mirrors — both updated together (parity is test-enforced). New `FeedbackZendeskSync` model added to both mirrors.
- **Migration:** new revision, `down_revision="c4d5e6f7a8b9"` (current single head, verified across 66 migrations). Adds `status_sync_enabled`, `status_mapping`, `last_status_synced_at`, `last_status_sync_error` to `zendesk_integrations` + creates `feedback_zendesk_sync`.
- **Webhook path:** the receiver already HMAC-verifies and fail-closes on missing secret. The status branch must (a) resolve the org from the integration, (b) gate on `status_sync_enabled`, (c) reconcile only the affected ticket. Idempotent — a webhook and a poll observing the same change must not double-apply (the change-gate via the sidecar guarantees this).
- **Beat:** add `sync-zendesk-status-every-15-min` to `celery_app.py` + register `src.tasks.zendesk_status_sync` in `include`.

### Data Model (additions)

```
zendesk_integrations  (+ columns)
  status_sync_enabled     Boolean  NOT NULL  server_default false
  status_mapping          JSON     NULL      -- {zendesk_status: workflow_status}
  last_status_synced_at   DateTime NULL
  last_status_sync_error  Text     NULL

feedback_zendesk_sync  (new)
  feedback_id             FK feedback.id  PRIMARY KEY  (CASCADE)
  last_ticket_status      String(20)  NOT NULL
  last_status_synced_at   DateTime    NOT NULL
```

### API Contracts

- `PATCH /api/v1/integrations/zendesk/status-sync` → `{enabled: bool, status_mapping?: {str:str}}` → `ZendeskStatusResponse`
- `POST  /api/v1/integrations/zendesk/status-sync/sync` → 202 `{status: "queued"}` (or 502)
- `GET   /api/v1/integrations/zendesk/status` → adds `status_sync_enabled`, `status_mapping`, `last_status_synced_at`, `last_status_sync_error`
- `POST  /api/v1/webhooks/zendesk/events` (existing) → now also reconciles status on ticket-update events

## Risks & Open Questions

- **R1 — double-apply (webhook + poll).** Mitigated by the sidecar change-gate: whichever observes the change first applies it and updates `last_ticket_status`; the other sees no delta → no-op. Must be covered by a test.
- **R2 — closed/archived tickets.** Zendesk `closed` is terminal and may drop out of `show_many` after archival. Acceptable: once mapped to `closed`, the feedback is terminal too; a missing ticket in `show_many` is skipped (no error). Confirmed acceptable.
- **R3 — reconcile core coupling.** The Jira core is category-based; we add a Zendesk-specific reconcile rather than generalizing it, to keep Jira byte-identical and avoid destabilizing the in-flight `feat/asana-status-sync` worktree that shares the core.
- **R4 — user manually set a status.** If a human set the feedback to `resolved` and the ticket later goes back to `open`, the poll would move it to `in_review`. This matches Jira's behavior (Zendesk is source-of-truth when sync is on). Documented, not gated.
- **R5 — webhook event shape.** Need to confirm the exact payload/event-type Zendesk sends for status changes vs. the ingestion `ticket.created` path the receiver already handles. Resolve during the webhook aspect dig.

## Out of Scope

- **Outbound write-back / bidirectional sync** (Rereflect → Zendesk). Explicitly v2 (`DEV-TRACKING.md:221`).
- OAuth flow, per-comment ingestion, historical backfill, status/tag/view filters, multiple subdomains per org (pre-existing Zendesk v2 deferrals).
- Rich per-status-name mapping editor UI (JSON override + defaults ship; editor is v2).
- Any change to Jira/Asana status-sync or the shared `status_sync_core.py` Jira constants.
