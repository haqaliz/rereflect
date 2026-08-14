# Spec — settings-api-and-churn-accuracy-card (slice 2d)

## Problem slice

Surface the churn head to the operator: mode toggle in Settings → AI, a fourth
incumbent-vs-challenger accuracy card with versions/rollback/resume, and a readiness
readout reflecting the re-derived gate.

## In scope

- **Settings API** (`services/backend-api/src/api/routes/ai_settings.py`):
  `churn_classifier_mode` in `AISettingsResponse`/`AISettingsUpdate`; validation block
  reusing `VALID_CLASSIFIER_MODES` + `_classifier_deps_available` (422 when sklearn
  unavailable). Settings tab copy: "Your model, trained on your data, promoted only when
  measurably better."
- **Accuracy/versions/rollback/resume** (`classifier_accuracy.py`): extend
  `VALID_CLASSIFIER_TYPES` + `_HOLD_COLUMN_BY_TYPE` with `"churn"` — the endpoints are
  already generic via `classifier_type`. RBAC unchanged (admin/owner for rollback/resume).
- **Frontend**:
  - Mode dropdown in `components/settings/AISettingsGeneral.tsx` (mirror the existing
    three toggles).
  - Fourth `<ClassifierAccuracyCard classifierType="churn" />` in the Accuracy tab of
    `app/(dashboard)/settings/ai/page.tsx` (+ `TYPE_COPY` entry) — incumbent-vs-challenger
    macro-F1 + delta + `n`, version history, rollback, hold banner, resume nudge
    (all existing components are type-parameterized).
  - Readiness: `AIReadinessCard`/`ai_readiness.py` reflect the re-derived target from
    aspect 2 (target may change; "under review" caveat copy stays honest); a
    `churn_classifier_mode` note on the Readiness tab.
- **Tests**: settings validation (mode + deps gate), route tests for
  accuracy/versions/rollback/resume with `classifier_type='churn'`, frontend
  `ClassifierAccuracyCard` + settings page tests (assert exactly four cards),
  readiness boundary tests if the target moves.

## Out of scope

- The ML head itself, training, seam (aspects 3-5). Changing `CORRECTION_VOLUME_TARGET`.
- Any plan gating or new pages beyond the existing settings surfaces.

## Acceptance criteria

1. `PATCH /api/v1/settings/ai` accepts `churn_classifier_mode` off/shadow/auto, rejects
   invalid values (422), and rejects when sklearn deps are unavailable.
2. `GET /classifier/accuracy?classifier_type=churn` returns the incumbent-vs-challenger
   card (empty state when no model); versions/rollback/resume work with hold semantics.
3. UI shows the fourth card and the mode toggle; a test asserts four cards render.
4. Readiness target matches the aspect-2 decision and the copy carries the honest caveat.
5. Backend + frontend suites green (`pytest`, `pnpm test`, `pnpm lint`).

## Dependencies / sequencing

- Last aspect: needs the gate decision (2), the core (3), the worker (4), and the seam
  columns (5). Purely additive; no migration of its own.

## Open questions / risks

- Copy wording for the churn card when the incumbent itself is still identity-fallback
  (pre-qualifying org): "No qualifying org yet — labels/500" style honesty, mirroring
  `ModelAccuracyCard` empty states.
