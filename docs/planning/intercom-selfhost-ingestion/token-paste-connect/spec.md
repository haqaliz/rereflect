# Aspect Spec — `token-paste-connect`

**Feature:** `intercom-selfhost-ingestion`
**PRD:** `../prd.md` (requirements **R2**, **R6**; decisions **D1**, **D4**, **D6**)
**Date:** 2026-07-31
**Size:** M (new model + migration + 3 routes + auto-provisioning)
**Depends on:** `envelope-seam-fix` (shipped — without it a connected org still ingests nothing)

---

## Problem slice

Intercom connect is OAuth-only. `routes/integrations.py:981-984` returns **403 "Intercom
OAuth is not configured. Set INTERCOM_CLIENT_ID environment variable"**, and a self-hoster
has no documented way past it short of registering a public OAuth app.

Every other BYO-credential integration deliberately chose token-paste because OAuth was
judged *"awkward for self-host"*: HubSpot (private-app token), Zendesk (agent email + API
token), Jira (Atlassian API token), Asana (PAT). **Intercom is the only holdout.**

Intercom's own documentation designates exactly this path for exactly this case: *"An
Access Token is for if you're using the API to access data in your own Intercom workspace,
in other words, building a private app"*, and *"We provide you with an Access Token as soon
as you create an app on your workspace"* (Developer Hub → Configure → Authentication). So
token-paste is not a workaround here — it is the vendor's intended mechanism.

## Why the client secret is collected at connect time

The operator must create a Developer Hub app to obtain the Access Token. **That same app
carries the `client_secret`** (Basic Info page) which is the key Intercom uses to sign
`X-Hub-Signature` on webhook deliveries. Collecting it here — encrypted, per-org — is what
lets a later aspect (`webhook-per-org-secret`) verify signatures **per tenant** instead of
against one global env var, dissolving the limitation recorded in the 1.0.0 changelog:
*"A valid signature cannot identify a tenant here."*

It is collected in this aspect and **stored only**. Nothing reads it until
`webhook-per-org-secret`. It is optional on the request so an operator who only wants the
pull path is not forced to hand over a secret they will not use.

## In scope

1. **`IntercomIntegration` model** — one row per org, mirroring `ZendeskIntegration`:
   `organization_id` (unique), `access_token` (Fernet), `client_secret` (Fernet, nullable),
   `token_hint`, `workspace_id`, `workspace_name`, `admin_id`, `is_active`,
   `connected_by_user_id`, `connected_at`, `last_synced_at`, `last_sync_status`,
   `last_error`, `created_at`, `updated_at`.
2. **One Alembic migration**, chained off the live-verified head `12a1003fbfe0`.
3. **`POST /api/v1/integrations/intercom/connect`** — validate the token against
   `GET https://api.intercom.io/me`, derive `workspace_id` (`app.id_code`),
   `workspace_name` and `admin_id`, encrypt and upsert by org, auto-provision the
   feedback source. 422 on invalid token, 502 on transient upstream, 422 when
   `LLM_ENCRYPTION_KEY` is unset.
4. **`GET /status`** and **`DELETE /disconnect`** (soft-delete: `is_active=False`).
5. **Auto-provisioned `FeedbackSource`** with `triggers={"new_conversations": True}` (R6).
6. **RBAC**: `dependencies=[Depends(require_admin_or_owner)]` on all three routes.
7. **D6 guard**: one Intercom connection per org, symmetric across both credential paths —
   connecting via token-paste while an active OAuth `Integration(type="intercom")` exists
   is rejected, and vice versa.

## Out of scope

- **`POST /sync-now`** — belongs to `pull-sync`; there is no pull task to trigger yet.
- Reading the `client_secret` for verification — `webhook-per-org-secret`.
- The frontend page — `frontend-intercom-page`.
- Docs/changelog truth-up — `cleanup-and-docs`.
- Encrypting the **legacy** OAuth tokens on `Integration` (`DEV-TRACKING.md:402`) — needs a
  backfill migration; separate card. The new table is encrypted from birth.
- Adding RBAC to `routes/integrations.py` (`DEV-TRACKING.md:422`) — separate card. These
  new routes enforce it; they must not inherit that module's omission.

## The trap this aspect must not fall into (R6)

`adapters/intercom.py:42-57` returns a trigger match **only** when one of
`all_conversations` / `new_conversations` / `replies` / `ratings` is truthy. A
`FeedbackSource` auto-provisioned with `triggers={}` drops every delivery silently — the
source looks connected and ingests nothing, which is the *same* failure mode as the
envelope defect, reached from a third direction.

Zendesk hit this and documented the fix inline (`zendesk_integration.py:346-352`). This
aspect must seed a trigger **and** pin it with a test, not merely set it.

## Acceptance criteria

| # | Criterion | Verification |
|---|---|---|
| B1 | Valid token → connected, workspace resolved from `/me` | Route test with mocked client |
| B2 | Invalid token → 422, nothing persisted | Route test |
| B3 | Transient upstream error → 502, nothing persisted | Route test |
| B4 | Both secrets stored Fernet-encrypted; neither ever returned or logged | Test asserts ciphertext in DB and absence from the response body |
| B5 | Missing `LLM_ENCRYPTION_KEY` → 422, not a 500 | Route test |
| B6 | Reconnect upserts one row, does not duplicate | Test connects twice, asserts one row |
| B7 | Auto-provisioned source carries a truthy trigger and ingests | Test asserts `triggers["new_conversations"] is True` |
| B8 | `member` role → 403 on all three routes | Route tests |
| B9 | Cross-path conflict rejected in both directions (D6) | Two tests |
| B10 | Disconnect soft-deletes and leaves the FeedbackSource alone | Route test (Zendesk's decoupling precedent) |
| B11 | Single alembic head after the migration | **Live** `alembic heads` |

## Risks

| Risk | Mitigation |
|---|---|
| `/me` response shape assumed | The existing OAuth callback already parses it (`integrations.py:1066-1072`, `app.id_code`) — reuse that reading, do not invent one |
| A second credential path widens the tenancy surface | The discriminator change is `tenancy-discriminator`'s job; this aspect only *stores* `workspace_id`. Do not touch `_find_matching_sources` here |
| Migration id collision | Chain off the **live-verified** head; never grep version files for `down_revision` — that has caused a fabricated fork and an id collision in this repo |
