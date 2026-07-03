# Understanding — feat/crm-writeback

Synthesized from 4 read-only mapper agents over the worktree (backend CRM, worker sync, health recompute, frontend UI). All line refs are the worktree checkout.

## What the task is really asking

Add the **outbound** half of CRM integration: push Rereflect's `health_score` for a matched
customer back into the connected CRM (HubSpot, slice 1) as a **custom contact property**,
opt-in per org, reusing the existing inbound (read) CRM plumbing. Today CRM data flows
**one way** (CRM → Rereflect health `crm_component`); this adds Rereflect → CRM.

## Affected areas (by service)

**backend-api**
- `src/models/crm_enrichment.py` — per-`(org, email)` row, `provider` discriminator, `hubspot_contact_id` (the id we PATCH against). Row written by worker, read by health/profile.
- `src/models/hubspot_integration.py` — one row/org; encrypted `access_token` + `token_hint`; **`arr_property_name` (default `annualrevenue`) is the existing precedent for a configurable HubSpot property name** → mirror it for a writeback field name. Sync-status columns (`last_synced_at`/`last_sync_status`/`last_error`) → mirror for writeback status.
- `src/api/routes/hubspot_integration.py` — connect/status/disconnect/test/sync (prefix `/api/v1/integrations/hubspot`). Only a **GET** validation client exists here; **no PATCH/write client anywhere in backend-api**. `get_decrypted_token()` exported for the worker.
- `src/models/org_ai_config.py` — generic per-org settings, opt-in-default-off precedent (`health_weight_crm=0`). Candidate home for the writeback flag/field-name (vs. putting it on `HubSpotIntegration`).
- `src/services/crm_integration_common.py` — shared one-CRM guard + `purge_crm_enrichment`.
- `src/services/health_score_service.py` — **the trigger source.** `update_customer_health()` (:278) recomputes+persists; captures `old_score`/`new_score` (:313–332) and fires `_check_health_drop_alert()` at **:335** — the natural change-detection hook. It does **not** commit (caller owns txn), and is called predominantly from the **worker**.

**worker-service**
- `src/tasks/hubspot_sync.py` — per-org fan-out (`sync_all_hubspot` → `sync_hubspot_org`), Fernet `_decrypt` (env `LLM_ENCRYPTION_KEY`), `HubSpotClient` context manager, retry decorator (`max_retries=3`), `HubSpotTransientError` on 429/5xx.
- `src/clients/hubspot.py` — `HubSpotClient` (base `https://api.hubapi.com`, Bearer). **Read-only today (GET only)** — a `PATCH /crm/v3/objects/contacts/{id}` method is the new write surface.
- `src/tasks/salesforce_sync.py` — the **invalid_grant → `is_active=False` disconnect** pattern (:372–387) to mirror if a writeback token loses scope.
- `src/celery_app.py` — `beat_schedule` (HubSpot 03:15, Salesforce 03:45, usage-recompute 04:00 UTC) + `include=[...]` task registry. A new writeback beat/task registers here.
- **Worker mirrors backend models (no cross-import); a CI parity test enforces column match** — any new column added to a mirrored model must be added on both sides.

**frontend-web**
- `app/(dashboard)/settings/integrations/hubspot/page.tsx` — detail page with the **ARR-property-name input + status grid + Test/Disconnect + `last_error` alert** → the exact shape to extend with a writeback toggle, field-name input, and writeback-status row.
- `lib/api/hubspot.ts` (+ shared `lib/api-client.ts` axios w/ Bearer interceptor) — add writeback config + status calls here.
- `components/settings/AISettingsGeneral.tsx` — clean `Switch` → PATCH persist pattern to mirror for the opt-in toggle.

## Design decision that must be settled (trigger model)

Two viable placements — the mappers split on this, so it's the #1 interview question:
1. **Event-driven**: enqueue a writeback Celery task from `update_customer_health` right after :335 when the score changed *and* writeback is enabled. Timely; matches the brief's "push when the score recomputes". Couples health service → writeback; fires pre-commit (must enqueue, not call HubSpot inline).
2. **Batch daily beat** (mapper-recommended for symmetry): a standalone `sync_hubspot_writeback` task on its own beat that scans `CustomerHealth` and pushes changed scores. Simplest, matches existing sync symmetry, rate-limit-friendly, decoupled; less timely (up to 24h lag).

## Ambiguities / open questions (for the interview)

- Trigger model (above): event-driven vs. daily batch for slice 1.
- Config home: `HubSpotIntegration` (per-integration, mirrors `arr_property_name`) vs. `OrgAIConfig` (generic settings).
- Field provisioning: auto-create the HubSpot custom property via API on enable, vs. require the operator to create it and just **detect/validate** presence (safer, less scope).
- HubSpot object: contact property (matches the email-based read side) vs. company. Default: **contact**.
- Idempotency: skip the PATCH when the property already equals the current score (avoid churn + rate-limit waste).
- Failure surface: where "missing write scope / field not found / last pushed OK@T" status lives (writeback-status columns on the integration + rendered on the detail page).
- Missing write scope handling: mirror Salesforce's invalid_grant disconnect, or a softer "writeback paused, fix scope" status that leaves the read sync intact?

## No contradictions found

The brief matches the code: writeback genuinely does not exist, the read-side plumbing is present and provider-generalized, and the `arr_property_name` + sync-status precedents make a symmetric write path low-risk. The only real cost centers are the new PATCH client + the trigger-model choice.
