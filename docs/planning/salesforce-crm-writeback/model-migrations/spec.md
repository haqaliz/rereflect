# Aspect Spec — model-migrations

**Feature:** `salesforce-crm-writeback` · **Aspect:** `model-migrations` · **Deps:** none (foundation)

## Problem slice / outcome

The Salesforce writeback config and the matched-Contact target have nowhere to live. Add the schema so
every downstream aspect (config-api, push-task, sync) has stable columns to read/write, without
regressing the CRM read layer.

## In-scope

1. **`SalesforceIntegration` (`services/backend-api/src/models/salesforce_integration.py`)** — add 6
   columns mirroring `hubspot_integration.py:38-44`:
   - `writeback_enabled` `Boolean NOT NULL default False server_default "false"`
   - `writeback_field_name` `String(255) nullable`
   - `last_writeback_at` `DateTime nullable`
   - `last_writeback_status` `String(50) nullable`
   - `last_writeback_error` `Text nullable`
   - `contacts_written` `Integer NOT NULL default 0 server_default "0"`
2. **`CrmEnrichment` (`services/backend-api/src/models/crm_enrichment.py`)** — add
   `salesforce_contact_id` `String(100) nullable` (next to the `hubspot_*_id` columns at `:53-55`).
   Reuse existing `last_written_health_score` / `last_health_written_at` (`:59-60`) — do NOT add new
   idempotency columns.
3. **Worker model mirror (`services/worker-service/src/models/`)** — mirror `salesforce_contact_id`
   on the worker `CrmEnrichment` so the column-parity test stays green. (The worker does not need the
   `SalesforceIntegration` writeback columns unless the worker model mirrors that table — check and
   mirror only if a worker `SalesforceIntegration` model exists.)
4. **One Alembic migration** chained off the current head, adding all of the above. Follow the
   precedent `alembic/versions/9f56f9a4f999_add_salesforce_integrations_table.py`. Use
   `server_default` for the NOT NULL columns so existing rows backfill cleanly.

## Out-of-scope

- Any route, task, client, or UI logic (later aspects).
- Touching `crm_enrichment`'s read fields, `provider`, or `_compute_crm_component`.

## Acceptance criteria (testable)

- `test_salesforce_model.py` (extend): a `SalesforceIntegration` row defaults `writeback_enabled=False`
  and `contacts_written=0`; the 6 columns are settable/readable.
- New/extended model test: `CrmEnrichment.salesforce_contact_id` is settable and defaults null.
- Backend↔worker `CrmEnrichment` column-parity test stays green (mirror added).
- `test_crm_provider_generalization.py` stays **byte-identical** (health_score==47, crm_component≈25.0,
  the 7 crm_* serializer values) — the migration/columns must not alter health or serializer output.
- `alembic upgrade head` then `alembic downgrade -1` round-trips cleanly on a scratch DB.

## Dependencies / sequencing

First aspect. `writeback-config-api` and `push-task-trigger` both depend on this. Ship + merge (or at
least land on-branch) before those start to avoid migration races.

## Open questions / risks

- Confirm whether a worker-side `SalesforceIntegration` model exists (dig found the worker mirrors
  `CrmEnrichment`; the writeback config is read by the backend trigger, not the worker task — the task
  reads `SalesforceIntegration` via the backend model import path used by `hubspot_writeback.py`).
  Mirror only what the parity tests require.
