# Phase 2 — Understanding note: per-org category classifier (M5.2 v2)

Synthesis of four read-only service maps (analysis-engine, worker, backend, frontend), 2026-07-11.

## What the issue is really asking

Extend the shipped M5.2 per-org self-improving classifier from **sentiment** to a **category** head,
so an org's own `AICorrection` **category** signals train a small CPU-only per-org model that (in
shadow/auto) improves how feedback is categorized — same spine, same A/B-gate, same rollback, same
Settings surface as sentiment.

## Headline finding: the spine is already ~90% task-generic

The M5.2 authors built the storage and orchestration layers type-generic on a `classifier_type`
discriminator. **No migration is needed for the model/eval-run tables or the correction source.**

| Layer | State | What category needs |
|---|---|---|
| `OrgClassifierModel` / `OrgClassifierEvalRun` | **Already generic** — `classifier_type String(30)`; partial-unique active row is per `(org, classifier_type)` (`models/org_classifier.py:44,70-77,103`) | Nothing — rows just carry `classifier_type='category'` |
| `AICorrection` | `correction_type='category'` already flows end-to-end (`models/ai_correction.py:23-26`); public API + dashboard already write it | Nothing — data source exists |
| Accuracy + rollback API | **Already type-parameterized** — `GET/POST .../classifier/accuracy|rollback` take `classifier_type` (default `sentiment`) (`routes/classifier_accuracy.py:34,123,148`) | Nothing backend-side; frontend passes `classifier_type=category` |
| `predict.py` / `metrics.py` / `trainer.py` math | **Label-agnostic** — classes derived from the fitted model, stored in the JSON artifact | Nothing |
| Worker orchestration (`classifier_training.py`) | Type-agnostic **except** the module constant `_CLASSIFIER_TYPE="sentiment"` | Make it a loop variable over `("sentiment","category")`; suffix the Redis lock key with type |
| Analysis-engine core sentiment locks | 4 touch-points | `dataset.py:45,71` (label filter + `correction_type`), `trainer.py:64` (artifact type), `evaluate.py:205` (`labels = SENTIMENT_LABELS`) + a new label vocab in `labels.py` |
| Predict-seam mutation | `apply_classifier_override` threads `classifier_type` but **hard-writes `feedback.sentiment_label/score`** and uses sentiment-only `score_from_proba` (`services/classifier_predict.py:250-251`, `predict.py:120-123`) | Add a category branch: write `pain_point_category`/`feature_request_category`; bypass the signed-score reducer |
| `OrgAIConfig.classifier_mode` | **Single org-wide scalar** (off/shadow/auto) — the ONE sentiment-shaped schema gap (`models/org_ai_config.py:24`) | Decision: share one mode, or add a per-type `category_classifier_mode` (small migration) |

## The central design question (for the PRD interview)

`AICorrection` for a category correction stores `corrected_value` (a category name) but **not which
field** was corrected. `_resolve_correction` (`routes/public_api.py:355-362`) maps **both**
`pain_point` and `feature_request` field corrections to `correction_type="category"`. So the training
bucket mixes two disjoint dimensions with no kind discriminator.

Options for the head structure:

- **A — One unified `category` head (recommended first slice).** Multi-class over the label set that
  actually appears in the org's category corrections (dynamic-from-data → custom categories handled
  for free, no `CustomCategory` reconciliation needed). Override routes to `pain_point_category` vs
  `feature_request_category` by **which built-in vocab the predicted label belongs to**. Matches the
  existing data bucket exactly; zero correction-schema change. Limit: one prediction per item; can't
  independently correct both fields on the same item.
- **B — Separate per-kind heads** (`category_pain_point`, `category_feature_request`, maybe `urgency`):
  semantically cleaner, independent override targets — but the correction row lacks a kind field, so it
  needs either a schema change to record the corrected field, or membership-inference (ambiguous for
  custom/`general` categories). More work + a data-model change.
- **C — Pain-point-only first slice:** smallest, but still needs kind-inference to filter the bucket
  and yields the least data.

**Recommended default:** Option A + **dynamic label vocab from the org's own corrections** (not a fixed
built-in tuple, not `CustomCategory` reconciliation). This is *simpler* than the card's "fixed built-in
label set" mitigation and absorbs custom categories automatically. `evaluate.py:205`'s fixed-labels
assumption becomes "labels derived from the dataset."

## Other decisions to pressure-test

1. **Mode gating:** share the one `classifier_mode` (no migration, but `auto` enables both heads
   together) vs a per-type `category_classifier_mode` column (small migration, independent control).
   *Leaning per-type* — honesty/reversibility principle wants independent enable + the sentiment head
   should not silently change behavior when someone turns on category.
2. **Category incumbent for the A/B eval:** the deterministic **keyword categorizer**
   (`analyzer/categorizer.py`, base vocab) is the natural incumbent (cheap, no LLM). Note the analysis-
   engine keyword path does *not* merge `CustomCategory` today (`core.py` never calls
   `add_custom_categories`) — the LLM path in the worker does. Incumbent = keyword categorizer prediction.
3. **Override score:** category has no signed axis; store confidence = max class proba (or leave score
   null). Bypass `score_from_proba`.
4. **First-slice exit vs data-gated exit:** build + prove the pipeline end-to-end on **seeded/synthetic
   category corrections** (spine parity with sentiment). "Promoted on a real org's held-out category
   corrections" is the later, data-dependent exit — not the first PR (mirrors how M5.2 sentiment shipped).

## Cross-cutting principles that must hold
CPU-only; default analyzer output byte-stable when mode=off/shadow; every promotion A/B-gated + reversible;
no cross-tenant data; small model, described honestly (state `n` and the macro-F1 delta).

## Contradiction flagged
The `_card` brief's mitigation ("fixed built-in category label set first") is *superseded* by a cleaner
approach: dynamic labels from the org's corrections. Same risk-reduction (no `CustomCategory`
reconciliation in slice 1), less code, and it doesn't drop custom categories the operator has already
been correcting toward.
