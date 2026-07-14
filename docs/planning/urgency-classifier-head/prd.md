# PRD — Per-Org Self-Improving Urgency Classifier Head

**Slug:** `urgency-classifier-head`
**Branch:** `feat/urgency-classifier-head`
**Status:** Draft (pending review gate)
**Source:** `rereflect-next` handoff (2026-07-13), freeform (no GitHub issue)
**Milestone:** M5.2 flywheel — 3rd head (after sentiment 2026-07-11, category 2026-07-11)

## Problem Statement

Rereflect flags urgent (churn-risk) feedback with a **static keyword+sentiment heuristic**
(`feedback.is_urgent = has_urgent_keyword and is_very_negative`, `feedback.py:112`). It never learns
from operator corrections. The other two analyzer outputs — sentiment and category — already have
**per-org self-improving classifier heads** (M5.2): when a user corrects the AI, the correction is
stored, a per-org model is retrained weekly, and it's promoted only if it beats the incumbent on the
org's own held-out data. Urgency is the conspicuous gap in that flywheel.

**Who has the problem:** self-hosted operators whose "urgent" definition diverges from the built-in
keyword list (e.g. a fintech where "chargeback" is urgent, a devtool where "data loss" is urgent). Today
they either live with false flags or edit code. The urgent flag drives churn alerts and the
urgent-feedbacks queue, so misfires are costly.

**Evidence it's real:** the flywheel is the product's flagship moat (AI-TRACKING M5.2), and the urgency
head is the explicitly named next slice — AI-TRACKING lines 366–367 v3 deferral: *"separate per-kind
heads (needs recording the corrected field on `AICorrection`), an urgency head, and multi-label per item."*

## Goals & Success Metrics

- **G1 — Close the flywheel loop for urgency.** Users can override the urgent flag, that override is
  recorded as an `AICorrection(correction_type="urgency")`, and it feeds a per-org urgency model.
- **G2 — Honest, gated promotion.** The per-org urgency model is promoted to shadow/auto only when it
  beats the existing keyword heuristic (the incumbent) on the org's held-out corrections — same bar as
  sentiment/category.
- **G3 — Full parity UX.** Operators control it from Settings → AI with an off/shadow/auto toggle and
  see an urgency accuracy card, identical in shape to the category head.

**Success metrics (measurable):**
- All new/changed code TDD-covered; backend/worker/analysis `pytest` green, frontend `npm run test` +
  `npm run lint` green.
- End-to-end: a recorded urgency correction → weekly retrain → challenger evaluated vs keyword incumbent
  → promoted only on `macro_f1_delta ≥ MARGIN` → in `auto`, ingest overrides `feedback.is_urgent`.
- Zero behavior change when `urgency_classifier_mode = 'off'` (default): the keyword heuristic is
  byte-identical to today.

## User Personas & Scenarios

- **Operator (owner/admin)** — sets `urgency_classifier_mode` in Settings → AI; reads the urgency
  accuracy card; can roll back a promoted model.
- **Reviewer (any role)** — on the feedback detail page, toggles a feedback item's urgent flag when the
  analyzer got it wrong; that toggle silently produces the training signal.
- **API integrator** — flips `is_urgent` via `PATCH /api/public/v1/feedback/{id}`; same signal recorded.

## Requirements

### Must-have
- **M-1 (capture, dashboard):** an internal (JWT) endpoint to set a single feedback item's `is_urgent`,
  plus a control on the feedback detail page. On a user-driven change, emit
  `AICorrection(correction_type="urgency", signal="correction", corrected_value∈{"urgent","not_urgent"})`.
- **M-2 (capture, public API):** `PATCH /api/public/v1/feedback/{id}` emits the same urgency correction
  when `is_urgent` changes (currently records nothing).
- **M-3 (core):** `URGENCY_LABELS=("not_urgent","urgent")` + `build_urgency_dataset()` in the
  `corrections_classifier` package; exported. Binary, fixed vocab.
- **M-4 (config):** `urgency_classifier_mode` column on `OrgAIConfig` (both backend + worker mirrors),
  Alembic migration, GET/PATCH on the AI settings route, resolver map entry.
- **M-5 (trainer):** worker retrain loop trains/evaluates/promotes the urgency head per org, with the
  keyword heuristic wrapped as the binary incumbent.
- **M-6 (predict):** at ingest, under shadow (log only) / auto (override `feedback.is_urgent`), the
  resolved urgency model is applied; off = untouched keyword heuristic.
