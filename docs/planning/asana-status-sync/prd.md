# PRD — Asana Inbound Status-Sync

**Slug:** `asana-status-sync`
**Branch:** `feat/asana-status-sync`
**Type:** feat (freeform — no GitHub issue)
**Status:** Draft for review
**Author:** captured via `rereflect-begin-fast`, 2026-07-12
**Source docs:** `docs/planning/_card/card.md`, `docs/planning/_card/understanding.md`

---

## Problem Statement

The Asana integration (slice 1, shipped 2026-07-06) is **outbound-only**: an operator can create an
Asana task from a feedback item, but when the engineer later completes that task in Asana, the
Rereflect feedback item's `workflow_status` never updates. It sits at whatever status it had when
the task was created. The user has to manually reconcile Asana and Rereflect, or the feedback
silently rots as "open" long after the work shipped.

This is the same loop that was just closed for **Jira** (`jira-status-sync`, merged 2026-07-12) and
that **Linear** has had since March. Asana is now the **only** work-management integration that is
outbound-only. The Jira feature deliberately factored its reconcile logic into a **provider-agnostic
core** "for Zendesk/Asana reuse" — this PRD spends that investment.

**Who has the problem:** self-hosting operators (CS leads, PMs, support engineers) who route feedback
into Asana and want feedback status to reflect reality without manual double-entry.

**Evidence it's real:** Asana slice 1's own deferred-v2 list explicitly names "inbound status-sync
back to Rereflect" (`DEV-TRACKING.md:210`, `AI-TRACKING.md:60`). The recommendation that spawned this
work (`rereflect-next`, 2026-07-12) ranked it the highest-leverage unblocked follow-on precisely
because the reusable spine already exists.

## Goals & Success Metrics

