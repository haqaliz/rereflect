# Aspect Spec — settings-api-and-accuracy-card

**Parent PRD:** `../prd.md` (M5.2 per-org-corrections-classifier)
**Sequence:** after `data-layer`; UI reads data best once worker-trainer exists (dev with seeded rows).

## Problem slice / outcome

Operator-facing surface: a per-org mode toggle (off/shadow/auto) and an honest accuracy/delta card
under Settings → AI, mirroring the M5.1 `SentimentAccuracyCard` + churn-accuracy card patterns.

## In-scope

1. **Settings API** (`backend-api/src/api/routes/ai_settings.py`): add `classifier_mode` to the GET/PATCH
   request + response Pydantic models; validate against `{off, shadow, auto}` (422 on invalid), wired
   through `_get_or_create_config` + `_build_settings_response`. Light deps guard (TF-IDF needs only
   scikit-learn) analogous to `_sentiment_transformer_deps_available()`.
2. **Accuracy endpoint** `GET /api/v1/settings/ai/classifier/accuracy` (mirror the sentiment-accuracy
   endpoint shape): returns active model summary (kind label, `label_count`/n, macro_f1, fit_at,
   is-ready-per-type flag with count vs threshold) + last-N `org_classifier_eval_runs`
   (incumbent vs challenger macro_f1, delta, decision, n, created_at). Schema in `src/schemas/`.
3. **(Optional should-have)** `POST /api/v1/settings/ai/classifier/rollback` — deactivate the active
   model / re-activate the prior version (reversible).
4. **Frontend** (`frontend-web`): Settings → AI mode toggle (off/shadow/auto) calling PATCH; an
   accuracy/delta card (reuse `SentimentAccuracyCard`/churn-accuracy card structure) showing model kind
   ("per-org TF-IDF + logistic regression"), n, incumbent-vs-challenger macro-F1 + delta + last-N runs,
   a **"not ready"** state (count vs per-type threshold), and a **Roll back** action if the endpoint
   ships. Honest copy recommending `shadow` until n is substantial.

## Out-of-scope

- Training/predict/schedule (B/C/D). Category task (v2).

## Acceptance criteria (testable)

- PATCH `classifier_mode` persists + round-trips in GET; invalid value → 422; org-scoped.
- Accuracy endpoint: empty org → ready=false with count 0 and no runs; org with seeded model + runs →
  correct active summary + ordered last-N runs; cross-org isolation (org A never sees org B).
- Frontend: card renders loading / populated (with delta + n) / not-ready / empty / error states;
  toggle updates mode; matches existing AI-settings tab patterns and theme variables (no hardcoded
  colors). Component + a11y tests mirror `SentimentAccuracyCard` tests.
- Rollback (if shipped): flips active model; accuracy card reflects the change.

## Dependencies & sequencing

- **Blocked by:** data-layer (schema + mode column). Reads rows produced by worker-trainer; dev/test with
  hand-seeded `org_classifier_models` + `org_classifier_eval_runs`. **Blocks:** none.

## Open questions / risks

- Card placement: extend the existing Settings → AI "accuracy"/"Readiness" tab vs a new sub-card —
  recommend co-locating with the M5.1 SentimentAccuracyCard (confirm in tech-plan).
- Whether rollback ships in this PR (should-have) or a follow-up — recommend include if cheap.
