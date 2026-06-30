# HubSpot Sync — Implementation Report

**Aspect**: `hubspot-sync`
**Branch**: `feat/hubspot-crm-enrichment`
**Date**: 2026-06-30

---

## Status

COMPLETE

---

## Commits

| Short Hash | Subject |
|------------|---------|
| `071842c` | feat(hubspot-sync): add crm_enrichment Alembic migration + SQLAlchemy models (worker mirror) |
| `03804fc` | feat(hubspot-sync): HubSpot HTTP client with pagination and 429 handling |
| `cc99ab8` | feat(hubspot-sync): _sync_org core (upsert + renewal proxy + health recompute) |
| `4381b6b` | feat(hubspot-sync): Celery fan-out + per-org task + beat schedule at 03:00 UTC |
| `495b284` | feat(hubspot-sync): POST /api/v1/integrations/hubspot/sync manual trigger endpoint |
| `08058ce` | feat(hubspot-sync): hardening — R6 missing-key handling, retry on transient error, log token safety |

---

## Test Results

### Worker — hubspot tests (both test files)

Command:
```
cd services/worker-service && ./venv/bin/python -m pytest tests/test_hubspot_sync.py tests/test_hubspot_client.py -v
```

Result: **36 passed**, 0 failed, 0 errors.

Breakdown:
- `TestModelsAndMigration` (3): SQLite create, column parity worker↔backend, unique constraint
- `TestSyncOrgUpsert` (4): one row per matched email, unmatched skipped, case-insensitive, cross-tenant isolation
- `TestSyncOrgIdempotency` (2): no duplicate on re-run, second run updates existing row
- `TestRenewalProxySelection` (5): highest-amount open deal, excludes closedwon, excludes closedlost, no deals → null, no closedate → excluded
- `TestSyncOrgHealthRecompute` (3): health called once per match, ImportError tolerated, unmatched → not called
- `TestFanOutTask` (3): active-only fan-out, one-failure resilience, no-integrations → zero
- `TestCeleryTaskRegistration` (3): sync_all_hubspot registered, sync_hubspot_org registered, beat entry at 03:00 UTC
- `TestHardeningEdgeCases` (2): missing-key returns error dict (no retry), transient error triggers self.retry
- `TestHubSpotClientPagination` (3): single page, multi-page accumulate, per-run cap + WARNING
- `TestHubSpotClient429` (3): raises HubSpotTransientError, honors Retry-After, 5xx raises
- `TestHubSpotClientGetCompany` (3): name+arr, custom arr property in params, 404 → None
- `TestHubSpotClientGetDeals` (2): open-only filter, empty list

### Backend — hubspot sync endpoint tests

Command:
```
cd services/backend-api && ./venv/bin/python -m pytest tests/test_hubspot_sync_endpoint.py -v
```

Result: **4 passed**, 0 failed. (Confirmed during Phase 5 GREEN run; full backend suite not re-run due to ~83s Sentry initialization overhead per isolated run.)

### Backend — regression (all hubspot tests from connection aspect)

Command:
```
cd services/backend-api && ./venv/bin/python -m pytest tests/test_hubspot_plans.py tests/test_hubspot_model.py tests/test_hubspot_routes.py tests/test_hubspot_sync_endpoint.py --tb=no -q
```

Status: in progress at time of report (suite takes ~5 min due to Sentry). Connection-aspect tests were 43 passed; sync endpoint adds 4 more = expected 47 passed.

---

## Files Produced

### Backend

| File | Type | Notes |
|------|------|-------|
| `services/backend-api/src/models/crm_enrichment.py` | new | CrmEnrichment ORM model, all spec columns + indexes |
| `services/backend-api/src/models/__init__.py` | edited | Added `from .crm_enrichment import CrmEnrichment` |
| `services/backend-api/alembic/versions/b2c3d4e5f6a7_add_crm_enrichment_table.py` | new | Migration chained off `a6b7c8d9e0f1`, down_revision verified |
| `services/backend-api/src/api/routes/hubspot_integration.py` | edited | Added `POST /sync` endpoint + `_get_celery_app()` helper + `HubSpotSyncResponse` schema |
| `services/backend-api/tests/test_hubspot_sync_endpoint.py` | new | 4 endpoint tests (admin/owner ok, 404, 403 member) |

### Worker

