# Aspect Spec — capture-seam (backend + frontend)

**Services:** `services/backend-api/src/{api/routes/feedback.py, api/routes/public_api.py, services/ai_correction_service.py}`,
`services/frontend-web/` (feedback detail page + API client).
**Sequence:** can start immediately (parallel to urgency-core). No dependency on the model existing —
this makes signal accrue first.

## Problem slice / outcome

Every user-driven change to a feedback item's urgent flag is recorded as a training signal
(`AICorrection(correction_type="urgency")`), from BOTH the dashboard and the public API. Without this the
urgency head has nothing to learn from.

## In scope

### Backend — internal (JWT)
- Add a way for a dashboard user to toggle a single feedback item's `is_urgent`. Options for the plan:
  (a) new `PATCH /api/v1/feedback/{id}/urgent` endpoint, or (b) extend the existing feedback update.
  Prefer a dedicated, minimal endpoint to avoid entangling the text-edit-and-reanalyze flow at
  `feedback.py:636-665`.
- On a user-driven change where new `is_urgent` ≠ stored value, call
  `create_ai_correction(db, organization_id=<org>, user_id=<current user>, correction_type="urgency",
  entity_type="feedback_item", entity_id=fb.id, signal="correction",
  original_value=str(old_is_urgent), corrected_value="urgent" | "not_urgent", feedback_text=fb.text)`.

### Backend — public API
- In `public_update_feedback` (`public_api.py`, is_urgent block ~473-483), before overwriting `fb.is_urgent`,
  compare to stored value; if changed, emit the same urgency correction (mirror the sentiment/category
  emit at `public_api.py:456-471`; `user_id=None` for API-key actor). Extend `_resolve_correction` or emit
  inline.

### Frontend
- Add an urgent-flag control on the feedback detail page (`app/(dashboard)/feedbacks/[id]/page.tsx`,
  near the existing `handleCorrectionSubmit` at `:271-288`) that calls the new internal endpoint.
- API client function for the toggle.

## Out of scope

- Bulk urgent toggling.
- Capturing the analyzer's own heuristic set/clear (`feedback.py:112` initial set, `:665` clear-before-reanalyze)
  — these are analyzer-driven, **must not** produce corrections.
- Urgent toggle on the urgent-feedbacks list page (N-1, nice-to-have).

## Acceptance criteria (testable, TDD)

- Internal toggle endpoint: org-scoped (cross-org → 404), sets `is_urgent`, and on value change inserts
  exactly one `AICorrection(correction_type="urgency", signal="correction", corrected_value=...)` with the
  acting user's id. No-op when value unchanged → no correction row.
- Public API PATCH: changing `is_urgent` inserts one urgency correction (`user_id=None`); unchanged → none;
  the existing `correction` field behavior is unaffected (characterization test stays green).
- Analyzer re-analyze path (`update_feedback`) does NOT create urgency corrections.
- Frontend: toggling the control calls the endpoint and reflects new state; test with mocked API.
- `corrected_value` is exactly `"urgent"` or `"not_urgent"` (matches `URGENCY_LABELS`).

## Dependencies / sequencing

Independent of urgency-core (only shares the label string convention). Land early so corrections accrue.

## Risks

- **R-5**: guard strictly on *user-driven value change*. Add a test that the analyzer heuristic path emits
  no correction.
- Keep `corrected_value` vocabulary exactly aligned with `URGENCY_LABELS` — a mismatch silently drops all
  rows in `build_urgency_dataset`. Consider a shared constant / cross-service test.
