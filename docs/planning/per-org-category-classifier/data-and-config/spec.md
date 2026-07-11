# Aspect: data-and-config

**Slice:** the one schema change — a per-type category mode — plus AI-settings plumbing.

## Problem slice & outcome
Operators need to enable/disable the category head independently of sentiment. Add
`category_classifier_mode` (off|shadow|auto) to `OrgAIConfig` and expose it on the AI settings
GET/PATCH, without touching the already-type-generic classifier/eval-run/correction tables.

## In scope
- **Alembic migration** adding `org_ai_config.category_classifier_mode String(20) NULL server_default 'off'`
  (down_revision = current head `v2w3x4y5z6a7` or later; verify head first — repo has had multiple heads).
- ORM field on **both** mirrors: `services/backend-api/src/models/org_ai_config.py:24` (beside
  `classifier_mode`) and the worker mirror `services/worker-service/src/models/__init__.py:~607`.
- AI settings API (`services/backend-api/src/api/routes/ai_settings.py`):
  - `AISettingsResponse.category_classifier_mode: str = "off"` (mirror `:69`) built from `getattr(config, ...)`.
  - `AISettingsUpdate.category_classifier_mode: Optional[str]` (mirror `:79`); validate against
    `VALID_CLASSIFIER_MODES` + the sklearn dependency guard (`:519-541`, `_classifier_deps_available`);
    persist to the new column.
- Column-parity characterization test (mirror `test_worker_and_backend_org_classifier_model_columns_match`).

## Out of scope
- New classifier/eval-run tables (already type-generic). Any resolver/seam reading of the mode (→ predict-seam).
- Frontend (→ settings-and-frontend).

## Acceptance criteria (testable)
- `alembic upgrade head` then `downgrade -1` round-trips cleanly; new column defaults `'off'`.
- `GET /api/v1/settings/ai` returns `category_classifier_mode` (`'off'` for a fresh org).
- `PATCH` with `category_classifier_mode='shadow'` persists; invalid value → 422; `auto` without sklearn
  installed → the same guard error the sentiment path raises.
- Existing `classifier_mode` behavior byte-unchanged (characterization test green).

## Dependencies & sequencing
None upstream. **Blocks:** worker-trainer, predict-seam, settings-and-frontend. Do first.

## Open questions / risks
- Confirm the current single alembic head before authoring `down_revision` (memory notes prior multi-head
  incidents). One migration, one new column — keep it minimal.
