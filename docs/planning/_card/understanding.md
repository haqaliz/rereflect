# Understanding — inbound Zendesk status-sync

## What this is really asking

When a linked Zendesk ticket's status changes (e.g. agent marks it `solved`), reflect that
back onto the Rereflect feedback's `workflow_status` — the inbound direction, closing the loop
that ingestion (tickets → feedback) opened. This is the **Zendesk reuse** of the provider-agnostic
reconcile core that shipped with Jira status-sync (`jira-status-sync`, 2026-07-12). The Jira feature
is a near-verbatim blueprint.

## Affected services / areas

- **worker-service** (most of the work): new status-sync poller task + Zendesk client batch-status method + Celery beat entry.
- **backend-api**: new migration (opt-in columns), model updates (both mirrors), `PATCH /status-sync` toggle + status-sync manual trigger routes, `GET /status` response fields.
- **frontend-web**: `ZendeskStatusSyncCard` component (clone of `JiraStatusSyncCard`), mount on the Zendesk settings page, API-client fns + types, tests.
- **analysis-engine**: none.

## What already exists (reuse as-is)

- **Reconcile core** `services/{worker,backend}/src/services/status_sync_core.py` — byte-identical both mirrors. `VALID_STATUSES=("new","in_review","resolved","closed")` (target side is generic Rereflect). BUT its category vocabulary `{new,indeterminate,done}` + `CATEGORY_RANK` is **Jira's `statusCategory`** — Jira-coupled.
- **Jira blueprint** to clone: two-task fan-out (`sync_all_jira`→`sync_jira_org`), opt-in gating (`is_active` AND `status_sync_enabled`), 15-min beat, `apply_status_change_worker` (writes ONE `FeedbackWorkflowEvent status_changed`, `actor_id=None`, `metadata.source="jira"`, **no webhook** — deferred), `PATCH /status-sync` + `POST /sync` routes (`require_admin_or_owner`, 202/502), migration `c4d5e6f7a8b9`.
- **Zendesk integration**: `ZendeskClient` (Basic `email/token:token`, `https://{sub}.zendesk.com/api/v2`, 429/Retry-After sleep→`ZendeskTransientError`, 401/403→`ZendeskAuthError`); ingest poller `sync_zendesk_org` + beat `sync-zendesk-every-15-min`; `POST /sync` manual trigger (`send_task`); `ZendeskIntegration` model (both mirrors, unique per org); routes gated `require_admin_or_owner`.
- **Ticket↔feedback linkage**: `feedback.source='zendesk'`, `feedback.source_external_id`=ticket id (set in `source_events.py` `_process_event_for_source`). **No link table** (migration `z1a2b3c4d5e6` explicitly avoided one). Poll set = `SELECT feedback WHERE source='zendesk' AND source_external_id IS NOT NULL AND organization_id=:org`.
- **Frontend template**: `components/settings/JiraStatusSyncCard.tsx` (114 lines) + its component/api-client tests are direct clones; Zendesk page/api/tests are near-clones already.

## The real gaps (net-new engineering)

1. **Batch ticket-status fetch by ID** — neither Zendesk client can fetch a ticket's current status by id. Add `GET /api/v2/tickets/show_many.json?ids=1,2,3` → `{ticket_id: {"status": ...}}`, chunked (Zendesk caps ~100 ids/call). This is the one genuinely hard missing capability. (Analogous to Jira's `search_issues`.)

2. **Category-less status mapping** — Zendesk statuses are the flat set `new/open/pending/hold/solved/closed` (no `statusCategory`). The Jira reconcile core can't be reused verbatim. Decision needed (see Open Questions Q1).

3. **Per-feedback "last observed status" for the change-gate + baseline seed** — Jira stored `jira_status_category` on the link row to (a) detect change and (b) seed-without-applying on first poll. Zendesk has no link row. Without a stored last-status, re-applying the mapping every poll would **retroactively bulk-change all existing Zendesk feedback on first enable** — exactly the "no bulk backfill" behavior the brief forbids. Need somewhere to store last-observed ticket status per feedback (Open Questions Q2).

4. **Separate sync-status columns** — Zendesk's **ingest** poller already writes `last_synced_at`/`last_sync_status`/`last_error`. Jira reused those because Jira had no separate ingest poller. Zendesk has TWO pollers, so status-sync must NOT clobber the ingest indicators — it needs its own `last_status_synced_at` (+ error/status) columns (Open Questions Q3).

## Open questions (for the interview)

- **Q1 — mapping model.** (a) Direct Zendesk-status→workflow_status map with a per-org `status_mapping` override (transparent to operator, e.g. `solved→resolved, closed→closed, open/pending/hold→in_review, new→new`), reusing only `VALID_STATUSES` validation; **or** (b) collapse Zendesk status → Jira's 3 categories then reuse `resolve_target_status` verbatim. Leaning (a) — more honest/transparent, and Zendesk is single-ticket-per-feedback so `most_advanced`/rank is unneeded. Default mapping for `solved` vs `closed`: map to `resolved` vs `closed` respectively, or both to `resolved`?
- **Q2 — where to store last-observed ticket status** for change-gate + seed: new nullable column on `feedback`, a `source_metadata` JSON key, or a small `feedback_zendesk_sync` sidecar table. (Sidecar mirrors Jira's link-row model most faithfully and keeps the hot `feedback` table clean.)
- **Q3 — dedicated status-sync markers** on `zendesk_integrations`: `status_sync_enabled` (Bool, default false) + `status_mapping` (JSON) + `last_status_synced_at` + `last_status_sync_error`/`last_status_sync_status` (to avoid clobbering ingest's `last_*`).
- **Q4 — outbound webhook.** Jira deferred the outbound `feedback.status_changed` webhook on a sync-driven change. Match that (defer) for Zendesk? (Recommended: yes, defer — stay byte-parallel to Jira.)
- **Q5 — closed tickets.** Zendesk `closed` is terminal/archived and may drop out of `show_many` after archival. Acceptable to stop syncing archived tickets (they're already terminal)?

## Contradictions / notes

- The card's proposed default (`solved`+`closed → resolved`, `open/pending/hold → in_review`, `new → new`) collapses `closed` into `resolved`; but Rereflect has a distinct `closed` workflow status, so `closed→closed` is arguably more faithful. Resolve in Q1.
- Reconcile core is shared with Jira (and the in-flight `feat/asana-status-sync` worktree). **Do not mutate Jira's category constants** — add Zendesk mapping alongside so Jira stays byte-identical (characterization-locked).
- New migration must chain `down_revision="c4d5e6f7a8b9"` (current single head, verified across 66 migrations).
