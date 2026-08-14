# Spec — churn-label-gate-study (slice 1)

## Problem slice

`CHURN_LABEL_TARGET = 500` (`src/config/readiness_thresholds.py:8`) is a verbatim copy of
a pre-pivot hosted-SaaS criterion; half of it ("≥ 5,000 globally") is dead single-tenant,
and nobody has re-derived what a per-org churn classifier needs. `AI-TRACKING.md:551-553`
recommends an M5.3-scoped re-derivation before anyone builds against the number. This
aspect produces that measurement and the documented decision.

## In scope

- A committed, reproducible measurement harness (`services/backend-api/scripts/` or
  `services/analysis-engine/scripts/`, following `eval_sentiment.py` /
  `eval_embeddings.py` conventions): simulates per-org churn datasets at increasing label
  volumes (fixed seeds, stated data-generating process — signal strength, class balance,
  feature noise), trains the planned logistic challenger vs the calibrated-heuristic
  incumbent, and reports leakage-free holdout macro-F1/PR/AUC deltas and promotion rates
  vs label count (learning curves). CPU-only sklearn.
- Fixtures: any usable real labeled sets available in-repo (e.g. churn event data in
  tests/fixtures); otherwise purely synthetic — stated as such.
- Committed artifact `eval_results/churn_label_gate.json` + a readout endpoint/card in
  the M5.1/M5.4 style (`GET /api/v1/settings/ai/churn/label-gate` or a file-served card —
  follow the existing committed-artifact route pattern).
- A **documented decision** in the PRD Decision Record + applied to
  `readiness_thresholds.py`/`ai_readiness.py` if the target moves. The decision may
  honestly be "keep 500" or "the gate is genuinely high; no shortcut" — no fiat lowering.

## Out of scope

- Building the model head itself (aspects 3-5).
- Any production prediction-path change.
- Collecting telemetry from real deployments (no telemetry, ever).

## Acceptance criteria

1. The harness is committed, seeded, and reproducible; `--help`/README in the script
   documents the data-generating process and assumptions.
2. The artifact exists in `eval_results/` with `n`, method, and honest-limits fields,
   and the readout renders it (empty/absent state handled).
3. A documented decision is recorded in the PRD with a `keep`/`change` verdict and the
   number(s) it implies; if it moves, `readiness_thresholds.py` +
   `ai_readiness.py` + frontend card copy follow.
4. Both services' suites green; no migration.

## Dependencies / sequencing

- Can run in parallel with the beat fix (aspect 1). Must complete before the core aspect
  (3) locks the feature vector and before the settings/UI aspect (6) displays the target.

## Open questions / risks

- R1/R2/R3 from the PRD: the verdict may be "genuinely high"; simulation validity is
  bounded; sparse history reconstruction affects the challenger's ceiling — the harness
  should vary the feature-reconstruction fidelity as a dimension.
- Whether the study supports the M5.2 single-run +0.02 promotion rule or suggests a
  consecutive-runs rule for churn (OQ2) — record it.
