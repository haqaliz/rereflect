# Aspect Spec — salesforce-connection

**PRD:** `../prd.md` · **Build order: aspect 2 of 4.** Migration chains off `crm-provider-generalization`.

## Problem slice & outcome
An admin/owner connects their Salesforce org via web-server OAuth (mirroring Linear) and can see status / test / disconnect. Credentials are stored encrypted; only one CRM may be active per org.

## In scope
- **Model** `salesforce_integrations` (backend `src/models/salesforce_integration.py` + worker mirror): `organization_id` (no FK, `UniqueConstraint`), `refresh_token` (Text, Fernet-encrypted), `instance_url`, `sf_org_id`, `token_hint`, `connected_by_user_id`, `connected_at`, `is_active`, `last_synced_at`, `last_sync_status`, `last_error`, `contacts_synced`, `contacts_matched`, timestamps. Register in `models/__init__.py`.
- **Migration** `down_revision = <crm-provider-generalization rev>`.
- **Route** `src/api/routes/salesforce_integration.py`, prefix `/api/v1/integrations/salesforce`, all `require_admin_or_owner` + `require_feature("salesforce_integration")`:
  - `GET /connect-url` → `{auth_url}` (Salesforce authorize URL with `response_type=code`, scopes `refresh_token offline_access api`, the configured redirect URI, and a signed `state`). Mirror `linear_integration.py` getConnectUrl.
  - `GET /callback` (or `POST`) → exchange `code` for `refresh_token` + `access_token` + `instance_url`; encrypt + upsert; validate the token with a lightweight call (`GET {instance_url}/services/oauth2/userinfo` or `/services/data`).
  - `GET /status`, `DELETE /disconnect` (soft: `is_active=False`, **and purge**: delete this org's `crm_enrichment` rows where `provider='salesforce'` via a shared helper `purge_crm_enrichment(db, org_id, provider)`, then recompute the affected customers' health scores so a disconnected CRM stops influencing scores — locked decision 7; apply the same helper to `hubspot_integration.py` disconnect for consistency), `POST /test` (refresh + probe, never 500), `POST /sync` (manual → `send_task("src.tasks.salesforce_sync.sync_salesforce_org", args=[integ.id])`, lazy celery app).
  - **One-CRM guard (symmetric, required):** add a shared helper `another_crm_active(db, org_id, exclude_provider)` (checks `hubspot_integrations` + `salesforce_integrations` for any `is_active` row that isn't `exclude_provider`). `salesforce` `connect-url`/`callback` return 409 if HubSpot is active; **also add the same check to `hubspot_integration.py`'s connect** so HubSpot connect returns 409 when Salesforce is active. Neither direction can create the collision.
- Reuse `src/utils/encryption.py` (`encrypt_api_key`/`decrypt_api_key`/`get_key_hint`) + R6 guard (missing `LLM_ENCRYPTION_KEY` → 422).
- Register router in `src/api/main.py`.
- **Plans:** add `"salesforce_integration"` to the 4 feature lists + `FEATURE_PLANS` in `src/config/plans.py` (mirror `hubspot_integration`; SELF_HOSTED unlocks anyway).
- **Config:** read Salesforce Connected App client id/secret + redirect URI + login base (`https://login.salesforce.com`) + API version from env.

## Out of scope
- The actual data sync (aspect 3).
- Frontend (aspect 4).
- JWT-Bearer / pasted-token auth (v2).

## Acceptance criteria (testable)
1. `GET /connect-url` returns a well-formed Salesforce authorize URL with the right scopes + a verifiable `state`; requires admin/owner.
2. `callback` with a mocked token exchange persists an encrypted `refresh_token` + `instance_url`; `access_token`/`refresh_token` never returned by any endpoint.
3. Connect blocked (409/422) when HubSpot is already active for the org.
4. `disconnect` sets `is_active=False`; `status` reflects it. **Purge:** after disconnect, this org's `crm_enrichment` rows with `provider='salesforce'` are gone and the affected customers' health scores are recomputed (mock the recompute; assert rows deleted + recompute invoked). HubSpot rows for the org are untouched.
5. `test` handles a mocked refresh failure as `{"success": false}` (never 500); missing encryption key → 422.
6. Backend suite green.

## Dependencies & sequencing
- After `crm-provider-generalization` (migration chain). Supplies its migration rev to `salesforce-sync`.
- Mock all Salesforce HTTP in tests.

## Risks
- OAuth `state` CSRF handling — sign/verify it.
- `invalid_grant` on refresh (revoked) → mark disconnected with a clear error (mainly exercised in sync, but the model/status should represent it).
