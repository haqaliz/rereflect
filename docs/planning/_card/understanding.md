# Understanding — feat/urgency-classifier-head

Synthesized from four parallel read-only digs (analysis-engine, backend, worker, frontend) against the
shipped **category head** precedent (`docs/planning/per-org-category-classifier/`).

## What this is really asking

Add a **third self-improving classifier head — "urgency"** — to the M5.2 per-org corrections flywheel,
mirroring how the **category** head was added after **sentiment**. The flywheel: users correct the AI →
corrections stored as `AICorrection` rows → weekly per-org retrain trains a challenger → promoted only if
it beats the incumbent on held-out data → predictions optionally override the analyzer at ingest
(off/shadow/auto). Urgency mirrors the boolean `FeedbackItem.is_urgent` as a **binary** classifier
(`not_urgent` / `urgent`).

## Why it's tractable (the spine is already generic)

The classifier spine was deliberately built type-generic. Confirmed per layer:

- **analysis-engine** (`corrections_classifier/`): `classifier_type` is a plain string, never branched on.
  `fetch_correction_rows(..., correction_type=)`, `train_classifier(..., classifier_type=)`, `predict()`
  (already has a **binary sigmoid path** for 2-class), and `evaluate(..., labels=)` all parameterized.
  **New code = 3 tiny edits**: add `URGENCY_LABELS=("not_urgent","urgent")` to `labels.py`, add
  `build_urgency_dataset()` to `dataset.py`, export both from `__init__.py`. Simpler than category —
  fixed closed vocab, so **no `derive_labels`, no fair-A/B intersection**.
- **worker** (`tasks/classifier_training.py`): retrain loop already iterates
  `_CLASSIFIER_TYPES=("sentiment","category")` × orgs. Redis lock is **per-type+per-org**
  (`lock:classifier_refit:{type}:{org}`) → urgency never deadlocks against the others. `_promote`,
  `_insert_eval_run`, purge, beat schedule (Mondays 06:30 UTC), include — all untouched. Changes:
  append `"urgency"` to `_CLASSIFIER_TYPES` + add an urgency branch in `_dataset_and_incumbent_for`
  (wire `build_urgency_dataset`, a new binary incumbent predictor, `eval_labels` policy).
- **backend** (`ai_correction.py`, `ai_settings.py`, `org_ai_config.py`, `public_api.py`): `correction_type`
  is a free `String(50)` — `"urgency"` needs **no schema change to store**. The classifier-mode plumbing
  is a mechanical copy of the `category_classifier_mode` block (model column + migration + GET/PATCH +
  resolver map `MODE_COLUMN_BY_CLASSIFIER_TYPE`).
- **frontend** (`AISettingsGeneral.tsx`, `ClassifierAccuracyCard.tsx`, `ai-settings.ts`,
  `classifier-accuracy.ts`): accuracy/rollback API client is **already type-generic** (pass `"urgency"`,
  zero change). Add `urgency_classifier_mode` to the TS types, a 4th `<Select>` card (copy category),
  a `TYPE_COPY.urgency` entry, and one `<ClassifierAccuracyCard classifierType="urgency" />`.

## The one real open question (must resolve in PRD) — the CAPTURE SEAM

The head is worthless without training signal, and **urgency corrections are not captured today**:

- The **only** user/actor-driven `is_urgent` mutation in the whole backend is the **public-API**
  `PATCH /api/public/v1/feedback/{id}` (`public_api.py:476`) — and it currently records **nothing**.
- There is **no internal (JWT) urgent-toggle endpoint** and **no frontend urgent-toggle control**. The
  feedback detail page emits sentiment/category corrections, but has no urgency control. The internal
  `PATCH /feedback/{id}` only edits text/source and re-analyzes (it clears `is_urgent` then recomputes
  via the analyzer heuristic — that reset is analyzer-driven and must **not** be captured as a correction).

So the sentiment/category flywheel is fed by **dashboard** corrections, but urgency has no dashboard
surface. **Decision needed:**

- **Option A — public-API only (minimal):** emit `AICorrection(correction_type="urgency")` at
  `public_api.py:476` when `is_urgent` changes. Small, but only API-integrated orgs ever feed the head;
  dashboard-only operators get no urgency flywheel. Weak.
- **Option B — add the dashboard seam too (recommended, matches sentiment/category):** add an internal
  urgent-toggle (endpoint + a control on the feedback detail / urgent-feedbacks page) that emits the
  urgency correction, **plus** the public-API capture. This makes the flywheel actually turn for the
  primary (dashboard) user, consistent with how every other head gets its signal.

Recommendation: **Option B**, since the moat rationale (self-improving on the operator's own corrections)
depends on the dashboard producing signal.

## Incumbent predictor (design note for the plan)

The current urgency signal is a keyword/rule scorer (`analyzer/core.py` ~line 310, `categorizer.py` ~483,
worker `tasks/analysis.py:663-708` emitting "Not urgent"/"Marked as urgent"). The urgency head's
**incumbent** must wrap that existing heuristic as a binary predictor emitting `not_urgent`/`urgent`, so
the challenger is only promoted when it beats the keyword heuristic on the org's held-out corrections —
the honest bar to state in the UI copy.

## Affected areas (services)

- `services/analysis-engine/src/analyzer/corrections_classifier/` — core (labels, dataset, export)
- `services/worker-service/src/tasks/classifier_training.py` + `services/analysis-engine` incumbent
- `services/backend-api/src/{models/org_ai_config.py, api/routes/ai_settings.py, api/routes/public_api.py,
  api/routes/feedback.py (new internal toggle?), services/ai_correction_service.py}` + Alembic migration
  (heads-check: repo has multiple alembic heads)
- `services/frontend-web/` — AI settings toggle + accuracy card (+ feedback-detail urgent control if Option B)

## Aspects (natural decomposition, mirrors category head)

1. **urgency-core** (analysis-engine): `URGENCY_LABELS` + `build_urgency_dataset` + exports.
2. **capture-seam** (backend + frontend): record `correction_type="urgency"` on urgent-flag override
   (public API always; internal endpoint + dashboard control if Option B).
3. **data-and-config** (backend): `urgency_classifier_mode` column + migration + GET/PATCH + resolver map.
4. **worker-trainer** (worker): `_CLASSIFIER_TYPES += "urgency"` + `_dataset_and_incumbent_for` branch +
   binary incumbent.
5. **predict-seam** (worker/analysis): urgency `resolve_classifier` call site overriding `feedback.is_urgent`
   at ingest under shadow/auto.
6. **settings-frontend** (frontend): mode toggle + `ClassifierAccuracyCard classifierType="urgency"`.

## Contradictions / flags

- Brief said "dashboard flag toggle + public-API PATCH" as the capture surface, but the **dashboard toggle
  does not exist yet** — building it is in scope only if Option B is chosen. Flagged, not papered over.
- `churn_risk` head explicitly **out of scope** (M5.3 data-gated at ~500 labels).
