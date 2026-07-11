# Aspect spec — inbound-status-sync

**Feature:** `jira-status-sync` · **Aspect:** `inbound-status-sync` (the whole slice-1 feature is one aspect)
**PRD:** `../prd.md` · **Dig:** `../../_card/understanding.md`

## Problem slice & user outcome
For an org that opts in, a linked Jira issue moving status category (To Do / In Progress / Done)
automatically updates the linked Rereflect feedback item's `workflow_status`, with a timeline audit
event — poll-first (no ingress required), non-destructive on enable, and never clobbering a manual
edit unless Jira genuinely moved.

## In scope
- Per-org opt-in (`status_sync_enabled`, default false) + category→status mapping (`status_mapping`
  JSON, zero-config default in code).
- Poll-first Celery beat (fan-out → per-org) reconciling `feedback_jira_issues` via JQL.
- Change-gated apply through `apply_status_change(actor_label="jira-sync")`; first-poll baseline-seed
  (no write); multi-issue most-advanced-category-wins.
- Worker Jira client with 429/`Retry-After` throttle; auth/404 handling; durable last-sync status.
- Backend: extend `GET /status`; `PATCH` toggle; `POST /sync` manual trigger.
- Frontend: toggle + last-synced/last-error indicator + "Sync now" on the existing Jira tile.
- A pure, provider-agnostic reconcile core reusable by Zendesk/Asana later.

## Out of scope
Jira webhook (real-time), per-status-name mapping + editor UI, Rereflect→Jira write-back, OAuth/
Server-DC/multi-site, opt-in retroactive backfill-on-enable.

## Acceptance criteria (testable)
1. Sync runs only for `is_active AND status_sync_enabled` orgs; disabled org = zero calls.
2. Jira `statusCategory.key` maps `done→resolved`, `indeterminate→in_review`, `new→new` by default;
   `status_mapping` JSON overrides per key.
3. First poll after enable **seeds** `jira_status_category` on each link and applies **no**
   `workflow_status` change (NULL→value is not a "change").
4. A subsequent category transition applies exactly one `status_changed` event (metadata
   `source=jira`), invalidates cache, and dispatches the `feedback.status_changed` webhook.
5. Second identical poll is a no-op (no event, no webhook).
6. Multi-issue feedback: target = most-advanced category across links (`done>indeterminate>new`).
7. 429/`Retry-After`→retry (≤3), 401/403→record `last_sync_status=error` no disconnect, 404→skip
   that link, none abort the org batch.
8. `POST /sync` requires admin/owner, is org-scoped, and returns 502 (not 500) on broker failure.
9. Frontend toggle persists `status_sync_enabled`; indicator shows `last_status_synced_at` +
   `last_sync_status`/`last_error`; "Sync now" enqueues.

## Dependencies & sequencing
Migration+models → (client method ∥ reconcile core) → worker task+beat → backend routes → frontend.
Reconcile core is independent (pure) and can be built in parallel with the client method.

## Risks
Alembic 6-heads (chain off `j1k2l3m4n5o6`); Jira `/search`→`/search/jql` API migration; large-org
JQL pagination.
