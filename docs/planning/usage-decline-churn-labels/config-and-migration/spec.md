# Aspect — config-and-migration

**PRD:** `../prd.md` (M2)
**Sequence:** 1st. Blocks `worker-detector` and `frontend-settings-and-evidence`.

## Problem slice

There is no non-CRM home for a churn-label opt-in. Default-deny is the house pattern
(`models/hubspot_integration.py:47-48`) and the safety property; without a config home this feature
either breaks default-deny or overloads an unrelated knob.

## User outcome

An operator can set, per org, whether usage-decline churn-label detection is `off` (default),
`shadow`, or `active`, and tune `sustain_days` — through the existing Settings → AI surface.

## In scope

- Two columns on `OrgAIConfig` (`services/backend-api/src/models/org_ai_config.py`), alongside the
  existing `health_weight_usage` and `*_classifier_mode` columns:
  - `usage_churn_labels_mode` — `String(20)`, `server_default='off'`, values `off|shadow|active`.
    Follow the shipped `classifier_mode` / `category_classifier_mode` / `urgency_classifier_mode`
    column shape exactly (nullable with a server_default, per `:24-33`).
  - `usage_churn_label_config` — `JSON`, nullable, `{"sustain_days": 7}`.
- One Alembic migration.
  - **Run `alembic heads` LIVE at write time** and chain off what it returns. It is
    `a1c2d3e4f5a6` today (verified live 2026-07-23, single head) — but re-run the tool.
    **Do not derive the head by grepping `down_revision` strings**: the `crm-churn-labels` PRD had
    to publish a correction for a fabricated two-head fork produced by exactly that shortcut.
  - Migration must be reversible (`downgrade` drops both columns).
- Mirror both columns into the worker's model copy
  (`services/worker-service/src/models/__init__.py`) — the worker cannot import backend-api code.
  Follow the existing mirroring convention and its parity test.
- Read/write the two fields on the existing AI-settings endpoints
  (`services/backend-api/src/api/routes/ai_settings.py`), with Pydantic validation:
  mode ∈ `{off, shadow, active}`; `sustain_days` an int in a sane bounded range (reject 0/negative;
  cap generously, e.g. ≤ 90). Unknown mode → 422.

## Out of scope

- Any detector behaviour (that is `detector-core` / `worker-detector`).
- The settings **UI** (that is `frontend-settings-and-evidence`).
- Routing anything through `/integrations/{provider}/churn-labels` — hard fence, that module
  `KeyError`s on a third provider (`crm_churn_label_options.py:244`).
- Changing any existing `OrgAIConfig` column or its defaults.

## Acceptance criteria (testable)

1. A fresh `OrgAIConfig` row has `usage_churn_labels_mode == 'off'` and
   `usage_churn_label_config IS NULL` — **default-deny proven by test.**
2. Migration `upgrade` then `downgrade` runs clean; after `downgrade` neither column exists.
   (Follow the existing migration-test pattern, e.g. `tests/test_usage_trend_fields_migration.py`.)
3. `alembic heads` returns exactly **one** head after the migration is added.
4. Settings PATCH accepts each of `off|shadow|active`; any other value → 422.
5. `sustain_days` bounds enforced: 0, negative, and absurdly large → 422; 7 accepted.
6. Existing `OrgAIConfig` rows are unaffected — pre-existing columns byte-identical before/after
   (characterization test).
7. Worker-side model mirror has both columns; the existing model-parity test passes.

## Dependencies & sequencing

- Depends on nothing. Start here.
- `worker-detector` needs the worker-side mirror; `frontend-settings-and-evidence` needs the API
  contract.

## Open questions / risks

- Whether `sustain_days` belongs in the JSON blob or as its own column. Spec says JSON (matches
  `churn_label_config` precedent and avoids a second migration when more knobs arrive), but a
  planner may reasonably argue for a column. Either is acceptable; pick one and pin it with a test.
- The M3b suppression threshold (`MAX_QUALIFYING_SHARE`) may want to live in this config blob too —
  decide during `detector-core`, and if so it lands here as an additive JSON key (no migration).
