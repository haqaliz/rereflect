# Aspect Spec — predict-seam (worker / analysis at ingest)

**Service:** `services/worker-service/src/{services/classifier_resolver.py, tasks/analysis.py}`.
**Sequence:** after data-and-config (reads `urgency_classifier_mode`) and worker-trainer (a promoted model
must exist to resolve). Highest-stakes aspect — it can overwrite `feedback.is_urgent`.

## Problem slice / outcome

At ingest, the resolved per-org urgency model conditionally overrides the keyword heuristic's
`feedback.is_urgent`, gated by `urgency_classifier_mode`: `off` = untouched heuristic; `shadow` = predict
and log/store the shadow result but keep the heuristic value; `auto` = overwrite `is_urgent` with the
model's prediction.

## In scope

- `resolve_classifier(org_id, classifier_type="urgency", db)` call site in `analysis.py` alongside the
  existing sentiment/category resolves (`analysis.py:432,435,614,617` pattern), reading the urgency mode
  via `MODE_COLUMN_BY_CLASSIFIER_TYPE["urgency"]`.
- Apply logic mirroring sentiment/category:
  - resolve → if a model is active and mode ∈ {shadow, auto}, `predict(artifact, feedback.text)` →
    `label ∈ {"urgent","not_urgent"}` → `is_urgent_pred = (label == "urgent")`.
  - `auto`: **add-only** — set `feedback.is_urgent = True` only when `is_urgent_pred` is True and the
    heuristic said False (escalation). NEVER set it False when the heuristic said True (no de-escalation
    this pass). So `auto` = `is_urgent_heuristic OR is_urgent_pred`.
  - `shadow`: do NOT change `feedback.is_urgent`; log/store the shadow prediction as the other heads do
    (log BOTH directions, incl. would-be de-escalations, for future evaluation).
  - `off` / no active model: leave the keyword heuristic result (`feedback.py:112` equivalent) intact.
- Ensure this runs AFTER the keyword heuristic sets the baseline value, so `off` is byte-identical to today.

## Out of scope

- Recording a correction from the model's own prediction (only user overrides create corrections —
  capture-seam).
- Downstream churn-alert/urgent-queue logic — they read `is_urgent` and need no change.

## Acceptance criteria (testable, TDD)

- `off`: `is_urgent` equals the pure keyword-heuristic result; no model call applied. Byte-identical to
  pre-feature behavior (characterization test).
- `shadow`: `is_urgent` unchanged from heuristic; the shadow prediction is produced/logged as
  sentiment/category shadow does.
- `auto` (add-only): when the model predicts `"urgent"` and the heuristic said False → `is_urgent==True`
  (escalation applied). When the model predicts `"not_urgent"` and the heuristic said True →
  `is_urgent==True` stays (NO de-escalation). Add an explicit test for the no-de-escalation guard.
- No active model in shadow/auto → falls back to heuristic (no crash, no override).
- Org-scoped: an org with mode `auto` does not affect another org's ingest.

## Dependencies / sequencing

Depends on **data-and-config** (mode column + resolver map) and **worker-trainer** (a promoted model to
resolve). Build last among backend/worker aspects.

## Risks

- **R-2 high-stakes override** — `is_urgent` feeds churn alerts + urgent-feedbacks. The `auto` test must
  prove operator opt-in is the only path to overwrite; default `off` never touches the value.
- Sequencing bug: applying the override before the heuristic baseline would make `off` diverge. Assert
  ordering in a test.
