# Aspect Spec — hubspot-sync

**Parent PRD:** `../prd.md` · **Slug:** `hubspot-crm-enrichment`

## Problem slice & user outcome

After connecting, the operator's HubSpot Contacts/Companies/Deals are pulled,
matched to Rereflect customers by email, and written to a per-customer enrichment
store — on demand ("Sync now") and daily. This makes the data available for the
profile card, timeline, and health component.

## In scope

- **HubSpot client** (worker `src/clients/hubspot.py` or `src/adapters/hubspot.py`)
  using `httpx.Client`, `Authorization: Bearer <decrypted token>`:
  - List contacts (paginated) with properties `email`, `lifecyclestage`,
    `associatedcompanyid`.
  - Get companies (name, ARR/MRR property — configurable name, default e.g.
    `annualrevenue`).
  - Get associated open deals (amount, dealstage, closedate).
  - Honor 429 + `Retry-After`; paginate; broad try/except + log; raise a typed
    transient error for Celery retry.
- **`crm_enrichment` table** keyed `(organization_id, customer_email)` unique:
  `company_name`, `lifecycle_stage`, `arr`, `renewal_date` (from primary deal
  closedate), `deal_name`, `deal_stage`, `deal_amount`, `hubspot_contact_id`,
  `hubspot_company_id`, `hubspot_deal_id`, `last_synced_at`. Backend-api model +
  Alembic (chained with `hubspot-connection`) **and** worker mirror in
  `src/models/__init__.py` (no FK).
- **Sync task** `worker/src/tasks/hubspot_sync.py`:
  - Celery-free core `_sync_org(org_id, db, client)` — pull, match by lowercased
    email, Python-level upsert (no PG `ON CONFLICT`), pick **highest-value open deal
    with a closedate** as the renewal proxy, then guarded
    `update_customer_health(org_id, email, db)` (lazy import, tolerate ImportError).
  - `@shared_task(name="src.tasks.hubspot_sync.sync_all_hubspot")` fan-out over orgs
    with `is_active` HubSpot integrations → `sync_hubspot_org.delay(integration_id)`
    (mirror `integrations.py:sync_all_integrations`; per-org try/except so one
    failure doesn't abort the batch).
  - `@shared_task(bind=True, max_retries=3, name="src.tasks.hubspot_sync.sync_hubspot_org")`
    per-org worker; `self.retry` on transient HTTP errors; updates
    `last_synced_at`/`last_sync_status`/`last_error`/counts.
  - Register module in `celery_app.py` `include=[...]` and add a daily
    `beat_schedule` crontab entry (e.g. 03:00 UTC, between integrations 02:00 and
    usage 04:00).
- **Manual trigger:** `POST /api/v1/integrations/hubspot/sync` (backend-api, in the
  `hubspot-connection` router) enqueues `sync_hubspot_org.delay(...)`; gated
  `require_admin_or_owner`.

## Out of scope (this aspect)

- Connection model/routes/UI (→ `hubspot-connection`; this aspect consumes them).
- `crm_component` math + weights (→ `crm-health-component`); this aspect only
  *triggers* `update_customer_health`.
- Profile card + timeline rendering (→ `crm-profile-and-timeline`).

## Acceptance criteria (testable)

- `_sync_org` with a mocked HubSpot client upserts one `crm_enrichment` row per
  matched email; unmatched contacts are skipped and counted.
- Re-running `_sync_org` updates the existing row (no duplicate; idempotent upsert).
- Renewal proxy = highest-amount open deal with a `closedate`; ties + no-deal cases
  handled (null renewal).
- `_sync_org` calls `update_customer_health(org, email, db)` once per matched
  customer (mock asserts), tolerant of its ImportError.
- Fan-out task only enqueues orgs with active integrations; one org raising does not
  stop others.
- Client honors a 429 with `Retry-After` (mock) and paginates a multi-page list.
- Tests use in-memory SQLite + mocked `httpx`/client (no broker, no eager mode) —
  mirror `tests/test_usage_metrics.py` + `tests/test_intercom_adapter.py`.

## Dependencies & sequencing

- **Depends on `hubspot-connection`** (token decryption + integration row).
- Migration for `crm_enrichment` chains off the connection migration head.
- Build **before** `crm-health-component` is meaningful end-to-end (the component
  reads `crm_enrichment`), but the two can be developed in parallel against the
  agreed table schema.

## Open questions / risks

- ARR property name varies per portal → store configurable name on the integration
  (default `annualrevenue`); document the heuristic.
- Per-run work cap for huge portals → cap + `log()` truncation (no silent caps).
- Worker mirror model must stay in sync with the backend-api model (R4).
