# Aspect: writeback-config-api (backend + worker model mirror)

**Slice of:** crm-writeback PRD · **Services:** `services/backend-api` (+ `services/worker-service` mirror)
**Depends on:** nothing. **Blocks:** writeback-task-trigger, writeback-ui.

## Problem slice / outcome

Persist the per-org writeback opt-in + field name + status, and expose an API to configure and
read it. This is the config/state backbone the task and UI build on.

## In scope

- **Schema (Alembic migration + model, both `HubSpotIntegration` mirrors):**
  - `writeback_enabled: Boolean` default `False`, `server_default` false, not null.
  - `writeback_field_name: String | None` (nullable).
  - `last_writeback_at: DateTime | None`, `last_writeback_status: String | None`, `last_writeback_error: Text | None`, `contacts_written: Integer` default 0.
  - On `crm_enrichment` (both mirrors): `last_written_health_score: Integer | None`, `last_health_written_at: DateTime | None` (idempotency memory for the task).
  - **Both** the backend model and the worker mirror get the columns (the CI column-parity test asserts they match).
- **API (extend `/api/v1/integrations/hubspot` router, admin/owner only):**
  - `PATCH /writeback` — body `{ enabled: bool, field_name: str | None }`. When `enabled=true`: require a `field_name`, validate via the write-client's `get_contact_property_def` (exists + `number` type + writable). On validation failure return `400`/`422` with a clear message and **do not** set `enabled=true`.
  - `GET /status` — extend the existing response with `writeback_enabled`, `writeback_field_name`, `last_writeback_at`, `last_writeback_status`, `last_writeback_error`, `contacts_written`.
  - (should-have S1) `POST /writeback/test` — run the field validation on demand, return ok / reason.

## Out of scope

- The push task itself; the trigger hook; any UI. Salesforce config.

## Acceptance criteria (testable)

- Migration upgrades and downgrades cleanly; existing HubSpot rows get `writeback_enabled=false`.
- Column-parity test passes (backend ↔ worker mirror) for both `HubSpotIntegration` and `crm_enrichment`.
- `PATCH /writeback {enabled:true}` with a missing/wrong-type/read-only field → 4xx, integration stays `writeback_enabled=false`.
- `PATCH /writeback {enabled:true, field_name: <valid number prop>}` → 200, persisted; `GET /status` reflects it.
- Route rejects non-admin/owner (mirror existing gating tests).

## Notes

Config on `HubSpotIntegration` mirrors the existing `arr_property_name` precedent. Validation
reuses the worker write-client method — if backend cannot import the worker client, add a thin
backend-side httpx `GET /crm/v3/properties/contacts/{name}` (mirrors `_validate_hubspot_token`).
tech-plan resolves which side owns validation.
