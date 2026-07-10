# Aspect Spec — data-layer

**Parent PRD:** `../prd.md` (M5.2 per-org-corrections-classifier)
**Sequence:** FIRST — foundation; B/C/D/E depend on this.

## Problem slice / outcome

Persist per-org classifier artifacts + eval history + the per-org mode toggle, mirroring the proven
`churn_calibration_models` conventions, in **both** the backend ORM and the worker mirror. After this
aspect, other aspects can read/write the schema.

## In-scope

1. **`org_classifier_models`** table + `OrgClassifierModel` model (backend
   `src/models/`, exported from `src/models/__init__.py`):
   - `id` PK; `organization_id` FK→organizations **nullable** (NULL = global/base); `classifier_type`
     VARCHAR (v1 `'sentiment'`); `model_json` JSON (TF-IDF vocab/idf + logreg coef/intercept + classes —
     **JSON, never pickle**); `label_count` INT; `precision`/`recall`/`macro_f1`/`accuracy`
     Numeric(5,4) nullable; `fit_at` DateTime; `is_active` Boolean.
   - **Partial-unique index** `uq_org_classifier_one_active` on `(organization_id, classifier_type)`
     `WHERE is_active` (postgres) / `WHERE is_active = 1` (sqlite) — copy the churn model's dialect-aware
     partial index exactly.
2. **`org_classifier_eval_runs`** table + `OrgClassifierEvalRun` model (mirror `ChurnBacktestRun`):
   `id`; `organization_id` FK; `classifier_model_id` FK→org_classifier_models nullable; `classifier_type`;
   `incumbent_macro_f1`/`challenger_macro_f1`/`macro_f1_delta` Numeric(5,4) nullable; `decision` VARCHAR
   (`promoted`|`retained`|`skipped`); `n` INT; `duration_ms` INT; `notes` TEXT; `created_at` DateTime.
3. **`OrgAIConfig.classifier_mode`** VARCHAR(20) NULL `server_default='off'` (values `off`/`shadow`/`auto`)
   — added to backend `src/models/org_ai_config.py` **and** worker `src/models/__init__.py` mirror.
4. **Worker mirrors:** add `OrgClassifierModel` + `OrgClassifierEvalRun` **and** the currently-missing
   **`AICorrection`** mirror class (table `ai_corrections`, matching columns) to
   `services/worker-service/src/models/__init__.py`.
5. **One Alembic migration** (backend): create both tables + add `classifier_mode`. `down_revision =
   '6ad1dc4335f1'` (current single head). Mnemonic revision id style.

## Out-of-scope

- Any training/predict/schedule logic (aspects B–E). No API/UI.

## Acceptance criteria (testable)

- `alembic heads` shows a single head before and after; `alembic upgrade head` then `downgrade -1`
  round-trips cleanly on sqlite + (documented) postgres.
- Inserting two `is_active=True` rows for the same `(org, classifier_type)` violates the partial-unique
  constraint; differing `classifier_type` or `is_active=False` is allowed.
- `classifier_mode` defaults to `'off'` on a freshly-created `OrgAIConfig` (server_default) and is
  readable via `getattr(config, 'classifier_mode', 'off')` on an un-migrated row.
- Worker can `from src.models import AICorrection, OrgClassifierModel, OrgClassifierEvalRun` and query
  `ai_corrections` in the shared DB.
- Backend + worker column sets for the mirrored models match (characterization test asserting column
  names/types parity).

## Dependencies & sequencing

- **Blocks:** B, C, D, E. **Blocked by:** none.
- Gotcha: keep model definitions in sync across the two services (the file itself notes "should be in a
  shared package"). Never pickle. No heavy imports here.

## Open questions / risks

- Confirm Numeric(5,4) matches churn convention (it does). Confirm sqlite partial-index `WHERE is_active
  = 1` form is what the churn model uses (verify in `churn_calibration.py`).
