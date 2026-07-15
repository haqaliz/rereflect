# Aspect spec — public-taxonomy-crud

**Parent PRD:** `../prd.md` (M2) · **Slug:** `public-api-crud-v3`

## Problem slice & outcome

A public API key can manage the org's custom categories programmatically, mirroring the internal
`/api/v1/categories/custom` CRUD, with a delete/rename warning when the name is referenced by an automation rule.

## In scope

- `GET /api/public/v1/categories` (`read` scope) — list, optional `?category_type=`, org-scoped.
- `POST /api/public/v1/categories` (`write`) — `{name (1–100), description?, category_type ∈ pain_point|feature_request|urgency|general}`; 201; **409 on dup (org, type, name)**.
- `PATCH /api/public/v1/categories/{id}` (`write`) — `{name?, description?, is_active?}` (type not editable); 404 missing; 409 rename collision.
- `DELETE /api/public/v1/categories/{id}` (`write`) — hard delete (204) + `X-Rereflect-Warning` header when the name is referenced by a `feedback_category_match` automation rule (OQ2 resolved: header).
- Public request models use `extra="forbid"`.

## Out of scope

- Max-count limit (internal has none — no divergence).
- Cascade/rewrite of orphaned feedback strings or rules (warning only).
- Frontend changes.

## Acceptance criteria (testable)

1. Scope enforcement: GET needs `read`, writes need `write` (403 otherwise); 401 on bad key.
2. Create dup `(org, type, name)` → 409; valid → 201 with body.
3. Invalid `category_type` → 422; unknown field → 422 (`extra="forbid"`); name length bounds enforced.
4. Org scoping: PATCH/DELETE another org's category id → 404.
5. PATCH rename to an existing name → 409; `category_type` in body → 422 (not editable).
6. DELETE existing → 204; if name is rule-referenced, response carries `X-Rereflect-Warning`.
7. No regression: internal `/api/v1/categories/custom` behavior unchanged (characterization-locked if shared logic is extracted).

## Dependencies & sequencing

- Reuses `custom_categories` model + internal validation logic (`categories.py`) — extract shared create/update/delete
  helpers so public + internal share one implementation (characterization-lock internal first).
- Reuses the automation-rule lookup used by `feedback_category_match` for the warning.
- Independent of bulk-feedback-write; can run in parallel.

## Risks

- The rule-reference lookup must be cheap and org-scoped; if no rule engine query helper exists, add a small read-only one.
