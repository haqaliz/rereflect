# PRD — Per-Org Churn ML Model (M5.3)

**Feature**: per-org, local, self-improving churn model head that upgrades the current
isotonic-calibrated heuristic — with the heuristic preserved as the automatic fallback.
**Slug**: `per-org-churn-model`
**Branch**: `feat/per-org-churn-model`
**Status**: Draft for review
**Roadmap**: `AI-TRACKING.md` M5.3 ("Per-org churn ML model (Track C — data-gated)", lines 521-526) + M5 strategic framing (442-455) + gate caveat (542-553).
**Origin**: `rereflect-next` recommendation (2026-08-14); brief in `docs/planning/_card/card.md`.

---

## Problem Statement

For whom: the self-hosting operator of Rereflect who labels churn events (manually, via
CSV import, or by confirming CRM/usage-decline suggestions) and wants the product's
stated killer feature — "churn prediction that actually works" (`AI-TRACKING.md:5`) —
to get *measurably* better with their own data, staying local, CPU-only, and honest.

What is wrong today (evidence from the code, not prose):

1. **The incumbent never runs.** `services/worker-service/src/tasks/churn_calibration.py`
   defines `refit_all_orgs`, `refit_global_calibration`, `purge_old_calibration_models`
   as plain functions with **no Celery decorators**, yet they are registered in
   `celery_app.py` `beat_schedule` (lines 211-232). Beat dispatch raises `NotRegistered`,
   so the weekly per-org and daily global isotonic refits have **never executed in
   production**; `probability_updater._load_active_model` always falls through to the
   identity fallback (`p = score/100`). Corroborated by an in-repo NOTE at
   `tasks/usage_metrics.py:482-485`.
2. **The M5.3 activation gate is unvalidated.** `CHURN_LABEL_TARGET = 500`
   (`services/backend-api/src/config/readiness_thresholds.py:8`) was copied verbatim from
   the pre-pivot hosted PRD (`PRD-ADVANCED-CHURN-PREDICTION.md:463`); the "≥ 5,000
   globally" half of that criterion is meaningless single-tenant. `AI-TRACKING.md:542-553`
   explicitly says the gate is **not settled** and recommends an M5.3-scoped
   re-derivation before anyone builds against the number.
3. **Three label sources now produce training material with no trained consumer.**
   Manual + CSV import, CRM lost renewals (`crm-churn-labels`, shipped 2026-07-15), and
   usage decline (`usage-decline-churn-labels`, shipped 2026-07-24) all feed the
   confirm-in-review queue; `churn_labels_trainable` already excludes `auto_suggested`
   rows (`ai_readiness.py:91-99`). The calibrated heuristic consumes a single scalar
   (`churn_risk_component`); the richer customer features collected around it are unused
   for prediction.

## Goals & Success Metrics

| Goal | Success metric | Measured by |
|------|----------------|-------------|
| The calibrated-heuristic incumbent actually runs | Three beat tasks registered; a dispatch-level test green in the worker suite | `pytest tests/test_churn_calibration_tasks.py` (extended) |
| The 500-label gate is re-derived, not assumed | A committed measurement artifact + a documented decision (keep / lower / change activation), incl. sample size, method, and honest limits | `eval_results/churn_label_gate.json` + card; PRD decision record |
| Per-org ML head follows the M5.2 spine | For a qualifying org: challenger macro-F1 ≥ incumbent + 0.02 on leakage-free held-out labels → auto-promotes; otherwise retained; rollback + resume work | worker + backend + analysis-engine suites (M5.2 conventions) |
| Heuristic is the automatic fallback | With no active org model, `churn_probability` behavior is byte-identical to today | characterization test on `probability_updater` |
| Honest by construction | No "beats the heuristic" claim without a committed eval artifact; UI states model provenance | eval artifacts + UI copy tests |
| Repo conventions honored | CHANGELOG, SELF_HOSTING, AI-TRACKING/DEV-TRACKING markers, NOTE removal all land with the feature | docs diff in the PR |

**Product-level measurement caveat (stated plainly):** the only *outcome* metric — "for a
qualifying org, ML beats the heuristic" — is **not measurable at this card's ship date**:
no real org is at label volume and the product takes no telemetry. Success for this card
is therefore defined as: (1) the defect fix proven by tests, (2) the gate decision
delivered as an artifact, and (3) the spine shipped dormant-but-proven (shadow A/B +
rollback + fallback). The metric "qualifying org" is defined operationally in the
readiness report (trainable labels ≥ re-derived target), which any future org can
evaluate offline. Simulation evidence is a **bound, not a measurement** — every surface
that shows the study result says so.

