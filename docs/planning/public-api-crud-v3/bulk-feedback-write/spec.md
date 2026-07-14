# Aspect spec — bulk-feedback-write

**Parent PRD:** `../prd.md` (M1) · **Slug:** `public-api-crud-v3`

## Problem slice & outcome

A `write`-scoped public API key can update `workflow_status` / `tags` / `is_urgent` (and optionally record a
`correction`) for up to 500 feedback items in **one** request, and gets a **per-item result** for every id.

## In scope

- `POST /api/public/v1/feedback/bulk` (`write` scope).
- Request `{ ids: int[] (1..500, deduped), patch: <same fields+validators as PublicFeedbackUpdate> }`.
- Uniform patch applied to every matched id.
- Org-scoped: ids not in the org are **skipped** (not errors).
- `workflow_status` applied via **one** `apply_status_change` call on the whole matched set (batched-atomic);
  `tags`/`is_urgent`/`correction` applied per item; **non-contagious** (a per-item error doesn't roll back others).
- Batch-level side effects done **once**: cache invalidation, `feedback.status_changed` webhook per changed
  item, `workflow:status_changed` event with all changed ids.
- Response 200: `{ matched, updated, skipped, results: [{id, status, reason?}] }` where
  `status ∈ updated|noop|skipped|error`, ordered by deduped input order.
- Should-have: `?count_only=true` → `{ matched }` only, no mutation.

## Out of scope

- Heterogeneous per-id patches, filter-selector, bulk delete (PRD N1/N2).
- Per-field result granularity (OQ6 resolved: per-item is sufficient — see PRD OQ6).
- Mutating stored category/sentiment column.

## Acceptance criteria (testable)

1. `write` scope required (403 without); missing/revoked key → 401.
2. `ids` empty → 422; `>500` → 422 (reject, no truncation); duplicate ids deduped (one result each).
3. `patch` with no mutating field → 422 ("Nothing to update"); unknown field → 422 (`extra="forbid"`).
4. Cross-org / non-existent id → `results[i].status="skipped"`, `reason="not_found"`; not counted in `updated`.
5. `[good, good, bad]` → `matched=2, updated=2, skipped=1`; the 2 good persisted; response `results` has 3 entries.
6. Same-value status + no other field change → `status="noop"` (counted as success, not error).
7. Status change fires one `feedback.status_changed` webhook per changed item + one `workflow:status_changed`
   event; cache invalidated once. Same-status items don't fire.
8. `count_only=true` returns `{matched}` and mutates nothing.
9. No regression: existing single `PATCH /feedback/{id}` behavior byte-identical (characterization-locked if
   any shared helper is refactored).

## Dependencies & sequencing

- Reuses `apply_status_change` + `dispatch_status_webhooks` (`workflow_service.py`), `create_ai_correction`,
  the `PublicFeedbackUpdate` validators (extract/share the tag validator + field set).
- Register the static `/feedback/bulk` route **before** parametric `/feedback/{id}` (FastAPI ordering).
- First aspect; independent of taxonomy CRUD.

## Risks

- Commit choreography: `apply_status_change` doesn't commit (caller does), but `create_ai_correction` commits
  internally — for bulk, avoid per-correction commits or accept append-only multi-commit. Pin in plan.
- Non-contagion mechanism: per-item `db.begin_nested()` savepoint around per-item field writes.
