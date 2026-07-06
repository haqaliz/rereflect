# Aspect Spec — docs-openapi

**Feature:** public-api-write-v2 · **Aspect:** `docs-openapi`

## Problem slice & outcome

The public API docs, OpenAPI description, and tracking accurately describe the expanded `write` surface (tags/is_urgent edits + DELETE).

## In scope

- `public_api.py:8-12` module scope table — expand the `write` line to mention tags/is_urgent edits + DELETE.
- `public_api.py:753-758` `info.description` — same.
- `public_api.py:334-339` PATCH `description=` — mention tags/is_urgent (may be done in `patch-tags-urgent`; owned here if not).
- The new DELETE route's `summary`/`description`.
- `docs/API.md` — document the new PATCH fields (tags replace/[]=clear semantics, validation caps), the non-atomicity note, and `DELETE /feedback/{id}` (204, write scope, org-scoped).
- `AI-TRACKING.md:288` write-scope bullet + changelog entry — mark tags/is_urgent/DELETE shipped.

## Out of scope

- Any code behavior; frontend.

## Acceptance criteria

1. OpenAPI (`GET /api/public/v1/openapi.json` or the docs route) reflects the new fields + DELETE verb.
2. `docs/API.md` describes each new capability with an example request/response.
3. No stale claim that the write API is "PATCH-only" or "status + corrections only".

## Dependencies & sequencing

- **Last** — after `patch-tags-urgent` + `public-delete-feedback` land, so docs match shipped behavior. Small; the integrator may fold parts into the earlier aspects' commits.

## Risks

- Low. Keep the doc examples consistent with the actual validation (max 20 tags / 50 chars).
