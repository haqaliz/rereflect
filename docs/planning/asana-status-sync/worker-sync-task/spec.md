# Aspect: worker-sync-task

## Problem slice & outcome
The heart of the feature: a poll-first Celery task that reconciles Asana task completion onto linked
feedback, reusing the pure `status_sync_core.py`. Mirror `worker-service/src/tasks/jira_sync.py`.

## In scope
`services/worker-service/src/tasks/asana_sync.py`:
- **`sync_all_asana()`** — `@shared_task(name="src.tasks.asana_sync.sync_all_asana")`. Query worker
  mirror `AsanaIntegration` where `is_active AND status_sync_enabled`; `sync_asana_org.delay(id)` per
  org inside per-org try/except (one org's failure never aborts the batch).
- **`sync_asana_org(self, integration_id)`** — `@shared_task(bind=True, max_retries=3,
  default_retry_delay=30, name="src.tasks.asana_sync.sync_asana_org")`. Thin wrapper: call
  `_sync_asana_org_body`; on `AsanaTransientError` persist terminal `"retrying"` status in a fresh
  session then `raise self.retry(exc=exc)`.
- **`_sync_asana_org_body(integration_id, db, client=None)`** — injectable client for tests. Iterate
  the org's `FeedbackAsanaTask` links; for each, `client.get_task(gid)` → `asana_category(completed)`
  → `decide_link_update(fetched_category, fetched_name, stored_category)` from `status_sync_core`.
  On `seed`: write `asana_completed`/`asana_status_category`/`last_status_synced_at` only (no feedback
  change). On `changed`: update link state and collect the feedback for status resolution. Per feedback
  with ≥1 changed link, compute `most_advanced` of its links' categories → `resolve_target_status(cat,
  status_mapping)` → `apply_status_change_worker(...)`.
- **`apply_status_change_worker` reuse** — either import/lift the existing helper from `jira_sync.py`
  into a shared worker module, or copy it; the Asana caller supplies
  `metadata={"source": "asana", "asana_task_gid": …, "asana_completed": …}`.
- **Error taxonomy (mirror Jira):** missing `LLM_ENCRYPTION_KEY` → `{"status":"error",
  "reason":"missing_encryption_key"}`, no retry. `AsanaAuthError` → record `last_sync_status`/
  `last_error`, do NOT disconnect. 404 on a task → leave that link unchanged.
- **Celery wiring** (`services/worker-service/src/celery_app.py`): add `"src.tasks.asana_sync"` to
  `include`; add beat entry `"sync-asana-status-every-15-min"` → `sync_all_asana`, `"schedule": 900.0`.

## Out of scope
- The `get_task` client itself (asana-client-get-task aspect) — consumed here via injection.
- Model columns (model-migrations aspect).
- Outbound webhook dispatch on change (v2) — write only the timeline event + status change.

## Acceptance criteria (testable) — mirror `test_jira_sync_task.py`
- `_sync_asana_org_body` with an injected fake client: seed (NULL→state, no feedback change), noop
  (same category), changed (done→resolved applied), reopen (done→new reverts), most-advanced across
  multiple links, auth-error records without disconnect, missing-key returns error no-retry, transient
  triggers retry.
- Exactly one `FeedbackWorkflowEvent(status_changed, metadata source=asana)` per applied change;
  no-op when target == current status.
- `sync_all_asana` only fans out orgs with `status_sync_enabled=True`.
- Beat entry + `include` present.

## Dependencies & sequencing
- Depends on **model-migrations** (worker mirror columns) and **asana-client-get-task** (worker client).
- Reuses `status_sync_core.py` **unchanged** (verify no core edits needed).

## Open questions / risks
- Decide: lift `apply_status_change_worker` to a shared module vs copy. Prefer lift to avoid drift, but
  keep the diff small and characterization-locked so Jira behavior is byte-identical.
