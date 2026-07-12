# Card — feat/asana-status-sync (freeform)

**Type:** feat
**Slug:** asana-status-sync
**Branch:** feat/asana-status-sync
**Source:** freeform (no GitHub issue) — brief captured from the `rereflect-next` recommendation (2026-07-12) + user go-ahead.

## Brief

Build **inbound status-sync for the Asana integration** to close its loop, mirroring the
`jira-status-sync` feature merged 2026-07-12. Today the Asana integration (shipped slice 1,
2026-07-06) is **outbound-only**: it creates Asana tasks from feedback items. When the linked
Asana task is later completed by an engineer, Rereflect's feedback item does not reflect it.
This feature reconciles the Asana task's completion state back onto the linked feedback item's
`workflow_status`.

### Core behavior (first testable slice)
- A **Celery beat** polls Asana for the current status of tasks Rereflect created from feedback
  (recorded in the existing Asana task link table).
- Each completed task maps onto the linked feedback item's `workflow_status`
  (`completed=true → resolved`).
- **Opt-in per org, off by default** (mirror Jira status-sync).
- **Non-destructive baseline-seed on first poll** — no retroactive bulk backfill.
- Emit a `status_changed` timeline event tagged `source=asana` when a change is applied,
  via the shared `apply_status_change` worker mirror.
- Manual "Sync now" route.

### Design constraints / decisions carried from the recommendation
- **Reuse the provider-agnostic reconcile core** that `jira-status-sync` factored out
  (`docs/planning/jira-status-sync/`) — it was built explicitly for "Zendesk/Asana reuse".
- **Reuse the existing encrypted Asana PAT client** and the `feedback ⇄ asana_task` link.
- **Poll-first.** Self-hosted instances are frequently behind NAT/firewalls, so inbound
  webhooks are unreliable. Build polling first; an Asana webhook path is optional v2.
- **Rate limits.** Respect Asana Cloud rate limits and `Retry-After` (the Jira/Zendesk pollers
  already have a throttle precedent).

### Known caveat (must design around)
- Asana has **no `statusCategory`** like Jira. A task's state is a `completed` boolean (plus
  optional section membership / custom fields). So the reconcile core's 3-bucket category map
  (`done`/`indeterminate`/`new`) can only be fed **`done` (completed=true) vs `new`** in slice 1
  — there is no clean intermediate ("in_review"/"in_progress") state. Leave section-name /
  custom-field mapping to v2.
- The **current Asana client only creates tasks** — a get-task status fetch (`completed`,
  `completed_at`, optionally `memberships` for section) must be added before the reconcile core
  has anything to read.

## Provenance (from AI-TRACKING.md / DEV-TRACKING.md)
- Jira status-sync shipped 2026-07-12 (`AI-TRACKING.md:58`, `DEV-TRACKING.md:198`); its reconcile
  core was **factored provider-agnostic for Zendesk/Asana reuse**.
- Asana slice 1 shipped 2026-07-06 (`DEV-TRACKING.md:201`). **Deferred v2** explicitly includes
  "inbound status-sync back to Rereflect" (`DEV-TRACKING.md:210`, `AI-TRACKING.md:60`).
- **Linear** already does inbound sync (`linear_webhook.py`); **Jira** now does too — Asana is the
  last outbound-only work-management integration.

## Open questions (for the deep dig / PRD)
- What is the exact `workflow_status` enum on the feedback model, and does `completed → resolved`
  suffice, or should un-completing a task revert `resolved → in_progress`/`new`?
- Where does the `feedback ⇄ asana_task` link live, and what columns does it carry (task gid,
  org, feedback id, last-synced state)?
- What is the shape of the provider-agnostic reconcile core the Jira feature factored out — what
  does an "Asana adapter" need to implement (category derivation from `completed`)?
- Poll cadence (beat interval) and batching strategy for fetching many task statuses.
- Where does per-org opt-in + status-mapping config live (reuse Jira's `status_mapping` pattern
  / columns, or Asana-specific)?
