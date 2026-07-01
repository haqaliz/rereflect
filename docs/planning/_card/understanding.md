# Understanding — Salesforce CRM Enrichment (Phase 2 dig)

Synthesized from 3 parallel read-only dig agents (storage/health, connection/worker-sync, frontend). All `file:line` refs are in the `feat-salesforce-crm-enrichment` worktree.

## What the task really is

Add **Salesforce** as a second CRM enrichment source alongside the shipped HubSpot integration. The good news from the dig: **most of the consuming layer is already provider-neutral**, so this is mostly *additive* (a new integration + sync + UI sibling), plus a *light* generalization of the shared storage.

## Key finding: the generalization is smaller than the card assumed

- `crm_enrichment` has **7 semantic columns** (`company_name, lifecycle_stage, arr, renewal_date, deal_name, deal_stage, deal_amount`) that are already provider-neutral, + 3 HubSpot-specific ID columns (`hubspot_contact_id/company_id/deal_id`) + keys. `crm_enrichment.py:33-57`.
- **`_compute_crm_component` reads ONLY `renewal_date`** (`health_score_service.py:108-181`, raw SQL at `:138`). So the health-score math needs **zero change** and existing HubSpot-enriched scores are trivially stable — adding a `provider` column with `server_default='hubspot'` doesn't touch the renewal read. The usage-component "weight-0 characterization" discipline still applies as a safety test, but the risk is low.
- The serializer (`customer_profile_serializer.py::_read_crm_fields:91-130`) already returns only the 7 semantic fields to both v1 and public API — **no `hubspot_*` ID is ever exposed**. One shared serializer, one place to touch.
- Frontend `crm_*` profile fields, `ActivityEvent` CRM types, and `eventIconMap` are **already provider-neutral** (`customers.ts:100-107,168-197`, `ActivityTimeline.tsx:45-109`).

### The only true runtime HubSpot hardcoding
`customer_timeline_service.py::_fetch_crm_events` bakes `source="hubspot"` + "…from HubSpot" text at `:469-471,484`. This must become `provider`-driven once the discriminator exists. Everything else labeled "HubSpot" is either a comment or an intentionally provider-specific module/route/page that gets a **Salesforce sibling**, not a rename.

## Alembic
Current head of the whole tree = **`d4e5f6a7b8c9`** (`add_model_embeddings_to_org_ai_config`). New migration chains off it. Health-weights already sum **6** components (`churn .35, sentiment .25, resolution .25, frequency .15, usage 0, crm 0`) — `categories.py:192-198`. CRM weight is `org_ai_config.health_weight_crm` (default 0). Worker mirrors every model manually; a CI test enforces `CrmEnrichment` column parity — any new column must be added to **both** `src/models/crm_enrichment.py` and `worker-service/src/models/__init__.py:856-887`.

## Integration/connection pattern (two precedents in-repo)
- **HubSpot** (`hubspot_integration.py`): pasted **private-app token** (`POST /connect` with `access_token`), encrypted via `src/utils/encryption.py` (`encrypt_api_key`/`decrypt_api_key`/`get_key_hint`, `LLM_ENCRYPTION_KEY`, "R6 guard" → 422 not 500). One `hubspot_integrations` row per org (`UniqueConstraint(organization_id)`). Feature gated via `require_feature("hubspot_integration")` + `plans.py` (SELF_HOSTED → always unlocked).
- **Linear** (`linear_integration.py` + `linear.ts` + `linear/page.tsx:339-350`): **OAuth-redirect** flow (`getConnectUrl()` → `auth_url` → `window.location.href`). **This is the closer structural precedent for Salesforce's connect UX** than HubSpot's token form.

Worker sync (`worker-service/src/tasks/hubspot_sync.py` + `clients/hubspot.py`): per-org `_sync_org` upserts `CrmEnrichment` by `(org,email)`, `_pick_renewal_deal` renewal proxy, `_call_update_health` recompute; Celery fan-out `sync_all_hubspot` + per-org `sync_hubspot_org` (retryable), beat entry `sync-hubspot-daily` at 03:15 UTC. Manual trigger `POST /integrations/hubspot/sync` → `send_task`.

## What will NOT transfer from HubSpot (Salesforce divergences)
1. **Auth**: HubSpot = long-lived static bearer. Salesforce = OAuth2 with a **refresh token** + short-lived access tokens that must be refreshed before each sync → needs an encrypted `refresh_token` column + a refresh step in the client. (See decision D1.)
2. **`instance_url`** (per-org Salesforce base URL, returned at token exchange) replaces `hub_id`/`portal_name`; the client base URL is per-instance, not a fixed constant.
3. **SOQL over REST Query API** (`/services/data/vXX.X/query?q=…`, pagination via `nextRecordsUrl`) replaces HubSpot's associations + batch/read. Simpler in one way: `Contact.AccountId` is a direct FK (no associations round-trip). Objects: Account/Contact/Opportunity ↔ Company/Contact/Deal.
4. **Rate limiting**: Salesforce = rolling daily API quota (`Sforce-Limit-Info` header / `/limits`), not per-request `Retry-After`.
5. **ARR**: Salesforce `Account.AnnualRevenue` is standard — the configurable `arr_property_name` knob may be unnecessary.

## Open decisions to resolve in the interview
- **D1 — Salesforce auth flow.** Web-server OAuth redirect (mirrors Linear; needs the operator to set a redirect URI in their Connected App) vs. **JWT Bearer server-to-server** (headless, no redirect — better fit for self-host, but needs a cert/private-key on the Connected App) vs. a pasted session/access token (simplest, mirrors HubSpot's self-host rationale, but Salesforce tokens are short-lived). NOTE: HubSpot deliberately avoided OAuth *for self-hosting reasons* — but Linear proves redirect OAuth works in this product. **Primary decision.**
- **D2 — Storage strategy.** (a) **Separate `salesforce_integrations` table** (mirrors HubSpot, zero constraint changes, lowest risk) vs (b) unified `crm_integrations` with `UniqueConstraint(org, provider)`. Recommend (a) for slice 1.
- **D3 — One CRM per org, or both at once?** `crm_enrichment` is unique on `(org, email)` — if both HubSpot and Salesforce enrich the same customer they collide. Options: one-CRM-connected-at-a-time (simplest), last-writer-wins per customer, or add `provider` to the enrichment unique key + reconciliation. Interacts with D2.
- **D4 — Salesforce field mapping.** ARR ← `Account.AnnualRevenue`; renewal_date ← ? (Opportunity `CloseDate` of the open renewal? a custom field? Contract end date?); deal_stage ← `Opportunity.StageName`; deal_amount ← `Opportunity.Amount`; renewal deal pick ← mirror `_pick_renewal_deal` (open, has close date, highest amount).
- **D5 — Sync trigger.** Scheduled Celery beat (mirror HubSpot daily) + manual trigger; pull-only; polling (no streaming/Platform Events in slice 1). Pick an unused UTC beat slot (03:15 taken by HubSpot; 03:00 by calibration).

## Affected services
- `backend-api`: new `salesforce_integration.py` route + model + migration (provider column on crm_enrichment + salesforce_integrations table); `_fetch_crm_events` provider fix; optional `crm_provider` on serializer/responses; `plans.py` feature id.
- `worker-service`: new `clients/salesforce.py` + `tasks/salesforce_sync.py`; model mirrors; `celery_app.py` include + beat.
- `frontend-web`: new `lib/api/salesforce.ts`, integrations tile, `settings/integrations/salesforce/page.tsx` (Linear-OAuth-style connect), optional `SalesforceIcon.tsx`, 2 copy fixes.
- `analysis-engine`: unaffected.
