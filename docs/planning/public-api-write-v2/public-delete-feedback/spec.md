# Aspect Spec — public-delete-feedback

**Feature:** public-api-write-v2 · **Aspect:** `public-delete-feedback`

## Problem slice & outcome

An operator with a `write` key can delete a feedback item via `DELETE /api/public/v1/feedback/{id}`, with the same side effects as the internal dashboard delete.

## In scope

- **Extract** `delete_feedback_item(db, fb, *, org_id)` from the internal `delete_feedback` handler (`services/backend-api/src/api/routes/feedback.py:497-550`) into a service module (e.g. `src/services/feedback_service.py`, or an existing suitable module). It encapsulates: `db.delete(fb)` + commit → customer-health archive-on-last-feedback → `cache_invalidate` pair → `emit_event("feedback:deleted", {"id": id})`.
- **Refactor** the internal route onto the helper (behavior byte-identical, characterization-gated).
- **Add** `DELETE /api/public/v1/feedback/{feedback_id}` in `public_api.py`: `require_scope("write")`, `status_code=204`, org-scoped load → 404 if absent → call helper → return None.

## Out of scope

- Bulk delete; `SlackAlertLog` nulling (internal single-delete doesn't do it — mirror exactly); a separate `delete` scope.

## Acceptance criteria (testable)

1. `DELETE` with write key → 204, row gone.
2. Nonexistent id → 404; cross-org id → 404 (no tenant leak).
3. Read-key → 403; ingest-key → 403; write-only key (no read) → 204 (delete allowed).
4. Deleting the customer's last feedback archives their `CustomerHealth` row; non-last does not.
5. Deleting an item that has a `SlackAlertLog` reference does not raise an FK error (mirrors internal).
6. Internal `test_feedback.py` delete tests still green after refactor (204, not-found, unauthorized, customer-archive test in `test_customer_analyze_archive.py`).

## Dependencies & sequencing

- **Characterization-gate the internal delete first** (baseline green), then extract helper + refactor internal route (tests stay green), then add public route + its tests.
- Independent of `patch-tags-urgent`; can run in parallel (different concern; both touch `public_api.py` — sequence the file edits or let integrator merge).

## Risks

- Refactor regression on the internal route → characterization test guards it.
- `emit_event` is async; the extracted helper must be `async def` and awaited from both call sites.
