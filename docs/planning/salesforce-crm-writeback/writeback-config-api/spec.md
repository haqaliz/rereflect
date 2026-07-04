# Aspect Spec — writeback-config-api

**Feature:** `salesforce-crm-writeback` · **Aspect:** `writeback-config-api`
**Deps:** `model-migrations`, `salesforce-write-client` (validation service)

## Problem slice / outcome

An operator can enable/configure/validate Salesforce writeback and read its status from the app, with
legible errors and a backfill kicked off on enable — mirroring the shipped HubSpot writeback routes.

## In-scope (all under `/api/v1/integrations/salesforce`, `require_admin_or_owner` + `require_feature("salesforce_integration")` no-op)

1. **`PATCH /writeback`** — Pydantic `SalesforceWritebackRequest{enabled: bool, field_name: Optional[str]}`
   → `SalesforceWritebackResponse{writeback_enabled, writeback_field_name, last_writeback_at,
   last_writeback_status, last_writeback_error, contacts_written}`. Behavior mirrors
   `hubspot_integration.py:396-456`:
   - 404 if no active `SalesforceIntegration`.
   - Enabling with empty `field_name` → **422**.
   - Enabling: call `validate_writeback_field(refresh_token, instance_url, field_name)`; on failure
     raise **HTTP 400** `detail={"reason", "message"}` and leave `writeback_enabled=False`. On success
     set `writeback_enabled=True`, `writeback_field_name`, clear `last_writeback_status/error`, then
     call the inline backfill helper.
   - Disabling: set `writeback_enabled=False` only (leave field name).
2. **`POST /writeback/test`** — `SalesforceWritebackTestRequest{field_name: str}` →
   `SalesforceWritebackTestResponse{ok: bool, reason: Optional[str]}` (calls the validation service).
3. **`GET /status`** — extend the existing status response with the 6 writeback fields
   (mirror `hubspot_integration.py:303-308`).
4. **Backfill-on-enable helper** — `_enqueue_backfill_writeback(org_id, db)` mirroring
   `hubspot_integration.py:459-512`: query `CrmEnrichment` rows for the org with `provider='salesforce'`
   (skip rows with no resolvable contact — i.e. leave the id-fallback to the task), capped at
   `WRITEBACK_BACKFILL_CAP = 500`, `send_task("src.tasks.salesforce_writeback.push_health_to_salesforce",
   [org_id, row.customer_email])`. Never raises (log + swallow).
5. **Token access** — decrypt the refresh token via the existing helper used by the read routes.

## Out-of-scope

- The Celery task body + trigger generalization (push-task aspect).
- The client PATCH/describe + validation service internals (write-client aspect) — consumed here.
- Frontend (ui aspect).

## Acceptance criteria (testable)

- `test_salesforce_writeback_routes.py` (new): enable-with-valid-field → 200, `writeback_enabled=True`,
  backfill enqueued; enable-without-field → 422; enable-with-invalid-field → 400 `{reason, message}` and
  integration stays disabled; disable → 200 `writeback_enabled=False`; 404 when not connected; RBAC
  (member forbidden). Validation service + `send_task` mocked.
- `GET /status` returns the writeback fields (defaults when never configured).
- Multi-tenancy: all queries scoped by `organization_id` from JWT.

## Dependencies / sequencing

Starts after `model-migrations` (columns) and `salesforce-write-client` (validation service) land.
Its endpoint contracts are consumed by `writeback-ui`.

## Open questions / risks

- Confirm the exact decrypt helper + refresh-token access pattern used by the shipped Salesforce
  routes to avoid duplicating token logic.
- Backfill cap reuse (500) — confirm parity with HubSpot constant naming.
