# Aspect Spec — patch-tags-urgent

**Feature:** public-api-write-v2 · **Aspect:** `patch-tags-urgent`

## Problem slice & outcome

An operator with a `write` key can set a feedback item's `tags` and `is_urgent` via the existing `PATCH /api/public/v1/feedback/{id}`, in the same request that may also carry `workflow_status`/`correction`.

## In scope

- Extend `PublicFeedbackUpdate` (`services/backend-api/src/api/routes/public_api.py`) with `tags: Optional[list[str]]` and `is_urgent: Optional[bool]`, using `model_fields_set`/`exclude_unset` semantics + `model_config = {"extra": "forbid"}`.
- Tag validator: trim, dedupe (first-seen order), reject non-string/empty → 422, max 20 tags, element ≤ 50 chars → 422.
- Apply inline in `public_update_feedback`: `is_urgent` plain assign; `tags` **rebind a new list** (JSON change-tracking) or `flag_modified(fb, "tags")`; `db.commit()`.
- Widen the "Nothing to update" guard to include tags/is_urgent.
- Add `tags: Optional[list[str]]` to `PublicFeedbackItem` response.
- Best-effort side effects on tag/urgency change: `cache_invalidate` pair + `emit_event("feedback:updated", {"id": fb.id})`.

## Out of scope

- Mutating stored category/sentiment; DELETE (separate aspect); docs (separate aspect, though PATCH `description=` string may be touched here).

## Acceptance criteria (testable)

1. `tags: []` clears; omitted `tags` leaves unchanged; `tags: [...]` replaces — verified after re-fetch (proves JSON persistence).
2. `is_urgent: true/false` sets; omitted leaves unchanged.
3. Dedupe + trim applied; `>20` tags or `>50`-char element → 422; non-string element → 422.
4. Unknown field (`tag`) → 422 (`extra="forbid"`).
5. PATCH with only tags and/or is_urgent → 200 (guard widened), not 400.
6. Slice-1 behavior byte-identical: status change, correction, combined, no-op same-status, read-key 403, ingest-key 403, cross-org 404, invalid status 422 — all still pass.
7. Response echoes updated `tags`.

## Dependencies & sequencing

- **First:** characterization test run of `tests/test_public_api_write.py` must be green before edits (baseline). `extra="forbid"` change must not break existing slice-1 request shapes — confirm via that suite.
- Independent of `public-delete-feedback`; can run in parallel.

## Risks

- JSON in-place mutation no-op (must rebind list). `extra="forbid"` could reject a currently-accepted field — verify against slice-1 tests.