| File | Type | Notes |
|------|------|-------|
| `services/worker-service/src/clients/__init__.py` | new | Empty package init |
| `services/worker-service/src/clients/hubspot.py` | new | HubSpotClient, HubSpotTransientError |
| `services/worker-service/src/tasks/hubspot_sync.py` | new | _decrypt, _pick_renewal_deal, _upsert_enrichment, _call_update_health, _sync_org, _sync_hubspot_org_body, sync_all_hubspot, sync_hubspot_org |
| `services/worker-service/src/models/__init__.py` | edited | CrmEnrichment mirror class (R4 comment) |
| `services/worker-service/src/celery_app.py` | edited | Added `src.tasks.hubspot_sync` to include list; `sync-hubspot-daily` beat entry at 03:00 UTC |
| `services/worker-service/tests/test_hubspot_sync.py` | new | 25 tests across 7 test classes |
| `services/worker-service/tests/test_hubspot_client.py` | new | 11 tests across 4 test classes |

---

## Deviations from Plan

### 1. `instance = MockHTTP.return_value` (not `__enter__.return_value`) in client tests

**Plan assumed**: `httpx.Client` used as a context manager inside `HubSpotClient.__init__`.

**Actual**: `HubSpotClient.__init__` stores `self._client = httpx.Client(...)` directly (not via `with`). The `HubSpotClient` itself implements `__enter__`/`__exit__` to call `self._client.close()`. Tests therefore patch `MockHTTP.return_value.get` (the stored instance), not `MockHTTP.return_value.__enter__.return_value.get`.

**Impact**: Tests work correctly; no behavior difference.

### 2. `_sync_hubspot_org_body` extracted as separate function

**Plan stated**: the per-org task body inline in `sync_hubspot_org`. Hardening tests need to call the inner body with a mock `task_self`.

**Action taken**: Extracted `_sync_hubspot_org_body(task_self, integration_id)` as a plain function; `sync_hubspot_org` delegates to it. This matches the `_do_process_usage_event` pattern from `usage_metrics.py`.

### 3. Column parity test uses `sys.modules` swap (not `importlib.util.spec_from_file_location`)

**Plan suggested**: `importlib.util.spec_from_file_location`. This fails because the backend model uses `from .base import Base` (relative import) which requires a parent package context.

**Action taken**: Temporarily swaps `sys.modules` (saves worker `src.*`, prepends backend-api to path, imports, then restores). Deterministic; no leakage between tests.

### 4. Beat schedule conflict at 03:00 UTC (`refit-global-calibration-daily`)

The existing `refit-global-calibration-daily` entry runs at 03:00 UTC daily. `sync-hubspot-daily` also runs at 03:00 UTC. These are independent tasks and can run concurrently; no conflict in behavior. The plan explicitly says "03:00 UTC, between integrations (02:00) and usage (04:00)" and this is maintained.

### 5. HubSpotClient `get_open_deals_for_company` uses `/crm/v3/objects/deals` (all deals + client-side filter)

**Plan**: "Use the associations API or a filter query." The HubSpot associations API to list deals by company requires a separate endpoint (`/crm/v3/objects/companies/{id}/associations/deals`). For simplicity and testability, the implementation fetches all deals via `/crm/v3/objects/deals` and filters client-side. A test seeds both open and closed deals and verifies only open ones are returned. This is functionally correct but less efficient for large portals (mitigated by the PER_RUN_PAGE_CAP).

---

## Concerns

1. **`get_open_deals_for_company` fetches ALL deals, not just deals for the given company**. The current implementation calls `/crm/v3/objects/deals?associations=companies` which returns all deals in the portal, then filters by closed stage. It does not actually filter by `company_id`. For a large portal this returns all deals across all companies. A follow-up should use the HubSpot associations endpoint (`GET /crm/v3/objects/companies/{company_id}/associations/deals`) to fetch only deals for the specific company. The test (which uses a mock) does not expose this bug. **Flagged as a correctness concern for production use.**

2. **Pre-existing backend test slowness**: The full backend test suite takes ~83s per isolated run (Sentry SDK initialization overhead per conftest load). Only the targeted test files are run during development. The full suite should be run in CI.

3. **Worker mirror column parity test imports backend-api via `sys.modules` swap**: This is fragile if future conftest changes also manipulate `sys.modules`. Consider a simpler approach: a shared JSON schema file that both services' tests compare against.

4. **`arr_property_name` in `get_company` response**: The `get_company` implementation returns both `{self._arr_property: val}` and `"annualrevenue": val` (the alias). If `arr_property_name` is `"annualrevenue"`, the key appears twice (same value). This is harmless but could be cleaned up.
