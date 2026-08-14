# Spec — churn-predict-seam-resolver (slice 2c)

## Problem slice

The per-org mode gate and the prediction override: `OrgAIConfig.churn_classifier_mode`
(off/shadow/auto) + `churn_autopromote_hold`, a resolver mirroring
`classifier_resolver.py`, and a predict seam at `probability_updater` so an auto-mode
active churn model **upgrades the existing `churn_probability` column** (user-confirmed
decision), with shadow logging only and byte-identical behavior below the gate.

## In scope

- One Alembic migration (chained off the single head — `alembic heads` must print
  exactly one): `org_ai_config.churn_classifier_mode` String(20) server_default `'off'` +
  `churn_autopromote_hold` Boolean default false. Mirror both columns in
  `services/worker-service/src/models/__init__.py`.
- Resolver: extend `MODE_COLUMN_BY_CLASSIFIER_TYPE` with
  `"churn": "churn_classifier_mode"` in **both** `classifier_resolver.py` copies
  (byte-identical; golden-mirror test extended). Never-raises, getattr-defensive.
- Predict seam at the churn-probability computation site
  (`services/worker-service/src/services/probability_updater.py` `update()`):
  - `off`/no model → existing path byte-identical (characterization test).
  - `shadow` → compute the ML head's probability, log `rereflect.classifier.shadow`
    (structured logger), write nothing.
  - `auto` + active org churn model → ML probability **replaces** the calibrated value
    written to `customer_health_scores.churn_probability` (+ low/high CI + bucket, per
    the head's outputs); `calibration_model_id` semantics documented (ML-active state is
    visible via the org_classifier active row + a `probability_computed_at` timestamp
    stays fresh). All consumers (segments `AT_RISK_CHURN_PROBABILITY_THRESHOLD`,
    automations, badges) update for free — no consumer changes.
  - Cross-org safety: nothing outside the org's rows is ever read/written.
- Backend shadow-only mirror at the backend's health/churn recompute sites where
  applicable (mirror the `analysis.py`/`feedback.py` ownership split: worker
  authoritative `allow_override=True`, backend `False`).

## Out of scope

- Training/promotion (aspect 4). Settings API + UI (aspect 6). Consumer logic changes.

## Acceptance criteria

1. Migration up/down clean; `alembic heads` prints one head; column-parity tests
   (`test_model_parity_classifier.py`) green for both new columns.
2. Golden-mirror test for the resolver pair green with the new mapping.
3. `probability_updater` characterization test: with `off`/no model/no labels, output
   byte-identical to current behavior.
4. `auto` + active model: `churn_probability` comes from the ML head (seeded artifact
   test, `test_probability_updater.py` style); `shadow`: nothing written, shadow log
   emitted.
5. Worker + backend suites green.

## Dependencies / sequencing

- Needs aspects 1 (incumbent real) + 3 (core) + 4 (task produces artifacts) — the seam
  consumes whatever the worker wrote. Migration must land before the worker task reads
  the columns (getattr-defensive in the interim).

## Open questions / risks

- CI-width of the ML prediction: the pure-stdlib predict keeps the hot path sklearn-free
  (lazy import), matching worker CI constraints.
- `probability_updater` hysteresis guard: ML values may move differently than the
  scalar heuristic — the existing `_HYSTERESIS_THRESHOLD` guard is left as-is; noted in
  the PRD OQ2 if the study flags variance.
