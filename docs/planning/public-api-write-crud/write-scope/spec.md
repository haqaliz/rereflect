# Aspect Spec — `write-scope`

**Parent PRD:** `../prd.md` · **Slug:** `public-api-write-crud`

## Problem slice & user outcome
The public API has no `write` scope. Register a new `write` scope end-to-end so operators can *grant* it on an API key and see it documented, before any write endpoint uses it. Outcome: a user creates a key with the `write` scope from the UI; the backend accepts it; the docs list it.

## In-scope
- **Backend allowlist:** add `"write"` to `_VALID_SCOPES` (`services/backend-api/src/api/routes/api_keys.py:31`). [observed]
- **Backend docs strings:** scope sentence in the OpenAPI `info.description` (`public_api.py:610–611`) and the module docstring scope table (`public_api.py:8–11`); inline comment on `models/api_key.py:22`. [observed]
- **Frontend type:** `ApiKeyScope` union → add `| 'write'` (`services/frontend-web/lib/api/api-keys.ts:5`). [observed]
- **Frontend picker:** add `'write'` to the scope array (`app/(dashboard)/settings/api-keys/page.tsx:152`); replace the binary read-vs-else description ternary (`:167–171`) with a 3-way lookup so `write` gets its own copy; add a `write` color entry to `ScopeBadge` (`:53–65`). [observed]
- **User docs:** `docs/API.md` — update the scope list (`:76–77`) and the "read-only" description (`:68`). [observed]

## Out of scope
- The PATCH endpoint itself (aspect `feedback-write-endpoint`).
- Per-resource scopes (single flat `write`, per PRD decision).
- Any DB migration (scopes is a free-form comma `String(100)` — no schema change). [observed]

## Acceptance criteria (testable)
- Creating an API key with `scopes=["write"]` (or `["read","write"]`) succeeds and persists `write` in the comma list. [testable: `test_api_keys.py`]
- Creating a key with an unknown scope still 422s (regression). [testable]
- `GET /api/public/v1/openapi.json` `info.description` mentions the `write` scope. [testable]
- Frontend: `ApiKeyScope` typechecks with `'write'`; the create dialog renders a `write` checkbox with its own description; `ScopeBadge` renders a non-default color for `write`. [testable: `npm run test` + `lint`]
- `docs/API.md` no longer calls the API "read-only" and lists `write`.

## Dependencies & sequencing
- No dependency on `feedback-write-endpoint`; can land first. The endpoint aspect *requires* the allowlist entry here for `require_scope("write")` to be grantable, so **this aspect must merge/complete before the endpoint is exercised end-to-end** (though they can be developed in parallel).

## Open questions / risks
- Low risk. Only subtlety: the description ternary must become a 3-way map or `write` inherits the `ingest` copy — captured above.
