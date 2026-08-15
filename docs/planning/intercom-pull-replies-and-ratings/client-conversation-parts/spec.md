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

## Task 0 decision record (2026-08-15)

**Adopted shape: R1b** — `get_conversation(conversation_id)` → `GET /conversations/{id}`.
R1a was verified against Intercom's published OpenAPI specification. The docs site is
client-rendered, but it is served its spec from a machine-readable file:
`https://developers.intercom.com/page-data/shared/oas-docs/references/@2.16/rest-api/api.intercom.io.yaml.json`
(the page's `sharedDataIds.openAPIDocsStore`). Cross-checked spec versions @2.10, @2.12,
@2.14, @2.15 and @2.16 — all agree on every fact below.

| # | Fact to verify (R1a) | Verdict | Source (URL cited) |
|---|---|---|---|
| 1 | `display_as` is a top-level body field of `POST /conversations/search` | **FAIL** — the `search_request` schema has only `query` + `pagination`; `display_as` appears nowhere on the `searchConversations` operation in any spec version (2.10–2.16) | `https://developers.intercom.com/docs/references/rest-api/api.intercom.io/Conversations/searchConversations/` (spec: `paths./conversations/search.post` → `components.schemas.search_request`) |
| 2 | `"conversation_parts"` is a documented value | **FAIL** — the only documented `display_as` value is `plaintext` (a query param on `GET`/`PUT /conversations/{id}`, "Set to plaintext to retrieve conversation messages in plain text") | same spec: `paths./conversations/{conversation_id}.get.parameters[2]` |
| 3 | Response keeps `conversations[]` + `pages.next.starting_after` | **PASS** — `conversation_list` (`conversations[]` + `total_count` + `pages`), `pages` → `cursor_pages` → `next` → `starting_after_paging`; confirmed by the operation's own 200 example | same spec: `components.schemas.conversation_list`, `cursor_pages`, `starting_after_paging` |
| 4 | Items carry `conversation_parts.conversation_parts[]` | **FAIL** — the search item schema `conversation_list_item` has no `conversation_parts` key; only the detail `conversation` schema carries it | same spec: `components.schemas.conversation_list_item` vs `conversation` |

> **Adopted shape: R1a ☐ / R1b ☑** — stated assumption: detail `GET /conversations/{id}`
> per conversation, capped by the pull-enrichment aspect (prd.md R5). The plan's
> decision rule ("any fact failing or unfindable → R1b") applies: facts 1, 2 and 4 fail
> against the published spec.
>
> **Honesty caveat (recorded per plan Phase 2, final-authority note):** the machine-readable
> spec is known-incomplete — the shipped client's `sort` body key is likewise absent from
> `search_request` yet works in production — so absence from the spec is strong but not
> absolute proof that the live API rejects `display_as: "conversation_parts"` on search.
> The Phase 2 real-app smoke check remains the final authority; if the live shape differs,
> the pull-enrichment aspect can still adopt R1a without touching this client.
>
> **Additional verified facts (R1b side):** the detail `conversation` schema carries
> `conversation_parts` (`conversation_parts.conversation_parts[]` — the exact key path
> `adapter.fetch_context` already consumes, adapters/intercom.py:221) and a nullable
> `conversation_rating` object (`{rating, remark, created_at, updated_at, contact, teammate}`).
> The 200 example confirms part fields `id`, `part_type` (e.g. `comment`), `body`,
> `created_at`, `author`. The detail endpoint documents a **hard 500-part cap** (the 500
> most recent parts) — relevant to pull-enrichment R5.
>
> **Flag for the adapter aspect + smoke-check item 4:** the spec names the rating key
> `conversation_rating` (nullable), not the plan's assumed top-level `rating`. The client
> fixtures pin the plan's cross-aspect shape (top-level `rating`) per the §4 contract; the
> live response arbitrates. No client behavior depends on it — the client is
> shape-transparent.