**Goal:** When an operator opts in, a completed Asana task automatically moves its linked feedback
item to `resolved` (or the operator's mapped status), with a visible, auditable timeline event —
matching Jira's behavior exactly.

**Success criteria (testable):**
- With sync enabled, a task that becomes `completed=true` drives its linked feedback to the mapped
  status within one poll cycle, emitting exactly one `status_changed` timeline event tagged
  `source=asana`.
- With sync **disabled** (the default), no feedback status ever changes from Asana — byte-for-byte
  no behavioral change for orgs that don't opt in.
- First poll after enabling **seeds** current task state without moving any feedback (no retroactive
  bulk backfill).
- A feedback linked to multiple Asana tasks resolves only when the **most-advanced** task category
  wins (no regression when one of several tasks is reopened).
- Parity test suite green across backend, worker, frontend (mirror the Jira status-sync counts).

**Non-metric goal:** no new moat claims or hype — this is plumbing parity, described honestly.

## User Personas & Scenarios

- **CS lead (opt-in operator):** connects Asana, flips "Status sync" on, optionally remaps
  `completed → closed`. Files feedback into Asana; sees feedback auto-resolve when engineering closes
  the task. Uses "Sync now" to force an immediate reconcile before a standup.
- **PM (read-only beneficiary):** sees the feedback item flip to resolved with an Asana-sourced
  timeline entry, so the audit trail explains *why* it moved.
- **Operator who never opts in:** unaffected — default off, zero new polling, zero status changes.

## Requirements

### Must-have (slice 1)
1. **Per-org opt-in, off by default.** `AsanaIntegration.status_sync_enabled` (Boolean, default
   False, server_default false). No polling and no status changes unless enabled.
2. **Poll-first Celery beat.** `sync-asana-status-every-15-min` (900 s) fan-out task iterates orgs
   where `is_active AND status_sync_enabled`, enqueues a retryable per-org task.
3. **Completion → category adapter.** Asana task `completed=true → "done"`, `completed=false → "new"`.
   Feed the **existing provider-agnostic `status_sync_core.py`** unchanged.
4. **Bidirectional reconcile (mirror Jira).** A reopen (`completed` true→false) reverts a
   sync-driven feedback back toward `new`/`in_review` via the core's `most_advanced` +
   `decide_link_update`. Only feedback whose current status matches its prior sync-driven value is
   affected — `apply_status_change_worker` no-ops when the target equals the current status.
5. **Non-destructive first-poll seed.** `stored_category IS NULL` → record task state only, never
   move feedback (reuse `decide_link_update`'s `seed` action).
6. **Per-org `status_mapping` override.** Reuse Jira's `{category_key: rereflect_status}` JSON,
   default `{done: resolved, new: new}`. Validated (422 on bad keys/values). Operator can remap e.g.
   `{done: closed}`.
7. **Audited apply.** Each applied change emits one `FeedbackWorkflowEvent(event_type="status_changed",
   old_value, new_value, metadata={"source": "asana", "asana_task_gid": …, "asana_completed": …})`.
8. **Manual "Sync now."** `POST /api/v1/integrations/asana/sync` (202, enqueues the per-org task;
   400 if no active integration; 502 on broker/dispatch failure). Requires admin/owner.
9. **Toggle + mapping route.** `PATCH /api/v1/integrations/asana/status-sync` (admin/owner) toggles
   `status_sync_enabled` and sets validated `status_mapping`.
10. **Status surfacing.** `GET /api/v1/integrations/asana/status` extended with `status_sync_enabled`
    and `last_status_synced_at` (= `MAX(FeedbackAsanaTask.last_status_synced_at)` for the org).
11. **Rate-limit safety.** Worker Asana client honors `Retry-After` on 429 and raises a transient
    error the Celery task retries on (the current backend `AsanaClient` lacks this).
12. **Frontend parity.** `AsanaStatusSyncCard` (copy of `JiraStatusSyncCard`) on the Asana settings
    detail page: toggle, last-synced/last-error indicator, "Sync now" button — admin/owner only.
13. **Auth-error resilience.** An Asana `401/403` during sync records `last_sync_status`/`last_error`
    without disconnecting the integration (mirror Jira's `JiraAuthError` handling).

### Should-have
- Operator docs in `docs/SELF_HOSTING.md` describing the opt-in, the default mapping, and the
  poll-first (no webhook) behavior.
- `last_sync_status` reflects `success` / `error` / `retrying` like Jira.

### Nice-to-have (explicitly deferred to v2)
- Section-name / custom-field → `indeterminate` (`in_review`) mapping (gives Asana a true
  intermediate state).
- Real-time Asana webhook path (poll-first only in slice 1).
- Batch fetch (Asana has no JQL `in(...)`; slice 1 does one GET per linked task).
- Outbound `feedback.status_changed` webhook on an Asana-driven change.

## Technical Considerations

**Services changed:** `backend-api` (model columns, migration, routes, status schema), `worker-service`
(entirely new Asana footprint: client, mirror models, sync task, beat entry), `frontend-web` (card +
API client + type). `analysis-engine`: none.

**Reuse (do not rebuild):**
- `services/{backend-api,worker-service}/src/services/status_sync_core.py` — pure reconcile core,
  used **as-is**. Both decisions (bidirectional + status_mapping) were chosen specifically so the core
  needs no change.
- `apply_status_change_worker` (`worker-service/src/tasks/jira_sync.py`) — provider-agnostic body;
  lift to a shared worker helper or copy with `source="asana"` metadata.
- Jira's route/schema/validation patterns (`routes/jira_integration.py`), beat wiring, worker mirror
  model pattern, and `JiraStatusSyncCard.tsx` / `jira.ts` client.

**Multi-tenancy:** every query scoped by `organization_id`; `AsanaIntegration` is org-unique.

**Data model additions (Alembic):**
- `asana_integrations`: `status_sync_enabled` (Boolean, NOT NULL, default False), `status_mapping`
  (JSON, nullable). Reuse existing `last_synced_at` / `last_sync_status` / `last_error`.
- `feedback_asana_tasks`: `asana_completed` (Boolean, nullable), `asana_status_category` (String(20),
  nullable), `last_status_synced_at` (DateTime, nullable).
- One migration, **chained off the verified current single alembic head** (repo has a documented
  multi-head gotcha; the Jira migration already had to correct a stale down_revision). Worker mirror
  models updated in lockstep (no FKs, own Fernet `_decrypt`).

**API contracts (new/changed):**
- `PATCH /api/v1/integrations/asana/status-sync` → `{enabled: bool, status_mapping?: {str: str}}` →
  `AsanaStatusResponse`. 404 if no integration; 422 on invalid mapping.
- `POST /api/v1/integrations/asana/sync` → 202 `{status: "queued"}`; 400 no active integration; 502
  broker failure.
- `GET /api/v1/integrations/asana/status` → adds `status_sync_enabled`, `last_status_synced_at`.

**New Asana client method (both backend and worker copies):**
`get_task(task_gid) -> {completed, completed_at, memberships}` via
`GET /tasks/{gid}?opt_fields=completed,completed_at,memberships.section.name`. Worker copy adds
`Retry-After` handling. Fixed host `app.asana.com` invariant preserved.

**Non-functional:** CPU-only, no new heavy deps. One GET per linked task per poll — acceptable for
self-hosted volumes; throttle + `Retry-After` prevent hammering. Default-off means zero cost for
non-adopters.

## Risks & Open Questions

- **Reopen tug (accepted):** bidirectional means a manual Asana reopen can pull a feedback back to
  `new`. Chosen for Jira parity; bounded because `apply_status_change_worker` only acts when the
  target differs from the current status and the reconcile compares against the stored sync category.
  *Mitigation:* clear timeline event (`source=asana`) so the revert is auditable, and docs call it out.
- **N-GET fan-out:** no batch endpoint; large orgs poll many single GETs. *Mitigation:* 15-min cadence,
  `Retry-After` throttle, per-org isolation (one org's failure doesn't abort the batch). A hard cap is
  **out of scope** for slice 1 — flag if volumes prove problematic.
- **Inert `indeterminate`:** the core's `DEFAULT_CATEGORY_MAP` has `indeterminate→in_review`, which
  Asana never emits in slice 1. Harmless, but operator docs/UI must not imply Asana has an in-between
  state.
- **Alembic head:** must verify the current single head at plan time and chain correctly.
- **Worker Fernet key:** worker decrypts the PAT with its own `_decrypt` reading `LLM_ENCRYPTION_KEY`
  (can't import backend). Missing key → error, no retry (mirror Jira R6).

## Out of Scope
- Section / custom-field intermediate mapping (v2).
- Real-time Asana webhooks (poll-first only).
- Batch status fetch.
- Outbound webhook on Asana-driven status change.
- Any change to Asana **outbound** task creation (unchanged).
- Zendesk inbound status-sync (separate future feature; same core).
