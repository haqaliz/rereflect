# Aspect Spec — `feedback-write-endpoint`

**Parent PRD:** `../prd.md` · **Slug:** `public-api-write-crud`

## Problem slice & user outcome
A `write`-scoped API key can `PATCH /api/public/v1/feedback/{id}` to (a) change `workflow_status` and (b) submit a category/sentiment correction — through the **same internal code paths** the dashboard uses, org-scoped. Outcome: closed-loop automation from an operator's own tooling.

## In-scope
- **Shared status-change helper.** Extract the mutation core of `workflow.py:137 change_status` into a reusable function (e.g. `workflow_service.apply_status_change(db, feedback, new_status, actor_id|None, resolution_note, organization_id)`) that: validates against `VALID_STATUSES` (`workflow.py:25`), sets `workflow_status`, records `create_workflow_event(...)` (`workflow_service.py:15`), invalidates cache, dispatches the `feedback.status_changed` webhook + WS event. The internal route calls the helper too — **behavior byte-for-byte unchanged** (characterization test first). [observed]
- **Shared correction helper.** Extract the `AICorrection` creation from `ai_corrections.py:102 submit_correction` into a reusable function (e.g. `create_ai_correction(db, org_id, user_id|None, correction_type, entity_type, entity_id, signal, original_value, corrected_value, feedback_text)`). Internal route calls it too. [observed]
- **Public route** `PATCH /api/public/v1/feedback/{feedback_id}` behind `require_scope("write")` in `public_api.py`:
  - Org-scoped fetch-then-404 (idiom @ `public_api.py:244–253`). [observed]
  - `PublicFeedbackUpdate` request model (mirror `PublicFeedbackCreate` @ `:73`); all fields optional; **empty body → 400**.
  - `workflow_status` (+ optional `resolution_note`) → shared status helper. `actor_id=None` (API key, no user); event/webhook still fire. Invalid status → 400.
  - Category/sentiment correction → shared correction helper: `correction_type ∈ {category, sentiment}`, `entity_type='feedback_item'`, `entity_id={id}`, `signal='correction'`, `original_value=<current stored value>`, `corrected_value=<new>`, `user_id=None`, org from `auth.organization_id`. **Record-only — does NOT mutate the stored `*_category`/`sentiment_label` column.** [observed]
  - **Idempotency:** setting `workflow_status` to its current value is a **no-op skip** — no timeline event, no webhook (locked decision). [decided]
  - Returns the updated `PublicFeedbackItem` (`public_api.py:45`).

## Out of scope
- `tags` / `is_urgent` manual edits (no internal precedent — v2). [observed]
- Mutating the stored category/sentiment column (record-only). [decided]
- `assigned_to` (nice-to-have; only if trivially free after the status helper lands).
- Customer/category-taxonomy CRUD, bulk writes, DELETE.
- The `write` scope registration itself (aspect `write-scope`).

## Acceptance criteria (testable)
- **Characterization (RED first):** existing internal `change_status` and `submit_correction` behavior captured by tests that stay green after the refactor. [testable]
- `PATCH .../feedback/{id}` with `write` key + `{"workflow_status":"resolved"}` → 200, updated item; a `FeedbackWorkflowEvent` row created; `feedback.status_changed` webhook dispatched; cache invalidated. [testable]
- Same PATCH with the status already `resolved` → 200 **no-op**: no new event, no webhook. [testable]
- PATCH with a category correction → 200; one `AICorrection` row (`signal='correction'`, correct `original_value`/`corrected_value`); the feedback's stored `pain_point_category` is **unchanged**. [testable]
- Invalid `workflow_status` → 400; empty body → 400; unknown correction field → 400. [testable]
- `read`/`ingest`-only key → 403. Cross-org `feedback_id` → 404 (not 403). Non-existent id → 404. [testable]
- Internal (JWT) `change_status` and `submit_correction` endpoints behave identically post-refactor. [testable — regression]
- Backend `pytest tests/ -v` green (scope to relevant files; note the known pre-existing `test_report_ws.py` full-suite segfault — do not treat as a regression).

## Dependencies & sequencing
1. Characterization tests on internal routes (RED capturing current behavior).
2. Extract shared helpers; internal routes delegate (GREEN, characterization stays green).
3. Add the public PATCH route + request model (TDD).
4. Requires the `write` scope from aspect `write-scope` to be in `_VALID_SCOPES` for the end-to-end 403/200 tests.

## Open questions / risks
- **R1 (primary):** divergent write paths. Mitigation: shared helpers + characterization gate (must be green before and after).
- **OQ2:** correction wire format — flat (`category_correction_field` + `category_correction_value`) vs nested object. **Recommend nested** `{"correction": {"field": "...", "corrected_value": "..."}}` for clarity; finalize in `tech-plan`.
- `actor_id=None` path through `create_workflow_event`/webhook must be verified to not assume a user (nullable FK / optional actor).
