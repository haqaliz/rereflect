# Aspect Spec — data-and-config (backend)

**Service:** `services/backend-api/src/{models/org_ai_config.py, api/routes/ai_settings.py}`,
`services/worker-service` (OrgAIConfig mirror), `services/backend-api/alembic/`.
**Sequence:** before worker-trainer and predict-seam (they read the mode). Independent of core/capture.

## Problem slice / outcome

Operators can set `urgency_classifier_mode ∈ {off, shadow, auto}` per org, persisted and exposed via the
AI settings API, and readable by the predict resolver — exactly like `category_classifier_mode`.

## In scope

- **Model:** add `urgency_classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')`
  to `OrgAIConfig` in `org_ai_config.py` (backend) AND the worker mirror (`worker-service .../models/__init__.py`
  ~line 612/616 area where `classifier_mode`/`category_classifier_mode` live).
- **Migration:** new Alembic revision adding the column. **Check `alembic heads` first** — repo has
  multiple heads (memory: `rereflect-repo-test-gotchas`); set `down_revision` to the correct current head
  (or merge if needed). Mirror the `category_classifier_mode` migration.
- **Settings API (`ai_settings.py`):**
  - `AISettingsResponse` (~:63): add `urgency_classifier_mode: str = "off"`.
  - `AISettingsUpdate` (~:74): add `urgency_classifier_mode: Optional[str] = None`.
  - GET builder (`_build_settings_response`, ~:231-241): populate + pass the field.
  - PATCH (`update_ai_settings`, ~:551-572 category block): copy the category validation+persist block for
    urgency, validating against `VALID_CLASSIFIER_MODES` (`ai_settings.py:45`).
- **Resolver map:** add `"urgency": "urgency_classifier_mode"` to `MODE_COLUMN_BY_CLASSIFIER_TYPE`
  (`worker-service .../services/classifier_resolver.py:47-50`).

## Out of scope

- Any consumption of the mode (that's worker-trainer / predict-seam).
- Frontend (settings-frontend aspect).

## Acceptance criteria (testable, TDD)

- `alembic upgrade head` applies cleanly from the correct head; column exists with default `'off'`.
- GET `/api/v1/settings/ai` returns `urgency_classifier_mode` (default `"off"`).
- PATCH accepts `urgency_classifier_mode` ∈ {off,shadow,auto}, rejects invalid values (422), persists
  independently of the other mode fields (unchanged fields untouched); requires admin/owner.
- `MODE_COLUMN_BY_CLASSIFIER_TYPE["urgency"] == "urgency_classifier_mode"`.
- Worker OrgAIConfig mirror has the column (import + a read test).

## Dependencies / sequencing

Blocks worker-trainer (gating read is actually only at predict-seam, but the column must exist) and
predict-seam. Can run in parallel with urgency-core and capture-seam.

## Risks

- Multiple alembic heads — a wrong `down_revision` breaks `upgrade head`. Verify with `alembic heads`
  and run the migration in a test DB before wiring the rest.
- Keep backend and worker OrgAIConfig mirrors byte-consistent (both have the column, same default).
