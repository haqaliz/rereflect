# PRD — Public API Write Expansion v2 (tags, is_urgent, DELETE)

**Slug:** `public-api-write-v2` · **Branch:** `feat/public-api-write-v2` · **Type:** feat (freeform)
**Date:** 2026-07-07 · **Builds on:** slice 1 `public-api-write-crud` (merged 2026-07-06, commit `20ac3ae`)
**Status:** Draft for review gate

---

## Problem Statement

The public REST API's write surface is half-open. Slice 1 added a `write` scope and `PATCH /api/public/v1/feedback/{id}` that can move `workflow_status` and record record-only category/sentiment corrections. But an operator driving Rereflect from their own systems still **cannot**, via API key:

- **tag / re-tag** a feedback item (curate a taxonomy, add a triage label),
- **flag / unflag urgency** (`is_urgent`), or
- **delete** a feedback item (remove a bad import, a test row, or PII on request).

For an **open-source, self-hosted** product, programmatic **delete** is not a nice-to-have — it's the erasure primitive operators expect (right-to-be-forgotten, cleaning a botched bulk import). Today the only path is the JWT dashboard, which defeats automation.

**Evidence it's real:** these three edits are named as explicit deferred-v2 items in the slice-1 PRD (`docs/planning/public-api-write-crud/prd.md:57-64`). The `write` scope, key UI, and mutation plumbing already exist — this is the unblocked next slice, not new infrastructure.

## Goals & Success Metrics

**Goal:** an operator with a `write`-scoped API key can fully curate and remove a feedback item from their own systems — matching what the internal dashboard already allows, minus the deliberately deferred analyzer-column mutation.

| Metric | Target |
|---|---|
| New endpoints/verbs | `PATCH` gains `tags` + `is_urgent`; new `DELETE /feedback/{id}` |
| DB migrations | 0 (columns already exist) |
| Regression on slice-1 behavior | 0 — `workflow_status` + `correction` paths byte-identical (characterization-gated) |
| Internal DELETE behavior change | 0 — refactor onto shared helper, characterization-gated |
| Test coverage | New TDD tests for each field + DELETE (happy, clear, validation-422, scope-403, cross-org-404, idempotent-404) |
| Plan gating | None (OSS, all unlocked) |

## User Personas & Scenarios

- **Self-hosting operator / platform engineer.** Runs a script that reconciles Rereflect against their own DB: sets `is_urgent` on items matching an SLA rule, applies a house tag taxonomy, and deletes rows flagged as spam/test. Uses one `write` key.
- **Data/ML tinkerer.** From a notebook, bulk-relabels tags on a slice of feedback to prep a training set (single-entity calls in a loop; bulk endpoint is out of scope).
- **Compliance/erasure.** On a deletion request, an ops job calls `DELETE /feedback/{id}` for every item tied to a customer email.

## Requirements

### Must-have

1. **`PATCH /feedback/{id}` accepts `tags`** (list of strings) — **replace** semantics. Switch `PublicFeedbackUpdate` to `model_fields_set`/`exclude_unset` so:
   - `tags` **omitted** → unchanged
   - `tags: []` → **clears** all tags
   - `tags: ["a","b"]` → replaces the full array
