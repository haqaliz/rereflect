# Aspect Spec — push-task-trigger

**Feature:** `salesforce-crm-writeback` · **Aspect:** `push-task-trigger`
**Deps:** `model-migrations`, `salesforce-write-client`

## Problem slice / outcome

When a customer's health score changes, the score is pushed to their matched Salesforce Contact —
idempotently, safely, and only when Salesforce writeback is enabled — without disturbing the HubSpot
path. Also persist the matched Contact Id during sync so the push has a target.

## In-scope

1. **Sync persists the Contact Id** — in `services/worker-service/src/tasks/salesforce_sync.py`
   `_upsert_enrichment` (`:123-161`), also write `salesforce_contact_id = contact["Id"]` for the
   matched Contact. On duplicate-email matches, pick **deterministically**: lowest `Id` (M5a).
2. **Push task (`services/worker-service/src/tasks/salesforce_writeback.py`, new)** —
   `push_health_to_salesforce(self, org_id, customer_email)` (`@shared_task(bind=True, max_retries=3,
   default_retry_delay=30, name="src.tasks.salesforce_writeback.push_health_to_salesforce")`) + a
   testable `_push_health_to_salesforce_body(...)`, mirroring `hubspot_writeback.py`:
   - **Gating no-ops** → return a reason string: `integration_inactive`, `writeback_disabled`,
     `no_field_name`, `no_enrichment`, `no_contact_id` (after fallback fails), `no_health_row`.
   - **Contact-id resolution:** use `crm_enrichment.salesforce_contact_id`; if null, **re-query by
     email** via `client.list_contacts()`/a targeted SOQL, deterministic pick (lowest Id), and
     persist it back; if still none → `no_contact_id`. On >1 match record
     `last_writeback_error="ambiguous_contact"` (soft) but still write the chosen one.
   - **Idempotency:** compare `health.health_score` to `enrichment.last_written_health_score`
     (equal → `score_unchanged`; `abs(diff) < 2` → `change_too_small`).
   - **Encryption:** worker-local decrypt of `refresh_token` via `LLM_ENCRYPTION_KEY`; missing key →
     record `last_writeback_error="missing_encryption_key"`, no retry.
   - **Write:** `SalesforceClient(...) as c: c.update_contact_field(contact_id, field_name, score)`.
     On success set `enrichment.last_written_health_score`/`last_health_written_at`, integration
     `last_writeback_at`/`last_writeback_status="ok"`/`error=None`, increment `contacts_written`.
   - **Soft-pause** (never `is_active=false`): `missing_write_scope`, `field_not_found`,
     `contact_not_found`, `daily_limit` (`last_writeback_status="deferred: daily_limit"` + retry).
     **Retry** on `SalesforceTransientError`.
   - Register in `services/worker-service/src/celery_app.py` include list.
3. **Generalize the trigger** — extend `_maybe_enqueue_writeback` in
   `services/backend-api/src/services/health_score_service.py:278-326`: keep the HubSpot dispatch
   unchanged; additionally, if an active `SalesforceIntegration` with `writeback_enabled=True` exists,
   `send_task("src.tasks.salesforce_writeback.push_health_to_salesforce", [org_id, customer_email])`.
   Preserve the `abs(new-old) < 2` early-return and the existing-customer-only call site (`:406`).
   Broad try/except-log (never raise). The one-CRM guard means only one provider is ever active.

## Out-of-scope

- Routes/backfill (config-api), client internals (write-client), UI.

## Acceptance criteria (testable)

- `test_salesforce_writeback_task.py` (new): each gating no-op; id-from-enrichment happy path;
  id-null→re-query-by-email fallback (persists id); duplicate-email→deterministic pick +
  `ambiguous_contact`; skip-if-unchanged + change-too-small; soft-pause on scope/not-found/daily_limit
  (no `is_active` flip); transient→retry; missing key→no retry. Client + DB mocked/fixtured.
- `test_health_writeback_enqueue.py` (extend, not break): HubSpot-only org still dispatches exactly the
  HubSpot task; Salesforce-only org (active + writeback_enabled) dispatches the Salesforce task; neither
  fires when disabled or `abs(diff) < 2`.
- Worker↔backend `CrmEnrichment` parity green; read-side characterization tests byte-identical.

## Dependencies / sequencing

After `model-migrations` (columns) + `salesforce-write-client` (client PATCH). Independent of
`writeback-config-api` except both dispatch/consume the same task name (contract: the task name string
must match the backfill helper and the trigger).

## Open questions / risks

- The targeted re-query-by-email SOQL vs reusing `list_contacts()` (which pulls all) — prefer a
  bounded `SELECT Id FROM Contact WHERE Email = :email` for the fallback to avoid a full scan.
- Ensure the backend can import/read `SalesforceIntegration.writeback_enabled` in the trigger the same
  way `hubspot_writeback` reads HubSpot's (lazy import to avoid worker/backend coupling).