**Honest exit (from `AI-TRACKING.md:525-526`):** for a qualifying org, ML beats the
heuristic on backtest with the auto-fallback preserved. There is **no real org at label
volume today** — any such claim starts from simulation, and the exit stays conditional on
a qualifying org.

## User Personas & Scenarios

- **The self-hosting operator** (single org): accumulates churn labels over months via
  manual marking, CSV import, and confirmed CRM/usage suggestions. Readiness card shows
  trainable labels vs the gate. Wants: a mode toggle (`off`/`shadow`/`auto`), an
  incumbent-vs-challenger accuracy card, rollback, and honest copy ("your model, trained
  on your data, promoted only when measurably better").
- **The system admin** (multi-org operator): wants to see which orgs qualified and what
  each model's metrics are, mirroring the existing classifier accuracy/versions UI.
- **Scenario (shadow):** operator enables `churn_classifier_mode=shadow` at ~20 labels.
  Every refit evaluates the ML challenger against the calibrated heuristic on held-out
  labels, logs the delta, promotes nothing.
- **Scenario (auto + qualifying):** challenger clears +0.02 macro-F1 twice in a row →
  auto-promoted, `churn_probability` values now come from the ML head; a regression →
  one-click rollback re-engages the autopromote hold; heuristic remains fallback below
  `MIN_LABELS`.

## Requirements

### Must-have

- **Prerequisite — beat fix.** Decorate the three `churn_calibration.py` functions with
  `@shared_task` (matching the codebase's task convention), keep the existing
  `celery_app.py` beat entries working, and pin with a test that the tasks are registered
  (worker suite). No behavior change beyond registration.
- **Aspect: gate re-derivation study.**
  - A committed measurement harness (script + fixture data), M5.1/M5.4 style, that
    estimates the label volume at which a per-org logistic churn classifier reliably
    beats the incumbent heuristic on leakage-free evaluation — via simulated/synthetic
    datasets and any available real labeled sets. CPU-only, sklearn, seeds fixed.
  - Output: committed artifact (`eval_results/churn_label_gate.json`) + a card/readout,
    + a **documented decision** on `CHURN_LABEL_TARGET` (keep at 500 / lower / gate
    activation differently), recorded in this PRD and applied to
    `readiness_thresholds.py` + `ai_readiness.py` if it moves. The decision may honestly
    be "the gate is genuinely high; the head stays dormant below it."
- **Aspect: churn classifier core** (analysis-engine, `analyzer/churn_classifier/`).
  - A **fixed, documented feature vector** built per customer at label time,
    reconstructible from existing history (components at churn time from
    `customer_health_history`, usage + trend from `customer_usage`/`customer_usage_history`
    snapshots nearest label date, feedback aggregates, segment slug). Net-new schema only
    if the study shows it is required for the exit.
  - JSON-only model artifact (never pickle; `trainer.py` convention), pure-stdlib
    predict (no sklearn at predict time), lazy sklearn/numpy imports (worker CI runs
    without ML wheels).
  - Leakage-free holdout A/B with the calibrated heuristic as the incumbent (post-fix)
    and identity fallback below `MIN_LABELS`; promote only on macro-F1 delta ≥ **+0.02**
    (reuse the M5.2 `evaluate.py` core or a byte-faithful churn variant).
- **Aspect: worker trainer + schedule.**
  - `retrain_org(org_id, db)` / `retrain_all_orgs()` for `classifier_type='churn'`,
    Redis advisory lock, single-commit promote with `flush()` before INSERT (partial
    unique index), purge inactive > 90 days, weekly beat slot **before** the 06:30
    classifier slot (e.g. 06:00 UTC Mondays) and the existing 07:45 churn-calibration
    slot — sequencing matters: the ML challenger evaluates against the incumbent *after*
    the incumbent's own weekly refit.
  - `decision='held'` eval run on manual rollback (autopromote hold), mirroring
    `classifier_training.py`.
- **Aspect: predict seam + resolver.**
  - `OrgAIConfig.churn_classifier_mode` (`off`/`shadow`/`auto`, default `off`) +
    `churn_autopromote_hold`; mirrored in the worker models.
  - Resolver + predict seam mirroring `classifier_resolver.py` / `classifier_predict.py`
    (byte-identical pairs, golden-mirror tests).
  - **Prediction seam (user-confirmed):** in `auto` with an active churn model, the ML
    head's probability **upgrades the existing `churn_probability` column** at the
    `probability_updater` call site; in `shadow` it logs only. Calibrated/identity
    behavior byte-identical below the gate (characterization test).
- **Aspect: settings API + accuracy/versioning + frontend.**
  - `churn_classifier_mode` in `AISettingsResponse/Update` + validation (reuse
    `VALID_CLASSIFIER_MODES` + `_classifier_deps_available`).
  - `classifier_type='churn'` accepted by the existing `classifier/accuracy`,
    `classifier/versions`, `classifier/rollback`, `classifier/resume` endpoints
    (extend `VALID_CLASSIFIER_TYPES` + hold-column map); admin/owner gating unchanged.
  - Frontend: mode dropdown in Settings → AI General; fourth accuracy card in the
    Accuracy tab (incumbent-vs-challenger + n + rollback + hold banner); readiness
    card/`ai_readiness.py` reflects the re-derived gate.
- **Tests** per M5.2 conventions: mirror parity (backend + worker), model column parity,
  training-task suite (promote/retain/skip/held, active-invariant, lock), seam matrix,
  settings validation, accuracy/versions/rollback/resume routes, analysis-engine
  parity + fair-A/B, `probability_updater` characterization (heuristic fallback
  byte-stable).

### Should-have

- Gate-study methodology documented (sample sizes, iterations, seeds, assumptions) in
  the aspect spec so the artifact is reproducible.
- Honest-limits UI copy for the churn card (n shown, "promoted only when measurably
  better", provenance line), matching `ModelAccuracyCard`/`ClassifierAccuracyCard`
  conventions.
- Readiness readout: `churn_labels_trainable` vs the (possibly re-derived) target with
  the AI-TRACKING "under review" caveat in the card copy.

### Must-have (continued)

- **Aspect: docs, changelog, tracking close-out.** Repo convention (visible across every
  shipped feature's commit history): CHANGELOG.md entries, `docs/SELF_HOSTING.md` upgrade
  callout (new `churn_classifier_mode` setting, gate decision, air-gap notes), AI-TRACKING.md
  M5.3 markers + the gate decision record, DEV-TRACKING.md FIXED marker for the beat
  defect, and removal of the `usage_metrics.py:482-485` NOTE once the fix lands.

### Nice-to-have (explicitly deferred)

- Per-customer prediction-history log (net-new table) for offline replay backtests.
- Multi-label / per-reason-code heads; seasonality dampening; per-org thresholds for
  the usage-trend signal (already deferred in M3.2b).
- Any change to the calibrator beyond the decorator fix (F1-drop guard, window tuning,
  `MIN_LABELS` parity with the study's findings is in scope; other debt is not).

## Abort / continue criteria for the gate-study verdict

The gate study (aspect 2) can honestly conclude "no defensible single-tenant threshold"
(e.g. the learning curves never converge, or simulation variance is too high to justify
any number). **This does not cancel the card.** Aspects 3-6 ship regardless: the spine
ships dormant below the existing gate with shadow-only evaluation and the honest card,
because the per-org self-improving spine *is* the M5.3 deliverable and the gate is
data-dependent, not code-dependent. The only abort case is a study failure so severe it
calls the feature vector itself into question (R3) — then aspects 3-6 are rescoped after
a gate review rather than auto-cancelled. This decision point is recorded in the PRD
Decision Record when the study lands.

## Technical Considerations

- **Services**: analysis-engine (new `analyzer/churn_classifier/` core), worker-service
  (task, model mirror, resolver/predict mirrors, `probability_updater` seam),
  backend-api (models, `ai_settings.py`, `classifier_accuracy.py`,
  `ai_readiness.py`, one Alembic migration), frontend-web (Settings → AI General +
  Accuracy tabs, readiness card).
- **DB**: reuse `org_classifier_models` (`classifier_type='churn'`) and
  `org_classifier_eval_runs` — both are already generic. Two new `OrgAIConfig` columns
  via one migration chained off the single head (`alembic heads` must print exactly one
  head). Partial-unique index on (org, type) WHERE `is_active` applies unchanged.
- **Backend↔worker duplication conventions apply**: byte-identical mirror pairs,
  golden-mirror tests, model column-parity tests, lazy ML imports. Worker cannot import
  backend-api.
- **Sequencing**: the ML challenger's A/B incumbent is the calibrated heuristic — the
  beat fix must land first so the incumbent is real. The 06:00 churn-ML slot must run
  after the 03:00 global/07:45 per-org calibration refits, not before.
- **Multi-tenancy**: everything org-scoped; no cross-org pooling; no new telemetry
  (M4.3 guardrail `AI-TRACKING.md:388-402`).
- **CI**: backend job strips torch/transformers; worker runs without ML wheels —
  lazy imports are load-bearing. No new pytest markers.

## Risks & Open Questions

- **R1 — The re-derived gate may be genuinely high** (or the study may show no
  single-tenant threshold is defensible). Then the head ships dormant below the gate,
  shadow-only. This is an honest, accepted outcome — the roadmap's recommended follow-up
  is exactly this measurement, and the decision is recorded rather than fiat.
- **R2 — Simulation validity.** There is no real org at label volume; synthetic learning
  curves are only a bound. The study must state this on the card.
- **R3 — Feature reconstruction at label time.** Health/usage history may be sparse for
  old labels; the feature builder must handle missing snapshots (documented defaults),
  and the study should measure how much that degrades the challenger.
- **R4 — The defect fix wakes up a never-run path.** `refit_all_orgs`/global have never
  executed; first production runs may surface latent bugs. Mitigation: existing direct-call
  tests stay green, and the fix adds only registration (no behavior change).
- **R5 — Incumbent metrics are in-sample today** (`calibration_refit.py:89-90`); the A/B
  must evaluate both sides on the same leakage-free holdout or the delta is meaningless.
- **OQ1** — Exact feature vector contents and preprocessing (fixed in the core aspect
  spec; the study informs the final set).
- **OQ2** — Auto-promotion cadence: promote on a single +0.02 delta run (M5.2 behavior)
  vs. consecutive-runs requirement for churn. Default: match M5.2 (single run), revisited
  if the study shows high variance.

## Out of Scope

- Cross-tenant anything (benchmarks, pooled training, telemetry) — M4.3 is DROPPED.
- Per-org fine-tuning of the BYOK LLM.
- Plan gates / tiers — everything unlocked (OSS).
- Prediction-history table (nice-to-have above), CRM/usage feature *collection* (already
  shipped), the outreach/automation loop (consumes `churn_probability`; unchanged).
- Calibrator debt beyond the decorator fix (per R4); Stripe (dead post-pivot).

## Decision Record

| Date | Decision |
|------|----------|
| 2026-08-14 | Full M5.3 in one card, sequenced aspects: beat fix → gate study → core → worker trainer → predict seam → settings/UI. |
| 2026-08-14 | Beat fix included as prerequisite (user-confirmed). |
| 2026-08-14 | Auto-mode ML probability **upgrades** `churn_probability` (user-confirmed). |
| 2026-08-14 | Gate: **under review** — output of the study, not assumed at 500. |
| 2026-08-14 | Abort/continue: a "no defensible gate" verdict does **not** cancel the card — the spine ships dormant + shadow-only; only an R3-scale feature-vector failure rescopes it (added at self-critique). **Outcome: no abort triggered** — the study produced a defensible verdict (`keep_500`), the feature vector survived the 25%-missing-snapshot fidelity check, and all 7 aspects shipped on the branch. |
| 2026-08-14 | Docs/changelog/tracking close-out promoted to a must-have aspect (repo convention; added at self-critique). |
| 2026-08-14 | Gate study verdict: keep 500 (simulated crossover 200 at full fidelity and at 25% missing-snapshot fidelity; gate clears with margin). OQ2: single-run +0.02 promotion is high-variance at crossover (57% promo rate) → consecutive-runs promotion adopted for the churn head (see aspect 4 amendment). |
| 2026-08-14 | Gate verdict **applied: keep 500 → no threshold change** — `CHURN_LABEL_TARGET`/readiness surface untouched; the `keep_500` verdict recorded in `AI-TRACKING.md`'s gate-caveat block and on the Churn Label Gate card. |
| 2026-08-14 | **Consecutive-runs promotion adopted** (shipped): two consecutive weekly clears of the +0.02 macro-F1 bar — run 1 stages `promoted_candidate` (no swap), run 2 promotes; any evaluable non-clear breaks the streak; below-gate weeks are no-signal and don't; the autopromote hold clears both runs' state. |
| 2026-08-14 | **Aspect statuses: all 7 aspects shipped** on `feat/per-org-churn-model` (2026-08-14) — calibration-beat-fix, churn-label-gate-study, churn-classifier-core, worker-churn-trainer-and-schedule, churn-predict-seam-resolver, settings-api-and-churn-accuracy-card, docs-changelog-tracking. |
