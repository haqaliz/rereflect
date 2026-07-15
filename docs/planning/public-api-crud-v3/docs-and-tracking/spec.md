# Aspect spec — docs-and-tracking

**Parent PRD:** `../prd.md` (M4) · **Slug:** `public-api-crud-v3`

## Problem slice & outcome

Ship the docs/tracking that every prior public-API slice shipped, so the two new capabilities are discoverable
and the roadmap reflects reality.

## In scope

- Public-API OpenAPI description text / `docs/SELF_HOSTING.md`: document `POST /feedback/bulk` + the taxonomy CRUD routes.
- `CHANGELOG.md`: add an entry under the working version.
- `AI-TRACKING.md`: update the line-292 v2 deferral (bulk writes + taxonomy CRUD now shipped).
- `DEV-TRACKING.md`: mark the same.
- `docs/planning/_card/` remains the pipeline record (no action).

## Out of scope

- Frontend docs pages, marketing/landing copy.

## Acceptance criteria

1. `/api/public/v1/docs` (Swagger) shows the bulk + taxonomy routes with accurate request/response schemas
   (auto from FastAPI — verify, don't hand-write).
2. `SELF_HOSTING.md` + `CHANGELOG.md` + `AI-TRACKING.md` + `DEV-TRACKING.md` updated and internally consistent.

## Dependencies & sequencing

- **Last** aspect — depends on the final shipped shapes of bulk-feedback-write + public-taxonomy-crud.
