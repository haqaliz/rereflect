# PRD — Per-Org Self-Improving Corrections Classifier (M5.2)

**Slug:** `per-org-corrections-classifier`
**Branch:** `feat/per-org-corrections-classifier`
**Roadmap:** AI-TRACKING.md → M5.2 (Track A, flagship of the M5 Local Model Layer block)
**Status:** Draft for review gate
**Date:** 2026-07-10

> Grounding: `docs/planning/_card/card.md` (brief) + `docs/planning/_card/understanding.md`
> (Phase 2 code-dig). Decisions below were confirmed in the Phase 3 interview.

---

## Problem Statement

Rereflect has collected human corrections of its AI output since M3.3 (`AICorrection`, table
`ai_corrections`) — but **nothing trains on them**. The analyzer that assigns sentiment and
categories to feedback is static: VADER thresholds + keyword/LLM categorizers. When an operator
repeatedly corrects "this negative item was tagged neutral," that signal is stored and shown on an
accuracy tab, then ignored. M4.2's "fine-tuned classification" was deferred; the flywheel is open.

For an **open-source, self-hosted, BYOK** product the moat is explicitly **not** a central model or
cross-tenant dataset (dead single-tenant — the reason M4.3 benchmarks were dropped). The M5
strategic framing names the defensible play: a **per-org, local, self-improving model layer** that
trains only on the operator's own data, runs locally with no cloud dependency, improves the more
it's corrected, and stays honest (small models, stated as such — as churn already is "a calibrated
heuristic"). This PRD closes the corrections loop for **sentiment** first, on that pattern.

**Evidence it's real:** grep confirms `AICorrection` appears only in model/service/readiness/
public-API-write code — **zero training consumers**. The heavy platform is already installed
(`scikit-learn` used lazily by the churn calibrator) and the per-org fit + provider-injection
patterns already exist (M4.1 `churn_calibrator`, M5.1 `sentiment_providers`).

## Goals & Success Metrics

**Goal:** an operator can enable a per-org classifier that learns from their sentiment corrections,
runs in shadow against the incumbent analyzer, and — in `auto` mode — promotes itself **only when it
measurably beats the incumbent** on held-out corrections, with a visible delta and one-click rollback.

| Metric | Target (v1, this PR) |
|---|---|
| Spine proven end-to-end on **synthetic/seeded** corrections | Train → shadow-A/B → promote-when-better → rollback all pass in tests |
| Default behavior unchanged | `classifier_mode` defaults `off`; analyzer output **byte-identical** when off or shadow |
| Promotion safety | A challenger is promoted **iff** macro-F1 delta ≥ margin on a held-out split; else incumbent retained; every run recorded |
| Honesty | Accuracy card states model kind ("per-org TF-IDF + logistic regression"), `n` (label count), and the incumbent-vs-challenger macro-F1 with delta |
| CPU-only / offline | No torch, no GPU, no network; artifact is small JSON; no new heavy dependency |

**Real-world exit (later, NOT gating this PR):** ≥1 design-partner org has a promoted per-org
sentiment model beating the default on their own held-out corrections.

## User Personas & Scenarios

