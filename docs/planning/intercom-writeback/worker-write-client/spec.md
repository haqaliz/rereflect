# Aspect spec — Worker Intercom write client

**Feature:** `intercom-writeback` (prd.md R8) · **Aspect:** `worker-write-client`

## Problem slice

The write-back needs outbound Intercom calls with the worker's proper error taxonomy.
Today the only implementation is the orphaned backend `intercom_service.py`
(`add_note_to_conversation`, `close_conversation`, `get_admin_id`), which swallows every
`httpx.HTTPError` into a bare `bool`/`None` — it cannot distinguish 401/403 (scope) from
404 (already closed) from 429 (retryable). It must be deleted (P2 wire-or-delete
decision, prd.md R8) and its behavior ported into the worker's `IntercomClient`
(`services/worker-service/src/clients/intercom.py`), which already has the taxonomy:
`IntercomError` / `IntercomAuthError` / `IntercomTransientError`
(`src/clients/intercom.py:29-43`).

## In-scope

- Add to worker `IntercomClient`:
  - `add_note(conversation_id: str, admin_id: str, body: str)` — POST
    `https://api.intercom.io/conversations/{id}/reply`, body
    `{"message_type": "note", "type": "admin", "admin_id": ..., "body": ...}`.
  - `close_conversation(conversation_id: str, admin_id: str)` — POST
    `/conversations/{id}/parts`, body
    `{"message_type": "close", "type": "admin", "admin_id": ...}`.
  - `fetch_admin_id()` — GET `/me`, returns `data["id"]` (admin fallback when the
    stored `admin_id` is absent).
  - Error contract: 401/403 → `IntercomAuthError`; 429/5xx → `IntercomTransientError`;
    **404 must be distinguishable** — a distinct `IntercomNotFoundError` (or a
    documented sentinel) so "conversation already closed / not found" is a noop, not an
    error. Match the client's existing transport injection pattern (injectable
    `httpx.Client`/transport for tests, per `clients/intercom.py:46-54`).
  - Timeouts: follow the existing client defaults.
- Delete `services/backend-api/src/services/intercom_service.py` entirely (it is only
  imported by tests — verified by grep 2026-08-14).
- Port the service tests from `services/backend-api/tests/test_intercom.py:590-684`
  (mocked-httpx note/close/admin-id tests) into the worker suite as
  `test_intercom_client_writeback.py` (or the client's existing test file), updated to
  the new error contract: 403 → `IntercomAuthError`, 404 → not-found sentinel,
  429 → `IntercomTransientError`, plus the add-note/close body + URL assertions.
- Remove the orphaned tests from `test_intercom.py`; confirm nothing else imports
  `intercom_service` (sweep with grep across both services).
- Update stale references: the `intercom_service` mention in DEV-TRACKING P2 is handled
  by the docs aspect; check for any comment/import referencing the deleted module.

## Out of scope

- The task itself, guards, marker writes (worker-writeback-task aspect).
- Backend-side client changes (backend keeps its minimal validation client).
- `response_sender.send_via_intercom` (separate surface, prd.md N3/out-of-scope).

## Acceptance criteria (testable)

1. `intercom_service.py` no longer exists; grep across `services/` finds zero imports.
2. `IntercomClient.add_note` / `close_conversation` / `fetch_admin_id` exist with the
   error contract above; tests assert: URL + body shape, 401/403 → `IntercomAuthError`,
   404 → distinguishable not-found, 429/5xx → `IntercomTransientError`, transport
   injection works.
3. Worker suite green; backend suite green (with the ported-out tests removed from
   `test_intercom.py`).

## Dependencies & sequencing

- Needs nothing from other aspects. Sequence before `worker-writeback-task` (task uses
  the client methods).
- Independent of `db-config-model`.

## Open questions / risks

- Intercom's exact 404 semantics for note-on-closed vs close-of-closed conversations:
  treat both as the same not-found sentinel (the task maps it to a noop).
- Whether `fetch_admin_id` should raise `IntercomAuthError` on 401/403 like `/me`
  validation in the backend — yes, consistent with the connect-time validation behavior.
