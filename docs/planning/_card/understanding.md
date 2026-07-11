# Phase 2 — Deep-dig understanding: jira-status-sync

Grounded in three read-only dig agents. All refs are primary-checkout `file:line`.

## What the feature really is
Close the Jira integration loop: the outbound slice (shipped 2026-07-05) only *creates* Jira
issues from feedback. When that Jira issue later moves (e.g. → Done), the linked Rereflect
feedback item's `workflow_status` should follow. **Poll-first** (self-host is often behind NAT;
webhook is optional v2).

## The exact mirror that already exists (Linear)
`services/backend-api/src/api/routes/linear_webhook.py` does inbound status-sync **via webhook**:
- looks up `FeedbackLinearIssue` by `linear_issue_id` (lines 124-138),
- maps by a DB table `LinearStatusMapping` keyed on **`linear_status_type`** (backlog/unstarted/
  started/completed/canceled) → `rereflect_status` (lines 141-177),
- writes `feedback.workflow_status` **directly** (line 176) — does NOT call `apply_status_change`,
  emits a `linear_status_changed` timeline event (line 184), fires **no** outbound webhook.

**Design lesson:** map by Jira **`statusCategory`** (`new` / `indeterminate` / `done` — the 3
Jira category keys), NOT brittle free-text status names, exactly as Linear maps by *type*.

## Ground truth: workflow_status
- `services/backend-api/src/models/feedback.py:65` — `workflow_status String(50)` default `"new"`,
  not a DB enum.
- Valid values (route-enforced): **`new`, `in_review`, `resolved`, `closed`**
  (`api/routes/workflow.py:29`; `api/routes/public_api.py:322`). → **brief's `in_progress` is
  invalid; use `in_review`.**
- Shared helper `apply_status_change(db, feedbacks, new_status, *, organization_id, actor_id,
  actor_label, resolution_note)` — `services/workflow_service.py:15-50`. No-op on same value;
  mutates status; emits ONE `status_changed` `FeedbackWorkflowEvent`; returns changed items.
  Caller drives commit + cache-invalidate + `dispatch_status_webhooks` (see `workflow.py:160-197`).

## Zero-config default mapping (corrected)
| Jira statusCategory (key) | → workflow_status |
|---|---|
| `done` | `resolved` |
| `indeterminate` | `in_review` |
| `new` (To Do) | `new` |
`closed` is not auto-targeted by the default (reserve for explicit user mapping).

## Existing Jira plumbing to REUSE (dig agent 1)
- `JiraIntegration` (`models/jira_integration.py:17-33`): one row/org, `site_url`, `email`,
  Fernet `api_token`, `is_active`, `last_synced_at`, `last_sync_status`, `last_error`.
- `FeedbackJiraIssue` (`:44-62`): `feedback_id`, `jira_issue_id`, `jira_issue_key`,
  `jira_issue_url`, `jira_issue_title` — **no status field, no synced-at.**
- `services/jira_client.py`: Basic-auth httpx client, error taxonomy (`JiraAuthError` 401/403,
  `JiraTransientError` 429/5xx, `JiraNotFoundError` 404), `_get`/`_post`, `validate/get_projects/
  get_issue_types/create_issue`. **No `get_issue`/JQL `search` method — must add.**
- Encryption: `utils/encryption.py` `encrypt_api_key`/`decrypt_api_key` (`LLM_ENCRYPTION_KEY`).
- Timeline: `_add_timeline_entry` (`routes/jira_integration.py:258-275`) writes `FeedbackWorkflowEvent`;
  existing event strings: `jira_issue_created`, `asana_task_created`, `linear_status_changed`.

## Worker/beat pattern to CLONE (dig agent 3) — Zendesk poller
**The worker does NOT import backend-api** — it mirrors models + duplicates clients against the
shared DB. So we add a worker-side `JiraIntegration` mirror + `services/worker-service/src/clients/
jira.py` + `services/worker-service/src/tasks/jira_sync.py`.
- Two-task fan-out: `sync_all_jira` (query active integrations, `sync_jira_org.delay(id)` each,
  per-org try/except) + `sync_jira_org` (`@shared_task(bind=True, max_retries=3,
  default_retry_delay=30)`) — mirror `tasks/zendesk_sync.py:339-385`.
- 429/`Retry-After` throttle in the client `_handle_response` → `JiraTransientError`; task
  `raise self.retry(exc)` (mirror `clients/zendesk.py:102-125`, `zendesk_sync.py:296-314`).
- Cursor: reuse `integ.last_synced_at`; only act when Jira category changed vs stored `jira_status`
  → natural guard against clobbering manual edits + against re-writing every poll.
- Terminal status durability: write `last_sync_status`/`last_error` in a fresh session on failure
  (`zendesk_sync.py:97-133`).
- Beat: add `"src.tasks.jira_sync"` to `include` (`celery_app.py:36-56`) + a beat entry (mirror
  Zendesk `900.0` = 15 min, `celery_app.py:231-234`).
- Manual "sync now": backend `POST /api/v1/integrations/jira/sync` → `send_task(
  "src.tasks.jira_sync.sync_jira_org", args=[integ.id])` (mirror `zendesk_integration.py:516-565`).

## Net new work (slice 1)
1. `feedback_jira_issues`: add `jira_status` (+ `jira_status_category`) + `last_status_synced_at`
   — Alembic migration + backend model + worker mirror.
2. Status-mapping store: JSON column on `jira_integrations` (slice-1 simple) with zero-config
   default in code — OR a `JiraStatusMapping` table mirroring Linear (more consistent; costs a
   table). **PRD decision.**
3. Poll enablement flag: on-by-default vs opt-in `status_sync_enabled` (off by default, CRM/usage
   precedent, since it mutates `workflow_status`). **PRD decision (product).**
4. `JiraClient.get_issue(key)` / `search_issues(jql)` (batch by `issue in (...)`), backend + worker.
5. Worker poller task + beat + manual `/sync` route.
6. Apply status: route through `apply_status_change` (dedup + cache + subscriber webhooks, stamp
   `actor_label="jira-sync"`) vs Linear-style silent direct-write + `jira_status_synced` event.
   **PRD decision.** No echo-loop risk today (outbound Jira never pushes status back).

## Reconcile/mapping core → later Zendesk/Asana reuse
Factor a provider-agnostic "given (external status category, mapping) → target workflow_status,
apply + record" core so Zendesk/Asana inbound-sync (both deferred v2) can adopt it.
