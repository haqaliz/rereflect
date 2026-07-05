# Aspect: backend-connection

**Slice:** The operator connects Zendesk via BYOK API token and Rereflect treats `zendesk` as a
selectable feedback-source type.

## In scope
- `ZendeskIntegration` model (mirror `JiraIntegration`): one row/org, unique on `organization_id`,
  Fernet-encrypted `api_token` (+ encrypted nullable `webhook_secret`), `subdomain`, `email`,
  `token_hint`, identity (`account_user_id`, `display_name`), `is_active`, `last_synced_at`,
  `last_sync_status`, `last_error`, `connected_by_user_id`, timestamps.
- Alembic migration `add_zendesk_integration_tables` — **resolve multiple heads first** (`alembic heads`;
  set correct `down_revision` or add a merge revision), matching `downgrade()`.
- `ZendeskClient` (`src/services/zendesk_client.py`, mirror `jira_client.py`): Basic auth
  `("{email}/token", api_token)`, base `https://{subdomain}.zendesk.com/api/v2`, `validate()` →
  `GET /users/me.json`; error classes (auth/transient/notfound); token-safe `__repr__`;
  `_assert_safe_site_url` (scheme https + host suffix `.zendesk.com`).
- Routes `src/api/routes/zendesk_integration.py`: `connect`/`status`/`disconnect`/`test`
  (mirror Jira shapes + Pydantic schemas), `require_admin_or_owner` + `get_current_org`.
  `_normalize_subdomain` (accept bare subdomain → `{sub}.zendesk.com`, reject non-`*.zendesk.com`),
  `_assert_host_not_ssrf` (`getaddrinfo` reject loopback/private/link-local). Generate + return the
  webhook secret on connect (display once).
- Register router in `src/api/main.py`.
- Source-type registration in `src/api/routes/feedback_sources.py`: add `zendesk` `SourceTypeInfo`
  to `/types` (`requires_integration=False`) + `"zendesk"` in `valid_types`.
- **Source auto-provision (PRD 9a option a):** on successful connect, auto-create a default
  `zendesk` `FeedbackSource` for the org (matched by subdomain) if none exists, so ingestion flows
  without a separate wizard step. `status` reflects whether a source exists.

## Out of scope
- Any ingestion (adapter, pull, webhook) — separate aspects.
- Frontend.

## Acceptance criteria (testable — mirror `test_jira_connection.py` / `test_jira_client.py` / `test_feedback_sources_jira.py`)
- Connect: 200 + fields; response never contains token; token stored **encrypted** (decrypt round-trips).
- Invalid token → 422, no row persisted; transient → 502; missing `LLM_ENCRYPTION_KEY` → 422 not 500.
- Subdomain normalization variants; reject non-`*.zendesk.com`; SSRF gate rejects private-resolving host, allows public.
- Reconnect reuses row + rotates token; status disconnected/connected; disconnect sets inactive.
- `zendesk` appears in `/types` and is accepted by `create_feedback_source`.

## Dependencies / sequencing
- **First aspect.** ingestion-core + frontend depend on the model, source-type reg, and client.
- Resolve Alembic heads before writing the migration.
