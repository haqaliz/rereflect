# Aspect: predict-seam

**Slice:** apply a promoted category model at ingest — shadow on backend, authoritative-auto on worker —
by reading the per-type mode and routing the predicted label to the right category field.

## Problem slice & outcome
`apply_classifier_override` already threads `classifier_type` but hard-writes `sentiment_label/score`.
Add a category branch and wire the call-sites + the per-type mode read, honoring byte-stability when the
mode is off/shadow.

## In scope (both `services/backend-api/src/services/` and `services/worker-service/src/services/` mirrors)
- `classifier_resolver.py`: `resolve_classifier(org_id, classifier_type, db)` must read the **per-type**
  mode — `classifier_mode` for `sentiment`, `category_classifier_mode` for `category` (currently reads the
  single field at `:78`). Keep returning None for off/missing/unrecognized.
- `classifier_predict.py` `apply_classifier_override(...)`:
  - Category branch: on `auto`+`allow_override`, write `feedback.pain_point_category` **or**
    `feedback.feature_request_category`, chosen by which built-in vocab the predicted label belongs to.
    **Unambiguous-routing rule (critique #1 — no silent mis-write):** override only when the label is in
    exactly **one** built-in vocab; a label in **neither** (custom category) or **both** is shadow-logged
    only, never written to a guessed field.
  - **Bypass `score_from_proba`** for category (no signed axis); do not write a sentiment score.
  - Shadow-mode logging reads the incumbent category field, not `sentiment_label`.
  - `load_active_classifier` already generic on `classifier_type` — no change.
- Call-sites:
  - Backend shadow-only: add `apply_classifier_override(feedback, db, classifier_type="category",
    allow_override=False)` in `routes/feedback.py` right after the categorizer block (`~:147`, before/beside
    the existing sentiment call at `:156-159`).
  - Worker authoritative-auto: add the category call beside the two sentiment call-sites in
    `tasks/analysis.py:427-429` and `:604-606` with `allow_override=True`.

## Out of scope
- Migration/config field creation (→ data-and-config). Engine spine (→ category-core). Trainer (→ worker-trainer).

## Acceptance criteria (testable)
- `category_classifier_mode='off'` (or no active model) → category fields byte-identical to today
  (characterization test on the ingest path).
- `='shadow'` → an eval/log signal is produced but stored `pain_point_category`/`feature_request_category`
  are unchanged.
- `='auto'` with an active category model whose top label ∈ **exactly** pain-point vocab →
  `feedback.pain_point_category` is overwritten; label ∈ exactly feature vocab → `feature_request_category`;
  label in **neither or both** → no category field written (shadow-logged only); no sentiment field/score is
  ever touched.
- Sentiment override behavior byte-unchanged (existing seam tests green; both types resolve independently).
- Cross-service parity: backend and worker `apply_classifier_override` behave identically for category
  (shared characterization).

## Dependencies & sequencing
**Blocked by:** data-and-config (mode column), category-core (predict/label vocab). Build after both.

## Open questions / risks
- Built-in vocab import location: reuse `analyzer/categorizer.py` category name sets; keep the routing
  table in one shared spot to avoid drift between backend and worker mirrors.
