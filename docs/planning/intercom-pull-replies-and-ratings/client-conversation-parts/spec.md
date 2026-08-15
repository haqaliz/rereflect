# Aspect spec — Client conversation-parts access

**Feature:** `intercom-pull-replies-and-ratings` (prd.md R1) · **Aspect:** `client-conversation-parts`

## Problem slice

The pull needs the conversation's reply parts + rating. Search results carry only the
first message (`test_intercom_sync.py:89-107` fixture shape). The client
(`services/worker-service/src/clients/intercom.py`) has no parts access — the only
live conversation-detail GET lives in `adapter.fetch_context` with its own httpx client
(unreachable for token-paste sources, not transport-injectable).

## In-scope

- Verify (plan task 0) which response shape the API actually returns:
  - **R1a (primary):** `POST /conversations/search` with `display_as: "conversation_parts"` —
    parts + rating ride along in the search response (no fan-out).
  - **R1b (fallback):** new `get_conversation(conversation_id)` → `GET /conversations/{id}`,
    parsed per the shape already consumed by `adapter.fetch_context` (conversation_parts
    array, rating object).
- Implement whichever is real via `IntercomClient` (instance method, injectable
  transport, existing taxonomy: IntercomAuthError / IntercomTransientError /
  IntercomNotFoundError). If R1a, extend `search_conversations` with the
  `display_as` parameter (default unchanged — existing contract pinned by
  `test_intercom_sync.py:152-175`).
- Pin the verified shape with `httpx.MockTransport` tests in the client's test style.

## Out of scope

- Extraction/merge logic (adapter aspect), sync-task integration (pull-enrichment),
  re-analysis (reanalysis-seam).

## Acceptance criteria (testable)

1. The plan's task 0 verification is recorded (real response shape cited, or the
   documented shape adopted with the decision).
2. The client exposes parts+rating access (search param or detail method) with the
   taxonomy contract; tests assert URL/body, 401/403 → AuthError, 429 → TransientError
   with Retry-After, 404 → NotFoundError (R1b only).
3. Existing `search_conversations` contract tests pass unchanged (defaults preserved).
4. Worker suite green.

## Dependencies & sequencing

- First aspect: the adapter + pull-enrichment aspects consume the verified payload shape.
- No dependencies on other aspects.

## Open questions / risks

- The `display_as` value may need to be a query param vs body field — whatever the API
  documents. If neither R1a nor R1b can be verified from docs, the plan falls back to
  R1b with the per-run cap (prd.md R5) and states the assumption.
