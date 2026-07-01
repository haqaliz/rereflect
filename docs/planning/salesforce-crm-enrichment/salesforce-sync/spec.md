# Aspect Spec — salesforce-sync

**PRD:** `../prd.md` · **Build order: aspect 3 of 4.** No new migration (writes existing `crm_enrichment`).

## Problem slice & outcome
A connected Salesforce org is pulled on a schedule (and on manual trigger); matched customers get their `crm_enrichment` populated with `provider='salesforce'` and their health score recomputed.

## In scope
- **Client** `services/worker-service/src/clients/salesforce.py`:
  - Token refresh: exchange stored `refresh_token` → short-lived `access_token` (against `{login_base}/services/oauth2/token`), using it as `Authorization: Bearer` against `instance_url`.
  - `SalesforceTransientError` for retryable 429 / 5xx.
  - SOQL over `GET {instance_url}/services/data/v{API}/query?q=...`; pagination via `nextRecordsUrl`; a `PER_RUN_PAGE_CAP` (mirror HubSpot) with a WARNING log when hit.
  - Daily-limit awareness via the `Sforce-Limit-Info` response header (log remaining; back off / stop when near zero).
  - Queries: Contacts (`Id, Email, AccountId, Name`), Accounts (`Id, Name, AnnualRevenue, Type`), open Opportunities per Account (`Id, Name, StageName, Amount, CloseDate, IsClosed`).
- **Task** `services/worker-service/src/tasks/salesforce_sync.py`:
  - `_sync_org(org_id, db, client)`: build known-email set from `CustomerHealth`; pull Contacts; match by lowercased `Email`; for matches, resolve Account (direct `AccountId` FK — no associations) → company/ARR; pick renewal Opportunity (`_pick_renewal_opportunity`: not closed, has `CloseDate`, highest `Amount`) → renewal_date/deal_*; `_upsert_enrichment(..., provider='salesforce')` (Python-level upsert on `(org,email)`, SQLite-safe); `_call_update_health(org_id, email, db)`.
  - `_sync_salesforce_org_body`: load integration, check `is_active`, refresh token (R6 missing-key → non-retrying error; `invalid_grant` → set `is_active=False` + `last_error`, non-retrying); run client + `_sync_org`; update sync stats; `SalesforceTransientError` → `self.retry()`; other → log + `last_sync_status='error'` + re-raise.
  - `sync_all_salesforce` (fan-out over active integrations, per-org failures isolated) + `sync_salesforce_org` (`bind=True, max_retries=3, default_retry_delay=30`).
- **Registration:** add `"src.tasks.salesforce_sync"` to `celery_app.py` `include`; add beat entry (new UTC slot, e.g. `crontab(hour=3, minute=45)` — avoid 03:00 calibration / 03:15 hubspot).
- Reuse the guarded `update_customer_health` import pattern (`hubspot_sync.py:136-153`).

## Out of scope
- Connection/OAuth (aspect 2 supplies creds).
- Frontend.
- Bulk API, streaming, push-back.

## Acceptance criteria (testable)
1. Synthetic mocked SOQL responses → `_sync_org` upserts a `crm_enrichment` row with `provider='salesforce'`, correct company/ARR/renewal/deal, matched by email.
2. Renewal pick chooses the open, highest-amount opportunity with a `CloseDate`; ignores closed ones.
3. `update_customer_health` called once per matched customer (mock).
4. Idempotent: re-running the sync doesn't duplicate rows (upsert on `(org,email)`).
5. 429/5xx → `SalesforceTransientError` → retry; `invalid_grant` → integration marked disconnected, no retry.
6. Worker suite green (`pytest tests/ -v`).

## Dependencies & sequencing
- After `salesforce-connection` (creds + model) and `crm-provider-generalization` (`provider` column).
- Task name must exactly match the `send_task` string in the connection aspect's `POST /sync`.
- Mock all Salesforce HTTP.

## Risks
- Timezone-aware `CloseDate` comparisons.
- Account with no open renewal opp → leave renewal_date null (neutral CRM component); don't crash.