2. **`PATCH /feedback/{id}` accepts `is_urgent`** (bool) — set/unset; omitted → unchanged. Manual override persists (only re-analysis would recompute it; a plain PATCH does not trigger re-analysis).
3. **Tag validation:** trim whitespace; drop duplicates (preserve first-seen order); reject non-string / empty elements → `422`; cap **20 tags**, element length **≤ 50 chars** → `422` on violation.
   - **Unknown fields → `422`:** set `model_config = {"extra": "forbid"}` on `PublicFeedbackUpdate` so a consumer typo (`tag` vs `tags`) is rejected loudly rather than silently no-oping. (Verify this doesn't break existing slice-1 callers — characterization test covers it.)
4. **`DELETE /api/public/v1/feedback/{id}`** → `204 No Content`, gated by **only** the existing `write` scope (independent of `read` — a write-only key can delete). Mirrors the internal single-delete exactly: org-scoped load → `404` if absent → delete → **archive the customer's health record if this was their last feedback** → cache invalidate → `feedback:deleted` event.
5. **Org scoping:** every new operation filters `organization_id == auth.organization_id`; cross-org id → `404` (indistinguishable from nonexistent — no tenant leak).
6. **`JSON` change-tracking correctness:** assigning `tags` **must** rebind a new list object (or `flag_modified(fb, "tags")`) before commit, with a regression test proving the write persists.
7. **Widened "Nothing to update" guard:** a PATCH carrying only `tags` and/or `is_urgent` must be accepted (current `:347` guard rejects it).
8. **Slice-1 parity preserved:** `workflow_status` + `correction` behavior unchanged; internal `delete_feedback` behavior unchanged after refactor — both characterization-gated before any change.

### Should-have

9. **`tags` echoed in the response** — add `tags: Optional[list[str]]` to `PublicFeedbackItem` so PATCH returns the updated set.
10. **Docs/OpenAPI updated:** the module scope table (`public_api.py:8-12`), `info.description` (`:753-758`), the PATCH `description=` (`:334-339`), `docs/API.md`, and the write-scope bullet in `AI-TRACKING.md:288` (+ changelog) to describe tags/is_urgent edits + DELETE.
11. **Best-effort side effects** on tag/urgency change: the standard `cache_invalidate` pair; optionally `emit_event("feedback:updated")` for real-time parity — never fail the write on a side-effect error (slice-1 try/except pattern).

### Nice-to-have (not this slice)

- Real-time `feedback:updated` event tuned per-field; a webhook event for tag/urgency edits (status change already emits a webhook; tag/urgency have no webhook event type today — leave as-is).

## Technical Considerations

**Single service: `services/backend-api`.** No frontend/worker/analysis-engine change; no migration.

**Endpoints (FastAPI):**
- `PATCH /api/public/v1/feedback/{feedback_id}` — extend `PublicFeedbackUpdate` + `public_update_feedback` (`public_api.py:304-437`). Gate unchanged (`require_scope("write")`).
- `DELETE /api/public/v1/feedback/{feedback_id}` — new route, `require_scope("write")`, `status_code=204`.

**Shared-helper extraction (mirrors slice-1 commit `7345f02`):**
- Extract `delete_feedback_item(db, fb, *, org_id) -> None` (or returning archived-flag) from `feedback.py:497-550` into a service (e.g. `src/services/feedback_service.py` or reuse an existing module). Encapsulates delete + health-archive-on-last + cache invalidate + `feedback:deleted` emit. Refactor the internal route onto it **first**, under a characterization test, then call it from public DELETE. Note: mirror the **single**-delete (no `SlackAlertLog` nulling — that's bulk-only; internal single-delete works today without it).

**Data model:** `FeedbackItem.tags = Column(JSON, nullable=True)`, `is_urgent = Column(Boolean, default=False)` — both already present (`models/feedback.py:22-23`). No Alembic change.

**Multi-tenancy:** `auth.organization_id` from `ApiKeyAuth` (`public/auth.py:49`); all queries scoped by it.

**Validation location:** Pydantic validator on `PublicFeedbackUpdate.tags` (trim/dedupe/cap/type) so bad input is `422` before touching the DB.

## Risks & Open Questions

| Risk | Mitigation |
|---|---|
| **`JSON` in-place mutation silently no-ops** (agent-confirmed trap) | Rebind new list / `flag_modified`; regression test asserts persisted value after re-fetch. Must-have #6. |
| Clear-vs-omit ambiguity confuses consumers | `model_fields_set` semantics, documented explicitly (`[]` clears, omit untouched). Confirmed design decision. |
| Refactoring internal delete introduces a regression | Characterization test on `delete_feedback` (204, row gone, health-archive) **before** extraction; RED→GREEN. |
| DELETE + FK to `SlackAlertLog` | Internal single-delete already works without nulling refs → mirror it exactly; add a test with an alert-logged item to confirm no FK error. |
| `is_urgent` manual override later clobbered by re-analysis | Documented behavior: a plain PATCH doesn't re-analyze; re-analysis (separate action) recomputes. Not a v1 concern; note in docs. |
| Non-atomic multi-field PATCH (status + tags commit separately) | Carry slice-1's documented non-atomicity note; low harm (append-only signals / idempotent field sets). |

**Open questions:** none blocking. (Whether to also emit a `feedback:updated` real-time event on tag/urgency change is a should-have, decided during planning.)

**Atomicity — decided:** a combined PATCH (`workflow_status` + `tags` + `is_urgent` + `correction`) is **non-atomic and best-effort**, carried from slice 1. Field mutations commit; a failing status-change *side effect* (e.g. webhook down) never rolls back the field writes and never fails the request. This is the intended behavior for an idempotent field-set API; documented in `docs/API.md`.

## Out of Scope (deferred again)

- Mutating the **stored** category/sentiment analyzer column (record-only corrections remain the path).
- Customer write/CRUD; category-taxonomy CRUD.
- **Bulk** write/delete endpoints (single-entity only).
- A separate `delete` scope (reuse the flat `write` scope).
- New webhook event type for tag/urgency edits.
- Any frontend change.

## Aspect Decomposition (proposed)

1. **`patch-tags-urgent`** — extend `PublicFeedbackUpdate` (model_fields_set, tags validator, is_urgent), apply inline with JSON-rebind + side effects, widen the guard, echo `tags` in response. Characterization-gate slice-1 status/correction first.
2. **`public-delete-feedback`** — extract `delete_feedback_item` helper, characterization-gate + refactor internal route, add public `DELETE` behind `write`.
3. **`docs-openapi`** — scope table, `info.description`, PATCH description, `docs/API.md`. (Small; may fold into aspect 1–2.)
