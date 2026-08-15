# Aspect spec — Write-back config API routes

**Feature:** `intercom-writeback` (prd.md R7 + S1) · **Aspect:** `config-api-routes`

## Problem slice

Operators need a programmatic + UI surface to flip the opt-in toggle and read the
write-back's honest state. Today the Intercom router has exactly three routes
(`intercom_integration.py`: POST `/connect` :272, GET `/status` :407, DELETE
`/disconnect` :423 — all `require_admin_or_owner`).

## In-scope

- `PATCH /api/v1/integrations/intercom/writeback` in
  `services/backend-api/src/api/routes/intercom_integration.py`
  (`require_admin_or_owner`, 404 when no connection for the org):
  - Request `{enabled: bool, action?: "note_only"|"note_and_close"}`, `extra="forbid"`,
    Pydantic model (422 on invalid action / unknown fields).
  - Persists on the token-paste `IntercomIntegration` row (the per-org row). If the
    org's connection is the legacy OAuth row (write-only), return 409 with an honest
    message (or 422 — decide in plan; the OAuth row has no writeback columns, so the
    toggle must not silently write nowhere).
  - No backfill-on-enable (prd.md OQ2) — flipping on does not touch existing resolved
    items. Explicit.
- `GET /api/v1/integrations/intercom/status` extended: return
  `writeback_enabled`, `writeback_action`, `last_writeback_at`, `last_writeback_status`,
  `last_writeback_error` (never the token; existing fields unchanged).
- `POST /api/v1/integrations/intercom/writeback/test` (S1): live probe — resolves the
  credential, calls `fetch_admin_id` (or a cheap `GET /me`), optionally performs a
  no-op-safe check; returns `{ok: bool, reason?: str}`. Must not send notes or close
  anything. 404 if no connection.
- Validation contract mirror: the CRM writeback routes
  (`hubspot_integration.py:517-585`, `salesforce_integration.py:821-890`) — 422 shapes,
  `require_admin_or_owner`, no plan gate.

## Out of scope

- The task, guards, marker (worker-writeback-task).
- Frontend card (frontend-writeback-card aspect consumes these routes).
- Backfill-on-enable; configurable target status (prd.md OQ1/OQ2).
- Changing the connect/disconnect/status routes beyond extending the status payload.

## Acceptance criteria (testable)

1. PATCH: 404 (no connection), 422 (invalid action, unknown field, missing `enabled`),
   200 + persisted columns (round-trip via GET /status).
2. Enabling does not enqueue or send anything (no task dispatch; no HTTP call to
   Intercom) — assert with mocks.
3. GET /status returns the five new fields; existing fields byte-identical
   (characterization).
4. POST /writeback/test: 200 `{ok: true}` with valid credential; `{ok: false, reason:
   missing_write_scope|auth_error|no_admin}` paths; performs zero mutation (no note,
   no close — mocked client asserts no reply/parts calls).
5. Legacy-OAuth-connection org gets a clean 409/422 (honest, not silent).
6. Backend suite green.

## Dependencies & sequencing

- Needs `db-config-model` (columns) and the client probe (`worker-write-client` —
  though `/writeback/test` runs backend-side: it needs the backend's own validation
  path or a backend probe; check whether the backend minimal client can probe scope —
  the connect-time `GET /me` validation already exists backend-side; reuse it).
- Sequence before the frontend card.

## Open questions / risks

- Scope probing is approximate: Intercom's `/me` does not report scopes. The honest
  probe is an empty note attempt — but that mutates. S1 is therefore a credential
  check (`{ok, reason}` on token validity + admin resolution), with scope errors only
  discovered on first real write-back (recorded as `missing_write_scope`). State this
  honestly in the route's response shape (no false "write scope OK" claim).
- Where the probe lives: backend route calling the backend's Intercom client vs
  dispatching the worker task. Lean backend-side (connect validation precedent).
