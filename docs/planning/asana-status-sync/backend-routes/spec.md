# Aspect: backend-routes

## Problem slice & outcome
Operator controls: toggle status-sync + set mapping, trigger a manual sync, and see sync state.
Mirror the three Jira endpoints in `routes/jira_integration.py`.

## In scope
`services/backend-api/src/api/routes/asana_integration.py` (+ Pydantic schemas), all
`Depends(require_admin_or_owner)`:
- **`PATCH /api/v1/integrations/asana/status-sync`** — request `{enabled: bool, status_mapping?:
  {str: str}}`, response `AsanaStatusResponse`. 404 if no integration row. Validate `status_mapping`
  against category keys `{new, done}` (plus `indeterminate` accepted for forward-compat but inert) and
  values `VALID_WORKFLOW_STATUSES = {new, in_review, resolved, closed}` → **422** on bad key/value.
- **`POST /api/v1/integrations/asana/sync`** — `status_code=202`, response `{status: "queued"}`.
  Requires an **active** integration (400 if none). Enqueue via
  `send_task("src.tasks.asana_sync.sync_asana_org", args=[integ.id])`; broker/dispatch failure → **502**
  (never 500).
- **`GET /api/v1/integrations/asana/status`** — extend `AsanaStatusResponse` with
  `status_sync_enabled: bool = False` and `last_status_synced_at` (computed as
  `MAX(FeedbackAsanaTask.last_status_synced_at)` for the org). Never return the token.

## Out of scope
- The worker task (worker-sync-task aspect) — only enqueued here.
- Any change to existing connect/disconnect/test/create-task routes.

## Acceptance criteria (testable) — mirror `test_jira_status_sync_routes.py`
- PATCH toggles `status_sync_enabled`, persists `status_mapping`; 404 when no integration; 422 on
  invalid mapping key or value; non-admin → 403.
- POST returns 202 `{status:"queued"}` with active integration; 400 without; 502 when the celery
  dispatch raises (patched).
- GET returns the two new fields; token/`api_token` never present in any response.

## Dependencies & sequencing
- Depends on **model-migrations** (columns).
- Independent of the worker task at test time (dispatch is patched/mocked).
- Frontend depends on the response shapes finalized here.

## Open questions / risks
- Keep `_validate_status_mapping` semantics identical to Jira's for parity; document that only
  `done`/`new` keys are meaningful for Asana.
