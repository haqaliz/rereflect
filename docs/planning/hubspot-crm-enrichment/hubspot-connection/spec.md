# Aspect Spec — hubspot-connection

**Parent PRD:** `../prd.md` · **Slug:** `hubspot-crm-enrichment`

## Problem slice & user outcome

An org-admin connects their own HubSpot portal by pasting a private-app access
token, can test it, see connection status (with last-synced time + a token hint,
never the token), and disconnect. This is the foundation aspect — `hubspot-sync`
and the enrichment store depend on the connection + decrypted token.

## In scope

- **Model `HubSpotIntegration`** (backend-api `src/models/`), one row per org:
  `organization_id` (unique), `access_token` (Text, **Fernet-encrypted** via
  `encrypt_api_key`), `token_hint`, `hub_id`, `portal_name`, `connected_by_user_id`,
  `connected_at`, `is_active`, `last_synced_at`, `last_sync_status`, `last_error`,
  `contacts_synced`, `contacts_matched`. Registered in models `__init__`.
- **Alembic migration** (backend-api `alembic/`) creating `hubspot_integrations`
  (this aspect owns the migration head; `crm-health-component` and `hubspot-sync`
  add their tables/columns to the **same** migration or a chained one — sequencing
  note below).
- **Routes** `src/api/routes/hubspot_integration.py`, prefix
  `/api/v1/integrations/hubspot`, included in `src/api/main.py`:
  - `POST /connect` — body `{ access_token, arr_property_name? }`; validates the
    token against HubSpot (`GET /account-info/v3/details` or contacts ping),
    stores encrypted, returns status (no token).
  - `DELETE /disconnect` — deactivate/delete the row.
  - `GET /status` — `{ connected, portal_name, last_synced_at, last_sync_status,
    last_error, token_hint, contacts_matched }`.
  - `POST /test` — re-validate stored token, return ok/error.
  - All gated `Depends(require_admin_or_owner)` + `Depends(require_feature("hubspot_integration"))`
    (register `hubspot_integration` in `src/config/plans.py`; no-op unlock self-hosted).
- **Token decryption helper** reused by `hubspot-sync` (export a
  `get_decrypted_token(integration)` or mirror `src/utils/byok.py`).
- **Frontend:** `lib/api/hubspot.ts` (`hubspotAPI = { getStatus, connect, disconnect,
  testConnection }`, mirror `lib/api/linear.ts`); HubSpot tile in
  `app/(dashboard)/settings/integrations/page.tsx` (+ status in the `fetchData`
  `Promise.allSettled`); detail page `app/(dashboard)/settings/integrations/hubspot/page.tsx`
  with a `type="password"` token `Input` (mirror webhook `new/page.tsx` form +
  `api-keys` masking), connect/test/disconnect, `isAdminOrOwner` redirect guard.

## Out of scope (this aspect)

- The actual contact/company/deal pull and `crm_enrichment` table → `hubspot-sync`.
- Health component, profile card, timeline events → other aspects.
- OAuth flow, bi-directional sync (PRD out-of-scope).

## Acceptance criteria (testable)

- `POST /connect` with a valid token stores an **encrypted** `access_token`
  (DB value ≠ plaintext; `decrypt_api_key` round-trips) and returns 200 without the
  token in the body. `token_hint` ends with the last 4 chars.
- `POST /connect` with an invalid token returns 4xx and stores nothing.
- `GET /status` reflects connected/disconnected; never returns `access_token`.
- `DELETE /disconnect` makes `GET /status` report disconnected.
- A `member`-role user gets 403 on connect/disconnect/status/test
  (role-matrix fixtures like `tests/test_health_weights.py`).
- All queries scoped by `organization_id`; a second org cannot see the first's
  connection.
- Frontend: token input is masked; non-admins redirected; connect calls
  `hubspotAPI.connect`.

## Dependencies & sequencing

- **Foundation — build first.** No dependency on other aspects.
- Owns the initial Alembic migration. Coordinate with `crm-health-component`
  (adds `crm_component` + `health_weight_crm`) and `hubspot-sync` (adds
  `crm_enrichment`) so migrations chain cleanly off one head (tech-plan decides:
  one combined migration vs. chained per-aspect).
- HubSpot token validation needs a minimal HubSpot client call — may share the
  `hubspot-sync` client module (coordinate to avoid duplication).

## Open questions / risks

- Token validation endpoint choice (account-info vs contacts ping) — pick the
  cheapest authenticated GET.
- Whether `arr_property_name` config lives here (connect body) or in sync settings —
  lean: accept it here, store on the integration row.
