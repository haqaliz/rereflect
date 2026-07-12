# Aspect: backend-routes

**Slug:** `zendesk-status-sync` · **Aspect dir:** `backend-routes`
**Sequencing:** after reconcile-core-and-model (needs columns + validation vocab). Parallel with poll/webhook.

## Problem slice & outcome

Operator control surface: toggle status-sync on/off (+ set the per-org mapping override), trigger a
manual "Sync now", and expose sync state on `GET /status`. Mirrors
`services/backend-api/src/api/routes/jira_integration.py` (L546 toggle, L595 sync).

## In scope
1. In `services/backend-api/src/api/routes/zendesk_integration.py` (all `Depends(require_admin_or_owner)`):
   - `PATCH /status-sync` → `ZendeskStatusSyncUpdateRequest {enabled: bool, status_mapping?: Dict[str,str]}`.
     - 404 if no integration row. `_validate_status_mapping`: keys ∈ `ZENDESK_STATUSES`, values ∈ `VALID_STATUSES` (else 422). Set `status_sync_enabled` (+ optional `status_mapping`), commit, return `ZendeskStatusResponse`.
   - `POST /status-sync/sync` → 202 `{status:"queued"}`. Requires active integration (400 if none). Dispatch `_get_celery_app().send_task("src.tasks.zendesk_status_sync.sync_zendesk_status_org", args=[integ.id])`; broker failure → 502 (never 500). (Distinct path from the existing ingestion `POST /sync`.)
   - Extend `ZendeskStatusResponse` + `GET /status` builder to include `status_sync_enabled`, `status_mapping`, `last_status_synced_at`, `last_status_sync_error`.

## Out of scope
- Worker task impl, webhook, frontend, migration/model (foundation aspect).

## Acceptance criteria (testable, FastAPI TestClient + fake celery app)
- `PATCH /status-sync {enabled:true}` on a connected org → 200, `status_sync_enabled=true` in response + persisted.
- `PATCH` with `status_mapping={"solved":"resolved"}` → persisted; `{"bogus":"resolved"}` → 422; `{"solved":"bogus"}` → 422.
- `PATCH` when no integration → 404.
- Non-admin (member) → 403 on `PATCH` and on `POST /status-sync/sync`.
- `POST /status-sync/sync` active org → 202 `{status:"queued"}`, `send_task` called with the status task name + `[integ.id]`.
- `POST /status-sync/sync` no active integration → 400; broker raises → 502.
- `GET /status` returns the 4 new fields; ingestion fields (`last_synced_at`/`last_sync_status`/`last_error`) unchanged.

## Dependencies & sequencing
- Needs: reconcile-core-and-model (columns + `ZENDESK_STATUSES`/`VALID_STATUSES`). Task-name string couples to poll-task (fine to define ahead — dispatch is by string).
- Blocks: frontend (consumes the endpoints + response shape).

## Open questions / risks
- Keep the new manual trigger clearly separated from the existing ingestion `POST /sync` (different sub-path `/status-sync/sync`) to avoid operator confusion — the frontend labels them distinctly ("Sync tickets" vs "Sync statuses").
