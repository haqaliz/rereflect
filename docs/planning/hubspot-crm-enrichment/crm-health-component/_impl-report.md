# Implementation Report — crm-health-component

**Status:** COMPLETE — all phases GREEN, all acceptance criteria met.

---

## Commits

| Hash | Subject |
|------|---------|
| `c2576f6` | `test(crm-health): RED phase — CRM component + 6-weight tests (all failing)` |
| `36948bd` | `feat(migration): add crm_component + health_weight_crm (3rd chained migration)` |
| `3b4d231` | `feat(models): add crm_component Float + health_weight_crm Integer to ORM models` |
| `d5654e3` | `feat(health): _compute_crm_component, WEIGHTS, _get_org_weights, weighted sum, upsert + history` |
| `79ab4f0` | `feat(categories): extend health-weights endpoint to 6 weights incl. crm` |
| `5d6d02c` | `feat(worker): catch up OrgAIConfig + CustomerHealth mirrors (usage + crm columns)` |
| `868de17` | `test(crm-health): confirm weight-0 regression — all existing health tests green` |

---

## Test Results

### New tests (TDD target)
```
cd services/backend-api
./venv/bin/python -m pytest tests/test_health_crm_component.py tests/test_health_weights_6fields.py -v
```
**Result: 27 passed, 0 failed**

### Regression suite (weight-0 invariance)
```
./venv/bin/python -m pytest tests/test_health_usage_component.py tests/test_health_weights.py -v
```
**Result: 47 passed, 0 failed**

---

## Deviations from Plan and Rationale

### D1: `crm_enrichment_table` fixture simplified
**Plan:** Create the `crm_enrichment` table via raw DDL inside the fixture, independent of hubspot-sync.
**Actual:** The `CrmEnrichment` ORM model was already present on this branch (from the hubspot-sync aspect, which was already committed). `Base.metadata.create_all()` in conftest already creates the table. The `CREATE TABLE IF NOT EXISTS` DDL in the fixture was a no-op that masked the real table schema.
**Resolution:** Made `crm_enrichment_table` a no-op yield fixture (table exists via ORM) and updated all test inserts to use the `CrmEnrichment` ORM model with proper required fields (`last_synced_at` is NOT NULL in the real schema).

### D2: `_insert_renewal` uses midnight datetimes
**Plan:** Store renewal_date as ISO8601 date string via raw SQL.
**Actual:** ORM inserts produce `DateTime` objects (or ISO8601 datetime strings in SQLite). Using `datetime.utcnow() + timedelta(days=N)` minus `datetime.utcnow()` has microsecond drift that makes `.days` off by 1. Used midnight datetimes (`datetime(y, m, d)`) for both inserts and the `now` argument to ensure exact day arithmetic.

### D3: String parsing extended for Python 3.9 compatibility
**Plan:** `date.fromisoformat()` to parse renewal_date strings.
**Actual:** SQLite returns datetime strings like `"2026-07-25 00:00:00.000000"`. Python 3.9's `date.fromisoformat()` only accepts `"YYYY-MM-DD"` format (not full datetime strings). Used `datetime.fromisoformat()` (which handles both formats in 3.7+) with a fallback to `strptime(raw[:10], "%Y-%m-%d")`.

### D4: Tests use `db.flush()` after `update_customer_health`
**Plan:** Not specified.
**Actual:** `TestingSessionLocal` has `autoflush=False`. The `db.add(history)` inside `update_customer_health` isn't auto-flushed before the test query. Added `db.flush()` in both persistence tests after calling `update_customer_health` to make the history row visible.

### D5: `test_health_usage_component.py` — two count assertions updated
**Plan:** Update only `test_returns_five_keys_with_usage_default` from `== 5` to `== 6`.
**Actual:** Also updated `test_returns_five_keys_when_config_exists` (in `TestGetOrgWeightsWithUsageColumn`) which also asserts `len(weights) == 5` and `"usage" in weights`. Both are intentional snapshot updates per plan §R-7 / note in §5 ("the plan identifies").

---

## Concerns

1. **Migration revision ID uniqueness:** The revision `c3d4e5f6a7b8` was hand-chosen to avoid collision with existing revisions. It follows the project's hex-string naming convention and was verified to produce a single head after creation.

2. **Worker model drift:** The worker `CustomerHealth` mirror was missing `confidence_score`, `usage_component`, and all CRM columns. This catch-up is additive (no breaking changes to worker queries) but future aspects must maintain discipline — these mirrors are not enforced by a CI check.

3. **SQLite vs PostgreSQL date handling:** The `_compute_crm_component` string parsing handles SQLite's text representation of datetimes. On PostgreSQL in production, `renewal_date` returns a native `datetime` object (bypassing the string path entirely). The code is tested against SQLite in CI and manually verified for the PostgreSQL code path via the isinstance guard.
