# Aspect: poll-task

**Slug:** `zendesk-status-sync` · **Aspect dir:** `poll-task`
**Sequencing:** after reconcile-core-and-model + client-batch-status.

## Problem slice & outcome

The 15-minute poll-first reconcile: fan out per opted-in org, batch-fetch linked tickets' statuses,
reconcile via the shared core, and apply changes with a source-tagged timeline event. Mirrors
`services/worker-service/src/tasks/jira_sync.py`.

## In scope
1. New worker task module `src/tasks/zendesk_status_sync.py`:
   - `sync_all_zendesk_status()` — query `ZendeskIntegration` where `is_active AND status_sync_enabled`, `sync_zendesk_status_org.delay(id)` per org (per-org try/except).
   - `sync_zendesk_status_org(self, integration_id)` — `bind=True, max_retries=3, default_retry_delay=30`; opens session, calls `_sync_zendesk_status_org_body`; `ZendeskTransientError` → persist `retrying` in fresh session → `self.retry`.
   - `_sync_zendesk_status_org_body(integration_id, db, client=None)` — injectable client (test seam, no HTTP/Celery). Flow:
     - Guards: not_found / inactive / disabled (re-check `status_sync_enabled`).
     - Decrypt token (Fernet, `LLM_ENCRYPTION_KEY`); missing key → `{"status":"error","reason":"missing_encryption_key"}`, no retry.
     - Poll set: `feedback WHERE source='zendesk' AND source_external_id IS NOT NULL AND organization_id=:org`. Map `source_external_id → feedback`.
     - Chunk ticket ids, `client.show_many(chunk)` → `{ticket_id: status}`. Per-run page cap (mirror ingest `PER_RUN_PAGE_CAP`) so huge backlogs span several beats.
     - Per feedback: read `FeedbackZendeskSync` row → `decide_update(fetched, stored)`. `seed`→upsert sidecar (`last_ticket_status`, `last_status_synced_at`), NO apply. `noop`→skip. `changed`→`resolve_target_status(fetched, integ.status_mapping)`; if target and ≠ current `workflow_status` → apply + upsert sidecar.
     - Apply via `apply_zendesk_status_worker(db, feedback, target, organization_id, ticket_id, zendesk_status)` — one `FeedbackWorkflowEvent(event_type="status_changed", actor_id=None, old/new, metadata={"source":"zendesk","zendesk_status":…,"zendesk_ticket_id":…})`; no-op if already equal; **no outbound webhook** (deferred).
     - Markers: `integ.last_status_synced_at=utcnow()`, `last_status_sync_error=None` on success.
   - Throttle/auth: `ZendeskTransientError` propagates → retry; `ZendeskAuthError` → record `last_status_sync_error`, no disconnect, no retry.
2. **Beat + include** in `src/celery_app.py`: register `src.tasks.zendesk_status_sync` in `include`; add `sync-zendesk-status-every-15-min` (`schedule: 900.0`).
3. Reuse the shared reconcile function + apply-writer helper (extract writer so webhook aspect reuses it).

## Out of scope
- Client `show_many` (its own aspect), routes, webhook, frontend.

## Acceptance criteria (testable, injected fake client — no HTTP)
- First poll over N linked tickets (no sidecar rows) → all `seed`: N sidecar rows written, **zero** `status_changed` events, zero `workflow_status` changes.
- Second poll, one ticket now `solved` → that feedback → `resolved`, exactly one `status_changed` event (`metadata.source=="zendesk"`), sidecar updated; others noop.
- "Poll twice, second is a no-op" — a poll after no ticket change produces zero new events.
- Org with `status_sync_enabled=false` → skipped by `sync_all_zendesk_status`.
- 429 from client → `ZendeskTransientError` → `self.retry` called; `last_status_sync_error` records `retrying`.
- 401 → `last_status_sync_error` set, integration still `is_active`, no retry.
- `resolve_target_status` returns None (unknown/overridden-out status) → no apply, sidecar still records last_ticket_status.

## Dependencies & sequencing
- Needs: reconcile-core-and-model (module + models + migration), client-batch-status (`show_many`).
- Blocks: nothing (webhook reuses the extracted apply-writer + reconcile).

## Open questions / risks
- Extract `apply_zendesk_status_worker` + the per-feedback reconcile step into a helper importable by the webhook receiver (which runs in backend-api, not worker) — see webhook aspect for the cross-service note; may need a backend mirror of the apply-writer (backend already has `apply_status_change` in `workflow_service.py`).
