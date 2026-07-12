# Understanding — feat/asana-status-sync (Phase 2 deep dig)

Synthesis of three read-only mapping agents (Jira reconcile core, Asana integration, frontend tiles).

## What the feature really asks

Close the Asana integration loop the way `jira-status-sync` (merged 2026-07-12) closed Jira's:
poll Asana for the completion state of tasks Rereflect created from feedback, and reflect it back
onto the linked feedback item's `workflow_status` — **opt-in per org, off by default**,
non-destructive first-poll seed, one `status_changed` timeline event tagged `source=asana`.

The Jira feature is a **ready-made 7-layer blueprint**; Asana is a near-mechanical mirror. The
only genuinely provider-specific pieces are (a) Asana's status model, (b) the `"source":"asana"`
metadata tags, and (c) the Asana API client (no JQL batch — one GET per task).

## The reusable spine (do NOT rebuild)

- **Pure reconcile core** — `services/{backend-api,worker-service}/src/services/status_sync_core.py`
  (duplicated verbatim; worker can't import backend). Zero-I/O, stdlib-only. Public surface:
  `VALID_STATUSES=("new","in_review","resolved","closed")`, `DEFAULT_CATEGORY_MAP={done:resolved,
  indeterminate:in_review, new:new}`, `CATEGORY_RANK`, `resolve_target_status(category, mapping)`,
  `is_seed()`, `most_advanced(categories)`, `decide_link_update(fetched_cat, fetched_name,
  stored_cat) -> (action, ...)` where action ∈ seed|noop|changed. **Reuse as-is.**
- **Contract an adapter must satisfy:** emit each external item's `{name, category}` where
  `category ∈ {done, indeterminate, new}`. The core does the rest (mapping override, most-advanced,
  seed/noop/changed).
- **`workflow_status`** is a `String(50)` allow-list (`feedback.py:65`), canonical values in
  `workflow.py:29` — provider-agnostic, no change.
- **Worker `apply_status_change_worker(db, feedback, new_status, *, organization_id, actor_label,
  metadata)`** (`worker-service/src/tasks/jira_sync.py:130-179`) — no-ops on same status, writes ONE
  `FeedbackWorkflowEvent(event_type="status_changed", old/new_value, metadata_=...)`. **Source
  tagging is caller-supplied metadata.** Body is fully provider-agnostic → lift to a shared worker
  helper (or copy with `source="asana"`).

## Key design decision — Asana's status model → the 3-bucket vocabulary

Asana has **no `statusCategory`**. A task exposes `completed` (bool) + `memberships[].section`.
**Decision (slice 1):** the Asana adapter maps `completed=true → "done"`, `completed=false → "new"`
— it emits only two of the three category keys, never `indeterminate`. This lets us reuse the
core AND the `status_mapping` override shape **verbatim** (default `{done:resolved, new:new}`).
Section-name / custom-field → `indeterminate` mapping is **deferred to v2**.

## What exists vs what must be built

**Already exists (reuse):**
- `AsanaIntegration` model (`models/asana_integration.py`) — encrypted PAT, org-unique, and already
  carries `last_synced_at` / `last_sync_status` / `last_error` (written today only by the create-task
  error path — reuse for sync status).
- `FeedbackAsanaTask` link (`asana_task_gid`, `feedback_id`, `organization_id`, url, name) — the poll set.
- `AsanaClient` (`services/asana_client.py`) — fixed host `app.asana.com`, Bearer auth, error taxonomy
  (`AsanaError/AuthError/TransientError/NotFoundError`). Backend-only; **no worker footprint at all.**
- Frontend `JiraStatusSyncCard.tsx` + `jira.ts` client — copyable line-for-line.

**Must build (the gap list):**
1. **`AsanaClient.get_task(task_gid)`** → `GET /tasks/{gid}?opt_fields=completed,completed_at,memberships.section.name`
   returning `{completed, completed_at, memberships}`. **No batch** (Asana has no JQL `in(...)`) — one
   GET per gid; add `Retry-After` handling (absent today; worker `JiraClient` sleeps on 429).
2. **`FeedbackAsanaTask` new columns** — `asana_completed` (Bool), `asana_status_category` (String(20)),
   `last_status_synced_at` (DateTime) + migration.
3. **`AsanaIntegration` new columns** — `status_sync_enabled` (Bool, default False, server_default false)
   + `status_mapping` (JSON) + migration (chain off the current single alembic head — VERIFY head first;
   repo has had multi-head issues).
4. **Backend routes** on `routes/asana_integration.py` — `PATCH /api/v1/integrations/asana/status-sync`
   (toggle + validated `status_mapping`, 422 on bad keys/values, `require_admin_or_owner`),
   `POST /api/v1/integrations/asana/sync` (202, enqueue `sync_asana_org`, 502 on broker failure),
   and extend `GET /status` with `status_sync_enabled` + `last_status_synced_at`
   (`MAX(FeedbackAsanaTask.last_status_synced_at)`).
5. **Worker service (all new for Asana)** — worker `AsanaClient` copy under `src/clients/`, worker
   mirror models (`AsanaIntegration` + `FeedbackAsanaTask`, no FKs, own `_decrypt`), `src/tasks/asana_sync.py`
   (`sync_all_asana` fan-out over active + `status_sync_enabled`; `sync_asana_org` retryable;
   `_sync_asana_org_body(integration_id, db, client=None)` injectable), reuse the pure `status_sync_core.py`,
   add `"src.tasks.asana_sync"` to celery `include` + a `sync-asana-status-every-15-min` (900s) beat entry.
6. **Frontend** — new `components/settings/AsanaStatusSyncCard.tsx` (copy of Jira card, jira→asana),
   add `patchAsanaStatusSync` + `triggerAsanaSync` + `AsanaSyncTriggerResponse` to `lib/api/asana.ts`,
   add `status_sync_enabled` + `last_status_synced_at` to `AsanaConnectionStatus` (+ `handleConnect`
   literal), render the card on `settings/integrations/asana/page.tsx` (~line 351, admin/owner only).

## Ambiguities / open questions for the PRD interview
- **Un-completion behavior:** if an Asana task is reopened (`completed` flips true→false), the adapter
  emits `new`, which would move `workflow_status` resolved→new. Jira reflects reopens for parity — do we
  want the same, or should Asana sync be forward-only (done→resolved, never revert)? **Lean: mirror Jira
  (reflect reopen), it falls out of the core for free** — confirm.
- **Poll cadence:** 15 min like Jira/Zendesk (default). Confirm.
- **N-GET fan-out:** no batch endpoint → one GET per linked task. Per-org throttle + Retry-After needed;
  acceptable for self-hosted volumes. Confirm no hard cap needed in slice 1.
- **`status_mapping` keys exposed to operators:** only `done`/`new` are meaningful for Asana in slice 1
  (no `indeterminate`). Validate against that reduced set, or accept all 3 keys for forward-compat?

## Contradiction / risk flags
- The reconcile core's `DEFAULT_CATEGORY_MAP` includes `indeterminate → in_review`; Asana never emits it
  in slice 1, so that entry is inert (harmless). No code change needed, but the operator-facing mapping
  UI/docs should not imply Asana has an intermediate state.
- Repo has a documented multi-alembic-head gotcha — the new migration must chain off the verified current
  single head (the Jira status-sync migration already had to correct a stale down_revision). Verify at plan time.