- **M-7 (frontend):** off/shadow/auto `<Select>` toggle in Settings → AI General, and a
  `ClassifierAccuracyCard classifierType="urgency"`.

### Should-have
- **S-1:** `CORRECTION_TYPE_LABELS` gains an `urgency` entry so the "Corrections by Type" breakdown reads
  "Urgency".
- **S-2:** honest UI copy stating urgency is trained on the org's own corrections and promoted only when
  it beats the keyword heuristic.

### Nice-to-have
- **N-1:** urgent-toggle control also on the urgent-feedbacks list page (not just detail).

### Out of scope
- The `churn_risk` head (M5.3 — data-gated at ~500 labels/org).
- Multi-label urgency and per-kind head splitting (M5.2 v3, still deferred).
- Reworking the `urgent_category` 10-way secondary field — the head mirrors the boolean `is_urgent` only.
- Changing the keyword heuristic itself.

## Technical Considerations

**Services changed:** analysis-engine (core), backend-api (capture + config + migration), worker-service
(trainer + predict-seam), frontend-web (settings + capture control).

**The spine is already type-generic** (verified in the four digs; `docs/planning/_card/understanding.md`):
- analysis-engine `predict()` already has a binary sigmoid path → urgency needs no predict/trainer/evaluate
  edits, only `URGENCY_LABELS` + `build_urgency_dataset` + exports.
- worker retrain loop already iterates `_CLASSIFIER_TYPES`; lock is per-type+per-org; `_promote`/eval-run/
  purge/beat untouched. Add `"urgency"` + one branch in `_dataset_and_incumbent_for` (+ binary incumbent).
- `AICorrection.correction_type` is a free `String(50)` — no schema change to store `"urgency"`.
- frontend accuracy/rollback client is already `classifier_type`-generic — pass `"urgency"`, zero change.

**Data model:**
- New column `OrgAIConfig.urgency_classifier_mode String(20)` server_default `'off'` (backend + worker
  mirror). New Alembic revision. **Repo has multiple alembic heads — check `alembic heads` and set
  `down_revision` correctly** (memory: `rereflect-repo-test-gotchas`).
- `org_classifier_models` needs **no** change — its partial-unique index already keys on `classifier_type`.

**Incumbent:** wrap the existing keyword urgency logic (`analyzer/core.py`, `categorizer.py`,
worker `tasks/analysis.py:663-708`) as a binary predictor emitting `not_urgent`/`urgent`.

**Multi-tenancy:** all correction rows, config, models, and locks are `organization_id`-scoped (existing
pattern). No cross-org exposure.

**Non-functional:** off-by-default; local/sklearn only (BYOK-agnostic); deterministic given dataset +
`RANDOM_STATE`.

## Risks & Open Questions

- **R-1 (resolved):** capture surface didn't exist → **decision: Option B**, build the dashboard toggle +
  endpoint AND the public-API capture.
- **R-2 (resolved):** overwriting `is_urgent` in auto mode is higher-stakes (drives churn alerts) →
  **decision: full off/shadow/auto parity**; auto is opt-in per org, default off.
- **R-3:** class imbalance — most feedback is `not_urgent`, so a naive model could collapse to the
  majority class. Mitigation: the `evaluate` gate uses macro-F1 (not accuracy), so a majority-class
  collapse won't beat the incumbent. Confirm macro-F1 is the decision metric for the binary case in the
  trainer aspect.
- **R-4:** signal sparsity — urgency corrections will accrue slower than sentiment. `MIN_LABELS=20`
  gate means the head simply stays on the incumbent until enough corrections exist (honest, not a bug).
- **R-5:** the internal urgent-toggle must NOT capture the analyzer's own heuristic set/clear
  (`feedback.py:112`, `:665`) as a correction — only user-driven changes. Guard on actor + value-change.

## Decisions (locked at review)

| Decision | Choice |
|---|---|
| Capture seam | **Option B** — dashboard toggle + endpoint AND public-API PATCH |
| Predict override | **off / shadow / auto** full parity (auto overwrites `is_urgent` at ingest) |
| Build depth | **Full head, all layers**, TDD |
| Label set | Binary fixed vocab `("not_urgent","urgent")` |
| **Auto-mode direction** | **Add-only this pass** — `auto` may escalate `not_urgent→urgent` but must NOT de-escalate `urgent→not_urgent`. De-escalation deferred to a higher-confidence phase (caps the downside of a thin per-org model flipping a real churn signal off). Shadow still logs both directions. |
