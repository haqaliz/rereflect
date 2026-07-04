# Understanding — feat/salesforce-crm-writeback

Synthesized from 4 read-only mapper agents over the worktree checkout: (1) the shipped **HubSpot
writeback** backend, (2) the shipped **Salesforce** inbound-enrichment client + connection, (3) the
provider-generalized **CRM read layer + health trigger seam**, (4) the **frontend** writeback card +
Salesforce settings page. All file:line citations below are verified on `feat/salesforce-crm-writeback`
(= `origin/master` @ `c44947e`).

---

## What the task really asks

Add **Salesforce health-score writeback** (push a customer's Rereflect health score into a Salesforce
field), by **mirroring the already-shipped HubSpot writeback** and **generalizing the single hardcoded
trigger seam**. Health-score, single-field, off-by-default, idempotent, OSS-unlocked. Everything on the
Salesforce *read* side (OAuth, client, sync, model, one-CRM guard) already ships — this slice is the
outbound half.

## Big favorable findings (de-risk the caveats)

1. **No reconnect needed — the OAuth scope is already write-capable.** The Salesforce connect flow
   requests `SALESFORCE_SCOPE = "refresh_token offline_access api"`
   (`backend-api/src/api/routes/salesforce_integration.py:108`, used at `:341`). The `api` scope is
   Salesforce's full REST scope and permits sObject `PATCH`. Existing connections already carry it.
2. **Idempotency memory is already provider-agnostic.** `crm_enrichment` already has
   `last_written_health_score` + `last_health_written_at` (`models/crm_enrichment.py:59-60`) — the same
   columns HubSpot writeback uses. Reuse them; no new idempotency schema.
3. **One-CRM-per-org guard is symmetric and shipped.** `another_crm_active(...)`
   (`services/crm_integration_common.py:18-73`) is enforced on both connect paths, so at most one
   provider is ever active. A simple provider-dispatch in the trigger is sufficient — no dual-CRM
   reconciliation.

## The trigger seam to generalize (the crux)

`health_score_service.py:278` `_maybe_enqueue_writeback(...)` is **hardcoded to HubSpot**: it queries
`HubSpotIntegration` (active + `writeback_enabled`) and `send_task("src.tasks.hubspot_writeback.push_health_to_hubspot", [org_id, email])`. Called from `update_customer_health` at `:406`, **existing-customer branch only** (new customers never enqueue), guarded by `abs(new-old) < 2` skip. It never raises (broad try/except-log).

→ Generalize this to also dispatch `src.tasks.salesforce_writeback.push_health_to_salesforce` when an
active writeback-enabled `SalesforceIntegration` exists. Must keep `test_health_writeback_enqueue.py`
green (HubSpot path unchanged) and preserve the `<2` threshold + the existing-customer-only behavior for
both providers.

## The 6 mirror areas (HubSpot → Salesforce), with anchors

