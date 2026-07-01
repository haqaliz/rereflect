# Aspect Spec — crm-provider-generalization

**PRD:** `../prd.md` · **Build order: aspect 1 of 4 (first).** Owns the first migration in the chain.

## Problem slice & outcome
Make `crm_enrichment` and its read paths provider-aware so a second CRM (Salesforce) can populate the same semantic fields without ambiguity — while every existing HubSpot-enriched org is **completely unaffected** (scores + API output byte-for-byte identical).

## In scope
- Add `provider VARCHAR(50) NOT NULL DEFAULT 'hubspot'` to `crm_enrichment` in **both** `services/backend-api/src/models/crm_enrichment.py` and `services/worker-service/src/models/__init__.py` (parity test enforced).
- Alembic migration `down_revision = 'd4e5f6a7b8c9'` (current head); `server_default='hubspot'` backfills existing rows.
- `customer_timeline_service._fetch_crm_events` (`:435-491`): replace hardcoded `source="hubspot"` (`:471,484`) and "…from HubSpot" text (`:469-470`) with `row.provider`-driven source + a provider-titled description (e.g. `.title()`).
- Add optional `crm_provider: Optional[str]` to the shared serializer `_read_crm_fields` (`customer_profile_serializer.py:91-130`) and to **both** `CustomerProfileResponse` (`customers.py:108-115`) and `PublicCustomerProfile360` (`public_api.py:181-188`) — kept in parity.
- Update the two "(HubSpot)" comments to "(HubSpot / Salesforce)".

## Out of scope
- Any change to `_compute_crm_component`, `WEIGHTS`, `_get_org_weights`, or the health-weights API (they read only `renewal_date` / weight columns — untouched).
- The `hubspot_*` ID columns (leave as-is; Salesforce IDs handled in the sync aspect via generic fields or its own columns — decided there).
- Salesforce connection / sync / UI.

## Acceptance criteria (testable)
1. **RED characterization test (write first):** for a fixture HubSpot-enriched org+customer, capture serialized `crm_*` profile output and `compute_health_score()` result; assert identical after the migration + code changes. Must pass unchanged.
2. Migration round-trips clean: `alembic upgrade head → downgrade -1 → upgrade head`.
3. Existing `crm_enrichment` rows read back with `provider == 'hubspot'`.
4. A `crm_enrichment` row with `provider='salesforce'` produces a timeline event whose `source == 'salesforce'` and description names Salesforce.
5. v1 and public profile responses include `crm_provider`; parity test still green.
6. Full backend suite green (`pytest tests/ -v`).

## Dependencies & sequencing
- **First.** Supplies the migration head revision id to `salesforce-connection`.
- No dependency on Salesforce code; purely a safe generalization.

## Risks
- Parity test between backend/worker models — remember to add the column in both places.
- Don't touch health math; the whole point is zero score movement.
