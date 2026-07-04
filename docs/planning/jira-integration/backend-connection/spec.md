# Aspect Spec — backend-connection

**Parent PRD:** `../prd.md` · **Aspect dir:** `backend-connection/`

## Problem slice & outcome

The foundation of the Jira integration: an operator can connect one Jira Cloud site per org with a
pasted **email + Atlassian API token** (Basic auth), have it validated + encrypted + stored, and
check/test/disconnect it. Nothing downstream (create-issue, source type, frontend) can be built
without this. Outcome: `POST /connect` → `connected: true` + `token_hint`; token never leaves the DB.

## In scope

- **Models** (`services/backend-api/src/models/jira_integration.py`, registered in `src/models/__init__.py`):
  - `JiraIntegration` (table `jira_integrations`, one row/org): `id`, `organization_id`
    (`UniqueConstraint("organization_id", name="uq_jira_integrations_org_id")`, FK→organizations
    CASCADE per repo norm), `site_url`, `email`, `api_token` (Text, **Fernet-encrypted**),
    `token_hint` (String(8)), `account_id` (nullable, from `/myself`), `display_name` (nullable),
    `is_active` (Boolean default True), `connected_by_user_id` (FK→users SET NULL), `connected_at`,
    `last_synced_at`, `last_sync_status` (String(50)), `last_error` (Text), `created_at`, `updated_at`.
  - `FeedbackJiraIssue` (table `feedback_jira_issues`): `id`, `organization_id`, `feedback_id`
    (FK→feedback_items CASCADE), `jira_issue_id`, `jira_issue_key`, `jira_issue_url`,
    `jira_issue_title`, `created_by_user_id`, `created_at`. Indexes on `feedback_id`, `organization_id`.
    (Defined here so the migration creates both tables at once; **used** by `backend-create-issue`.)
- **Alembic migration** (`alembic/versions/*_add_jira_integration_tables.py`): creates both tables +
  the unique constraint + indexes. `down_revision` = current head. **Keep it clean** — no unrelated
  auto-generated `alter_column` noise (Linear's migration has some; do not replicate).
- **`JiraClient`** (`src/services/jira_client.py`): constructed with `(site_url, email, api_token)`;
  HTTP Basic auth (`httpx` `auth=(email, api_token)`) against `https://{site}.atlassian.net/rest/api/3`.
  Slice-1 methods needed here: `validate()` → `GET /myself` (returns account id/display name).
  (The `get_projects`/`get_issue_types`/`create_issue` methods are added by `backend-create-issue`,
  but define the class + error taxonomy here.) Custom errors mirroring HubSpot:
  `JiraTransientError` (429/5xx), `JiraAuthError` (401/403), `JiraNotFoundError` (404). Never log the token.
- **Routes** (`src/api/routes/jira_integration.py`, prefix `/api/v1/integrations/jira`), all under
  `Depends(require_admin_or_owner)`:
  - `POST /connect` `{site_url, email, api_token}`: normalize `site_url` (accept `acme`,
    `acme.atlassian.net`, `https://acme.atlassian.net`, trailing slash → canonical
    `https://acme.atlassian.net`); `validate()` **before** storing; `encrypt_api_key` (catch
    `ValueError` when `LLM_ENCRYPTION_KEY` unset → **HTTP 422**, not 500); `get_key_hint`; upsert by
    org (reconnect **reuses the same row**, rotates token + hint, sets `is_active=true`). Response =
    metadata only; `api_token` **never** included.
  - `GET /status`: `{connected, site_url, email, token_hint, account_id, display_name, is_active,
    last_synced_at, last_sync_status, last_error, connected_at}` or `{connected: false}`.
  - `DELETE /disconnect`: **soft** (`is_active=false`); **preserves** `feedback_jira_issues`. Do NOT
    call any CRM purge.
  - `POST /test`: decrypt stored token, re-`validate()`, return `{success, message}`; **never 500**.
  - `get_decrypted_token(integration)` module helper (mirror HubSpot) for the create-issue aspect.
- **Router registration**: `include_router(jira_integration.router)` in `src/api/main.py`.
- **Unlocked gate**: add `"jira_integration": "free"` mapping in `src/config/plans.py` (+ include in
  the free plan feature list) so any `require_feature("jira_integration")` is a no-op. Keep RBAC.
- **NOT a CRM**: do not call/extend `crm_integration_common.another_crm_active`; Jira coexists with CRMs.

## Out of scope (this aspect)

- Any create-issue / projects / issuetypes endpoints (→ `backend-create-issue`).
- Worker model mirror / sync task / beat (none needed in slice 1).
- Frontend, landing, source-type enum.

## Acceptance criteria (testable — TDD)

- `test_jira_models.py`: both tables/columns exist; `uq_jira_integrations_org_id` enforced (second
  active row for same org fails); `FeedbackJiraIssue` FK/index present; models importable + in `__init__`.
- `test_jira_client.py`: client instantiates, stores creds, targets `https://{site}.atlassian.net/rest/api/3`,
  uses Basic auth; `validate()` happy path (mocked httpx) returns account info; 401/403 → `JiraAuthError`,
  429/5xx → `JiraTransientError`.
- `test_jira_connection.py`: `POST /connect` with valid (mocked) token → `connected:true` + `token_hint`,
  token absent from response body, row encrypted (stored ≠ plaintext); invalid token → **422**;
  `LLM_ENCRYPTION_KEY` unset → **422**; site_url normalization variants all canonicalize; reconnect
  reuses the row + rotates token; `GET /status` reflects state; `DELETE /disconnect` sets `is_active=false`;
  `POST /test` returns success/failure without 500; **works on a Free-plan org** (unlocked).
- Mock the client at the route module (`patch("src.api.routes.jira_integration.JiraClient")`),
  `unittest.mock` — the repo's Linear/HubSpot test pattern.

## Dependencies & sequencing

First aspect. Blocks `backend-create-issue`, `source-type-registration` (needs `/status`), and `frontend`.

## Open questions / risks

- `organization_id` FK vs no-FK: repo is mixed (Linear uses FK CASCADE; HubSpot no-FK). Pick **FK
  CASCADE** (Linear) since no worker mirror needs the no-FK relaxation here.
- Site normalization must reject a non-`atlassian.net` host cleanly (422) to keep slice-1 Cloud-only.