| # | Area | Shipped HubSpot anchor | Salesforce gap to build |
|---|---|---|---|
| 1 | **Writeback config columns** | `models/hubspot_integration.py:38-44` (`writeback_enabled`, `writeback_field_name`, `last_writeback_at/status/error`, `contacts_written`) | `models/salesforce_integration.py` ends at `contacts_matched` (`:38`) — add the same 6 columns + Alembic migration (precedent `9f56f9a4f999_add_salesforce_integrations_table.py`) |
| 2 | **Matched contact id + idempotency** | `crm_enrichment.py:53-55` `hubspot_contact_id`; idempotency `:59-60` (reuse) | **No `salesforce_contact_id`.** Salesforce sync throws Contact.Id away (`worker/src/tasks/salesforce_sync.py:145-161` upsert). Add a `salesforce_contact_id` column (+ worker-model mirror + migration) and populate it in `_upsert_enrichment` |
| 3 | **Field validation service** | `services/hubspot_writeback_validation.py` — `validate_writeback_field(token, name) -> (bool, reason)`; GETs `/crm/v3/properties/contacts/{name}`; checks `type=="number"`, not calculated, not read-only | New `salesforce_writeback_validation.py` — validate via Salesforce **sObject describe** (`/services/data/vXX/sobjects/Contact/describe`): field exists, `updateable==true`, numeric type (`double`/`int`/`currency`/`percent`). Same `(bool, reason)` contract |
| 4 | **Client PATCH + describe** | `worker/src/clients/hubspot.py:290` `update_contact_property` (`PATCH /crm/v3/objects/contacts/{id}`), `:337` `get_contact_property_def` | `worker/src/clients/salesforce.py` is query-only. Add `update_contact_field(id, field, value)` (`PATCH /services/data/{ver}/sobjects/Contact/{id}`, JSON body — **do NOT stringify** the number like HubSpot's `_format_number`) + a `describe_object`/field-def method. Reuse `_refresh`, `SalesforceTransientError`/`SalesforceAuthError`, `_validate_sf_id` |
| 5 | **Routes** | `routes/hubspot_integration.py`: `PATCH /writeback` (`:396`), `POST /writeback/test` (`:523`), writeback fields on `GET /status` (`:303-308`), inline backfill-on-enable `_enqueue_backfill_writeback` (`:459-512`, cap 500) | Mirror under `/api/v1/integrations/salesforce`, `require_admin_or_owner` + `require_feature("salesforce_integration")` (feature gate is an unlocked no-op). 422 on enable-without-field; 400 with `{reason, message}` on validation fail (leave disabled) |
| 6 | **Push task** | `worker/src/tasks/hubspot_writeback.py:205` `push_health_to_hubspot` (+ body `:60`): gating no-ops, skip-if-unchanged (`:105-111`), soft-pause never sets `is_active=False`, retry on transient; registered `celery_app.py:50` | New `salesforce_writeback.py` `push_health_to_salesforce` mirroring all of it; register in `worker/src/celery_app.py` include. Resolve the target Contact.Id from `crm_enrichment.salesforce_contact_id` (fall back to re-query-by-email if null, for rows synced before this slice) |

## Frontend (mirror, tightly scoped)

- **Create** `components/settings/SalesforceWritebackCard.tsx` mirroring
  `components/settings/HubSpotWritebackCard.tsx` (238 lines): Switch(enable) + field Input + Validate
  button + status grid + last-error alert; refetch-on-change (never optimistic); `null` when
  `!status.connected`. Swap copy + default field name (`Rereflect_Health_Score__c`, SF custom-field
  `__c` suffix).
- **Edit** `lib/api/salesforce.ts` (66 lines): extend `SalesforceConnectionStatus` with the 6 writeback
  fields (mirror `hubspot.ts:17-24`); add `updateWriteback` (`PATCH .../salesforce/writeback`) +
  `testWriteback` (`POST .../salesforce/writeback/test`) + 3 interfaces.
- **Edit** `app/(dashboard)/settings/integrations/salesforce/page.tsx` (431 lines): render
  `<SalesforceWritebackCard status={status} onStatusChange={setStatus} />` between the connection Card
  (~`:368`) and the Help Card (~`:371`), gated `status?.connected && isAdminOrOwner` (mirrors HubSpot
  page `:400-403`). No integrations-index tile change (HubSpot doesn't surface writeback there either).

## Must-not-regress (characterization)

`tests/test_crm_provider_generalization.py` — keep byte-identical:
`compute_health_score()` → `health_score==47`, `crm_component==pytest.approx(25.0)`, `risk_level=="at_risk"`
(`:81-95`); the 7 `crm_*` serializer values (`:147-156`). `_compute_crm_component`
(`health_score_service.py:108-181`) reads only `renewal_date` with **no provider filter** — adding
`salesforce_contact_id` / writeback columns must not touch it. Worker-model column parity for
`CrmEnrichment` is asserted by a test — mirror any new column in `worker/src/models/`.

## Contradictions / risks surfaced

- **Contact-id gap (real dependency):** writeback needs a Salesforce record to PATCH. Today none is
  persisted. Chosen approach: add `salesforce_contact_id`, populate in sync, and have the push task
  re-query by email when it's null (so the feature works before a full re-sync, and backfill-on-enable
  can enqueue rows too). This is the one net-new piece beyond a pure HubSpot mirror.
- **Field-type semantics differ:** HubSpot's `type=="number"` check does not map to Salesforce. SF uses
  the describe API's `updateable` flag + numeric `type` set. Validation logic must be SF-specific.
- **Number formatting differs:** SF REST accepts a JSON number; do not copy HubSpot's stringification.
- **`SalesforceIntegration` has no `writeback_enabled`** — needed for symmetric gating in the trigger.

## Open questions for the interview (seed)

1. **Write target — Contact vs Account?** Read side matches by `Contact.Email`, health is per-email →
   **Contact** field is the natural, consistent target. Confirm (Account would need aggregation).
2. **Config home** — mirror HubSpot by adding `writeback_*` columns to `SalesforceIntegration`
   (symmetric, no cross-provider schema) vs a shared generalized writeback-config table. Recommend
   **mirror on the model** (matches slice-1 precedent; slice-3 CRMs stay cheap by copying the pattern).
3. **Contact-id resolution** — persist `salesforce_contact_id` (populate in sync) **with** a
   re-query-by-email fallback in the push task (recommended), vs re-query-only (simpler, one extra SOQL
   per push, no schema/sync change). Recommend persist+fallback.
4. **Numeric field types accepted** — `double`/`int`/`currency`/`percent` via describe `updateable`?
   Confirm the exact allowed set + whether text fields are rejected (mirror HubSpot's `wrong_type`).
5. **Default field name** — `Rereflect_Health_Score__c` (SF custom-field convention). Confirm.
6. **Backfill on enable** — mirror HubSpot's inline enqueue over `crm_enrichment` rows with
   `provider='salesforce'` (cap 500), skipping rows with no resolvable contact id. Confirm cap reuse.
