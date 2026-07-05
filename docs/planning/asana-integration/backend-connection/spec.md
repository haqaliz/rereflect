# Aspect: backend-connection

**Slice of:** Asana Integration slice 1. **Owner:** one backend engineer/agent.

## Problem slice & outcome
An operator connects their Asana account with a Personal Access Token and can test/disconnect it. This aspect delivers the model, migration, encrypted-token storage, the `AsanaClient` (auth + validate + workspace/project metadata), and the connect/status/disconnect/test routes. Mirror `jira_integration` minus the SSRF/subdomain machinery.

## In scope
- **Model** `src/models/asana_integration.py` → `AsanaIntegration` (`asana_integrations`): `organization_id` FK unique (`uq_asana_integrations_org_id`) + index, `api_token` (encrypted Text), `token_hint`, `account_gid`, `display_name`, `is_active`, `connected_by_user_id` (FK SET NULL), `connected_at`, `last_synced_at`, `last_sync_status`, `last_error`, `created_at`, `updated_at`. Register in `src/models/__init__.py` (import + `__all__`). (`FeedbackAsanaTask` belongs to the create-task aspect, but MAY be co-located in the same model file — coordinate so the migration covers both tables.)
- **Migration** `alembic/versions/{rev}_add_asana_integration_tables.py`, `down_revision = "z1a2b3c4d5e6"` (Zendesk head). Create `asana_integrations` (+ `feedback_asana_tasks` if co-created); `downgrade()` drops in reverse. Comment: repo has multiple heads; real `alembic upgrade head` needs `alembic merge heads` (out of scope).
- **Client** `src/services/asana_client.py`: `AsanaClient(api_token)`, `BASE_URL = "https://app.asana.com/api/1.0"`, `httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {api_token}"}, timeout=15.0, follow_redirects=False)`. Constant scheme/host assert helper. Token in `self._api_token`, never logged; `__repr__`/`__str__` omit it. Error taxonomy `AsanaError` / `AsanaAuthError` (401/403) / `AsanaTransientError` (429,5xx) / `AsanaNotFoundError` (404) via `_handle_response`. Methods: `validate()` → `GET /users/me` returns `{gid, name}`; `get_workspaces()` → workspaces list `[{gid,name}]`; `get_projects(workspace_gid)` → `GET /projects?workspace=` `[{gid,name}]`.
- **Routes** `src/api/routes/asana_integration.py`, `prefix="/api/v1/integrations/asana"`, every endpoint `Depends(require_admin_or_owner)` + org dep + `get_db`. Pydantic: `AsanaConnectRequest{api_token}`, `AsanaConnectResponse`, `AsanaStatusResponse`, `AsanaDisconnectResponse`, `AsanaTestResponse`, `AsanaWorkspaceResponse`, `AsanaProjectResponse` (none echo the token).
  - `POST /connect` → `validate()` (AuthError→422, TransientError→502) → `encrypt_api_key` (ValueError→422) → upsert by org (reconnect rotates token) → metadata only.
  - `GET /status` → `connected=False` when no active row.
  - `DELETE /disconnect` → soft (`is_active=False`), preserve `feedback_asana_tasks`.
  - `POST /test` → decrypt + `validate()`, always `{success,message}`, never 500.
  - `GET /workspaces`, `GET /projects?workspace_gid=` → decrypt + call client.
  - Helpers: `_get_active_integration`, `_require_active_integration`, `get_decrypted_token`, `_close_client`. (No `_normalize_site_url` / `_assert_host_not_ssrf` — fixed host.)
- **Register router** in `src/api/main.py` (import + `include_router`, near the Jira line).

## Out of scope
- `FeedbackAsanaTask` create-task route + duplicate/timeline logic (→ backend-create-task aspect).
- Any SSRF DNS gate (not applicable — fixed host).
- Source-type registration (→ its own aspect).

## Acceptance criteria (testable)
- `test_asana_models.py`: columns, unique org constraint, cascade/SET NULL, encrypted-not-plaintext round-trip.
- `test_asana_client.py`: base_url + Bearer header asserted; `validate/get_workspaces/get_projects` parse mocked responses; error taxonomy maps 401/403/404/429/5xx; token absent from `repr`/`str`. No real HTTP (`unittest.mock` on `httpx.Client`).
- `test_asana_connection.py` (TestClient): connect stores encrypted (never plaintext, never in response); missing `LLM_ENCRYPTION_KEY` → 422; auth-fail → 422; transient → 502; status reflects connected/disconnected; disconnect is soft; test endpoint never 500.

## Dependencies & sequencing
Foundational — build first. Blocks backend-create-task and frontend. Reuses `src/utils/encryption.py` unchanged.

## Open questions / risks
- Confirm Asana `/users/me` and `/workspaces` payload shapes against the live API (unit tests pin the assumed shape).
- Multiple alembic heads — chain from `z1a2b3c4d5e6`; merge is out of scope.