- **Self-host operator / CS admin** — has been correcting sentiment on feedback for weeks. Enables
  `shadow` mode in Settings → AI, watches the accuracy card fill in ("challenger macro-F1 0.71 vs
  incumbent 0.66, +0.05, n=140"), then flips to `auto`. The model promotes on the next weekly refit
  and the operator sees which model is live, with a Roll back button.
- **Cautious operator** — leaves it in `shadow` indefinitely to observe the delta without ever
  changing stored values. Trusts the numbers before enabling `auto`.
- **Small/new org** — below the per-type label gate; the card shows "not ready — N/threshold
  sentiment corrections"; nothing trains; analyzer output is unchanged.

## Requirements

### Must-have (v1 — this PR)

1. **Data layer**
   - New table `org_classifier_models` (versioned JSON artifact; mirrors `churn_calibration_models`):
     `organization_id` (nullable = global/base), `classifier_type` (v1: `sentiment`), `model_json`
     (TF-IDF vocab + logreg coefficients + class list — **JSON, never pickle**), `label_count`,
     `macro_f1`/`precision`/`recall`/`accuracy` (Numeric(5,4), nullable), `fit_at`, `is_active`;
     **partial-unique** one active per `(organization_id, classifier_type)`.
   - New table `org_classifier_eval_runs` (mirrors `churn_backtest_runs`): per-run challenger-vs-
     incumbent macro-F1 + delta + decision (`promoted`/`retained`/`skipped`) + `n` + `duration_ms` +
     `notes` + FK to the model row. Feeds the accuracy card's history.
   - New column `OrgAIConfig.classifier_mode` VARCHAR(20) NULL default `'off'` (values
     `off`/`shadow`/`auto`), added to the SQLAlchemy model **and the worker mirror**, with one Alembic
     migration (`server_default='off'`, `down_revision='6ad1dc4335f1'`).
   - **`AICorrection` mirrored into `worker-service/src/models/__init__.py`** (not present today) so
     the trainer task can read corrections.
2. **Training + eval core** (pure compute, CPU, lazy imports)
   - Per-org **dataset builder**: query `ai_corrections` for `organization_id`, `correction_type='sentiment'`,
     `signal='correction'`, `corrected_value IS NOT NULL`; get input text via `feedback_text` if
     present else join `FeedbackItem.text` on `entity_id` (same org); label = `corrected_value`; drop
     rows with no resolvable text. Fixed label vocabulary `{positive, neutral, negative}`.
   - **TF-IDF + LogisticRegression** trainer producing a JSON artifact; deterministic given data.
   - **Per-type gate** `MIN_LABELS` (reuse the 20-label semantics; a per-type threshold read from the
     builder's own count, **not** the M5.0 grand-total `correction_volume_ready` flag).
   - **Shadow-A/B**: held-out split; score incumbent (current analyzer sentiment path) and challenger
     over the same held-out corrections; build two confusion matrices; reuse
     `scripts/eval_sentiment.py::compute_multiclass_metrics` + the `run_provider` shape; compute
     `macro_f1_delta`; **promote decision = delta ≥ margin**.
3. **Worker trainer task + schedule**
   - `tasks/classifier_training.py::retrain_all_orgs` — iterate orgs, per-org `try/except`, call the
     core, and on a passing challenger **insert a new active row + flip the previous active to
     inactive** (never mutate in place); record an `org_classifier_eval_runs` row every run regardless
     of decision; purge inactive > 90 days.
   - Registered in `celery_app.py` `include=[...]` + a `beat_schedule` entry in an **uncrowded Monday
     slot** (06:30 UTC).
4. **Predict seam + resolver**
   - `resolve_classifier(org_id, classifier_type, db)` mirrored in **both** services, `getattr`-defensive,
     never raises; reads `OrgAIConfig.classifier_mode`.
   - A classifier predictor that loads the org's active artifact with **three-tier fallback**
     (org active → global active → **incumbent**), corrupt-artifact → incumbent.
   - Inject at both sentiment call-sites (worker `tasks/analysis.py::_apply_keyword_analysis`/
     `_analyze_feedback_item`; backend `routes/feedback.py`):
     - `off` → do nothing (byte-stable).
     - `shadow` → compute challenger prediction, **log to `org_classifier_eval_runs`/a prediction
       log**, do **not** touch `feedback.sentiment_label/score`.
     - `auto` → if a promoted model is active, override `feedback.sentiment_label` (and set
       `sentiment_score` consistently — see **sentiment_score mapping** below) before commit.
   - **sentiment_score mapping (required):** a TF-IDF+logreg classifier outputs a class label +
     class probabilities, **not** a VADER-style compound in [-1, 1]. Downstream consumers
     (`health_score_service`, dashboard sentiment trend, churn factors) read `sentiment_score`, so the
     override must produce a coherent score, not just a label. Define a deterministic map (e.g.
     `score = P(positive) − P(negative)`, clamped to [-1, 1]) and characterization-test that
     health/trend math stays coherent when a promoted model is active. Confirm the exact formula in
     tech-plan.
   - **Trainer/promotion atomicity (required):** insert-new-active + flip-old-inactive must happen in
     **one transaction**, ordered so the partial-unique `(org, classifier_type) WHERE is_active`
     constraint is never violated (deactivate prior, insert new active, commit). Create-time predict
     reads whatever single active row is committed; there is never a window with 0 or 2 active models.
     The weekly beat is the only writer; a per-org advisory guard prevents overlapping refits of the
     same org.
   - Per-org artifact ⇒ the analyzer/predictor cache key must include `org_id` (current sentiment
     cache is keyed by provider-name only); the cache must invalidate when a new model is promoted.
5. **Settings API + toggle + accuracy card**
   - `ai_settings.py`: `classifier_mode` in the GET/PATCH request+response Pydantic models, validated
     against `{off, shadow, auto}`; if any heavy path were selected, gate on a deps-availability check
     like `_sentiment_transformer_deps_available()` (TF-IDF path needs only scikit-learn, so this is a
     light guard).
   - `GET /api/v1/settings/ai/classifier/accuracy` (mirror the sentiment-accuracy endpoint shape):
     active model + last-N eval runs (incumbent vs challenger macro-F1 + delta + decision + `n`).
   - Frontend: Settings → AI mode toggle (off/shadow/auto) + an accuracy/delta card (reuse the
     `SentimentAccuracyCard`/churn-accuracy card pattern), honestly labeled with model kind and `n`,
     plus a **Roll back** action (flip active model to previous / disable).

### Should-have

- Rollback UI beyond disable: explicitly re-activate the prior model version.
- "Not ready" state on the card with the per-type count vs threshold.
- Seed/synthetic-corrections test fixture usable as an operator demo.

### Nice-to-have (explicitly deferred)

- **Category classifier head** (pain-point + feature-request) with vocab reconciliation
  (built-ins ∪ active `CustomCategory`) + pain/feature disambiguation — the immediate **v2**.
- sentence-transformers / embedding-based featurization variant.
- Automatic mode escalation (shadow→auto) once the delta is stable.

## Technical Considerations

- **Services touched:** `backend-api` (models, migration, ai_settings API, accuracy endpoint,
  predict seam at create-time), `worker-service` (AICorrection + new-model mirrors, trainer task,
  beat schedule, predict seam), `analysis-engine` (optional home for the pure training/eval module,
  mirroring where `SentimentAnalyzer` lives), `frontend-web` (Settings toggle + accuracy card).
- **Patterns to mirror (do not reinvent):** `churn_calibration_models` storage/versioning/3-tier
  load; `tasks/churn_calibration.py` schedule; `sentiment_providers` + `resolve_sentiment_provider`
  injection; `eval_sentiment.py` metrics; `SentimentAccuracyCard` + churn-accuracy card UI.
- **Multi-tenancy:** every query scoped by `organization_id`; artifacts are per-org; `org_id=NULL`
  reserved for an optional global/base model.
- **Both-service mirroring:** `OrgAIConfig`, resolvers, and the two new model classes must exist in
  backend **and** worker `models/__init__.py`. `AICorrection` must be **added** to the worker mirror.
- **Alembic:** currently a **single head** `6ad1dc4335f1`; set `down_revision` to it; run
  `alembic heads` before generating; add a merge migration only if a concurrent branch splits heads.
- **CPU-only + lazy imports:** no top-level `sklearn`/`numpy` import (Py3.14 CI venv lacks wheels);
  no torch/GPU; artifacts small JSON; never pickle.
- **Byte-stable default:** `off` default; `shadow` never mutates stored values; `auto` only overrides
  when a promoted model is active; all reversible.

### Data Model (new)

```
org_classifier_models
  id PK
  organization_id  FK organizations (NULLABLE = global/base)
  classifier_type  VARCHAR  # v1: 'sentiment'
  model_json       JSON     # tfidf vocab/idf + logreg coef/intercept + classes  (NO pickle)
  label_count      INT
  precision, recall, macro_f1, accuracy  NUMERIC(5,4) NULL
  fit_at           DATETIME
  is_active        BOOL
  UNIQUE (organization_id, classifier_type) WHERE is_active   # partial unique

org_classifier_eval_runs
  id PK
  organization_id  FK
  classifier_model_id FK org_classifier_models NULL
  classifier_type  VARCHAR
  incumbent_macro_f1, challenger_macro_f1, macro_f1_delta  NUMERIC(5,4) NULL
  decision         VARCHAR  # promoted | retained | skipped
  n                INT
  duration_ms      INT
  notes            TEXT
  created_at       DATETIME

org_ai_config
  + classifier_mode VARCHAR(20) NULL DEFAULT 'off'   # off | shadow | auto
```

### API Contracts (new/changed)

- `GET/PATCH /api/v1/settings/ai` — add `classifier_mode` (validated `off|shadow|auto`).
- `GET /api/v1/settings/ai/classifier/accuracy` — active model summary + last-N eval runs.
- (Optional) `POST /api/v1/settings/ai/classifier/rollback` — deactivate/roll back the active model.

## Risks & Open Questions

- **R1 — sparse real corrections (the top failure mode).** Real orgs may never reach the per-type
  gate. *Mitigation:* v1 proves the machinery on synthetic corrections; the card honestly shows
  "not ready" with the count; nothing degrades when unbuilt. Real-org promotion is the later exit.
- **R2 — untrustworthy shadow-A/B on tiny held-out sets.** A +0.05 delta on n=15 is noise.
  *Mitigation:* a **small-sample guard** — no `auto` promotion unless the held-out set has ≥ a minimum
  count AND every class is represented; below that, `shadow` still trains + shows the delta but the
  decision is forced to `retained` with a "held-out too small" note. Card always shows `n`.
  **Open (confirm in tech-plan):** exact `MIN_LABELS`, held-out fraction (or stratified k-fold when
  tiny), minimum held-out size, and promotion margin — propose `MIN_LABELS=20`, 20–25% held-out,
  min-held-out ≈ 8 with all 3 classes present, margin `+0.02` macro-F1 (M5.1's stated ambition band).
- **R3 — incumbent scoring for the A/B.** The "incumbent" prediction for held-out corrections is the
  analyzer's sentiment on that text. **Open:** score incumbent live via `SentimentAnalyzer` at
  eval-time (clean) vs trust `AICorrection.original_value` (point-in-time, may have drifted). Lean
  live-score for fairness; confirm in tech-plan.
- **R4 — two call-sites drift.** Worker + backend inline both assign sentiment. *Mitigation:* shared
  resolve/predict/log helper invoked from both, mirroring how `sentiment_resolver` is duplicated.
- **R5 — worker model mirror drift.** Hand-mirrored models can desync. *Mitigation:* add
  `AICorrection` + both new tables to the worker mirror in the same PR; characterization test the
  shared column set.
- **R6 — promoted model changes user-visible sentiment.** In `auto`, stored `sentiment_label` can
  change. *Mitigation:* only when a promoted model exists; reversible; logged; off by default.

## Rollout & Adoption (self-hosted GTM)

- **Docs:** a `docs/SELF_HOSTING.md` section on the per-org classifier — what it is (honest: per-org
  TF-IDF + logistic regression on your own corrections), the three modes, the per-type readiness gate,
  and how to read the accuracy card. Mirror how M5.1's transformer sentiment + air-gapped pre-bake
  were documented.
- **Roadmap:** flip M5.2 to shipped in `AI-TRACKING.md` (with the honest "spine + sentiment; category
  is the v2 follow-on; real-org promotion is the later exit" note), and add a "Current AI Capabilities"
  row.
- **Adoption signal (post-merge):** an operator can enable `shadow`, generate corrections, and see a
  non-empty accuracy card with an incumbent-vs-challenger delta — provable in the demo/synthetic path
  without waiting on real-org volume.

## Out of Scope

- Category / pain-point / feature-request classifier heads (v2 follow-on).
- Churn ML model (M5.3 — hard-gated at ≥500 labels).
- Local embedding quality / sentence-transformers (M5.4 — parked).
- Cross-tenant / global training on pooled data (against OSS single-tenant model).
- Fine-tuning the operator's BYOK LLM (can't do uniformly across providers).
- Real design-partner-org validation (the later exit, not this PR).
