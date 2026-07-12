# Aspect: client-batch-status

**Slug:** `zendesk-status-sync` · **Aspect dir:** `client-batch-status`
**Sequencing:** parallel with reconcile-core-and-model; needed by poll-task.

## Problem slice & outcome

Add the one genuinely-missing capability: fetch the current status of a set of Zendesk tickets by ID
in batches, reusing the existing auth + throttle behavior.

## In scope
1. `ZendeskClient.show_many(ids: list[int|str]) -> dict[str, str]` in `services/worker-service/src/clients/zendesk.py`:
   - `GET /api/v2/tickets/show_many.json?ids=1,2,3` → parse `tickets[]` → `{str(ticket_id): status}`.
   - Chunk ids ≤ 100 per request (Zendesk cap); aggregate across chunks.
   - Reuse existing `_handle_response`: 429 → `Retry-After` sleep → `ZendeskTransientError`; 5xx → transient; 401/403 → `ZendeskAuthError`; 404 → skip (ticket may be archived/deleted, not fatal).
   - Missing/absent ticket ids in the response are simply omitted from the returned dict (no error).
2. Basic auth / base URL / no-log-token behavior unchanged (reuse constructor).

## Out of scope
- Backend client mirror (`services/backend-api/src/services/zendesk_client.py`) — only add there if a route needs it (routes dispatch to the worker; likely not needed).
- Any reconcile/apply logic.

## Acceptance criteria (testable)
- `show_many(["1","2"])` issues `GET …/tickets/show_many.json?ids=1,2` and returns `{"1":"open","2":"solved"}` (mock transport).
- 250 ids → 3 chunked requests (100/100/50), results merged.
- Ticket id present in request but absent in response → omitted from result (no KeyError).
- 429 with `Retry-After: 3` → sleeps ~3s then raises `ZendeskTransientError` (assert via patched sleep).
- 401 → `ZendeskAuthError`; empty id list → no HTTP call, returns `{}`.

## Dependencies & sequencing
- None upstream. Blocks: poll-task (needs `show_many`).

## Open questions / risks
- Confirm Zendesk `show_many` returns `status` field without `include` params — it does (core ticket field).
- Deleted vs archived tickets: both simply absent → handled by omit-on-absent.
