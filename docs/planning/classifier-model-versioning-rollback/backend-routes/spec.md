# Aspect spec — backend-routes

**Parent PRD:** `../prd.md` (M3, M4, M5, M6, M7, M8) · **Depends on:** `data-model-and-migration`.
All under existing router `services/backend-api/src/api/routes/classifier_accuracy.py`
(prefix `/api/v1/settings/ai`). Schemas in `src/schemas/classifier_accuracy.py`.

## Problem slice
Extend the classifier settings API so rollback is durable, targetable, resumable,
listable, validated, and audited.

## In scope
- **`classifier_type` validation helper** (M8): whitelist `{sentiment, category,
  urgency}`; unknown → `HTTPException(400)`. Applied to rollback, resume, versions.
- **`GET /classifier/versions?classifier_type=`** (M6): all `OrgClassifierModel`
  rows for (current_org, type), `order_by(fit_at.desc())`, each →
  `{id, fit_at, macro_f1, label_count, is_active}`; plus `hold: bool` (from
  `OrgAIConfig`) and `classifier_type`. New Pydantic `ClassifierVersionsResponse` +
  `ClassifierVersionSummary` (cast `Numeric`→`float`). Read: any authenticated org
  user (deps: `get_current_user` + `get_current_org`), no admin gate.
- **`POST /classifier/rollback?classifier_type=[&to_version_id=]`** (M3, M4):
  - `to_version_id` present → validate it's same-org, same-type, `is_active=False`,
    exists → else 404. Deactivate current active (flush), activate the target.
  - `to_version_id` absent → today's behavior (reactivate most-recent prior, or
    disable-only if none).
  - **Engage hold** (`<type>_autopromote_hold=true`) in the SAME transaction **iff a
    prior/target version was reactivated**; disable-only rollback does NOT engage the
    hold (PRD R5). Commit once.
  - Response: `ClassifierAccuracyResponse` extended with `hold: bool`.
  - Audit (M7): `log_action(action="classifier_rolled_back",
    target_type="org_classifier_model", target_id=<activated id or None>,
    details={classifier_type, from_model_id, to_model_id, held})`.
- **`POST /classifier/resume?classifier_type=`** (M5): clear the hold (idempotent,
  200 even if already false). Audit `action="classifier_autopromote_resumed"`.
- **Inject `current_user: User = Depends(get_current_user)` + `request: Request`**
  into rollback/resume for `log_action` (today rollback has only `current_org`).
- Extend `_build_response` / `ClassifierAccuracyResponse` with `hold`.

## Out of scope
- Frontend (separate aspect). Worker behavior (separate aspect).
- Changing `_get_active_model`/`_collect_history` semantics of `GET /accuracy`
  beyond adding the `hold` field.

## Acceptance criteria (testable) — follow existing self-contained test helpers
- Unknown `classifier_type` → 400 on versions/rollback/resume.
- `GET /versions`: seeded 3 versions (1 active) → returns 3 newest-first with correct
  `is_active`; `hold` reflects config; cross-org versions invisible.
- Rollback to a specific inactive `to_version_id` activates exactly it; exactly one
  active row remains; `hold` becomes true; audit row written with from/to ids.
- Rollback with cross-org or wrong-type `to_version_id` → 404 (no leak).
- Disable-only rollback (no prior) → `has_model=false`, `hold` stays **false** (R5),
  no crash; re-call idempotent-404 as today.
- Resume clears hold; idempotent second call still 200.
- Member role → 403 on rollback/resume; 200 on versions (read).
- Existing `test_classifier_rollback.py` / `test_classifier_accuracy_route.py`
  adjusted for the new `hold` field + engage-hold behavior (default-path rollback now
  sets hold when it reactivates a prior).

## Dependencies / notes
- Audit helper: `src/services/audit_service.py::log_action(db, org_id, user_id,
  user_email, action, target_type, target_id, details, request)`.
- Preserve the atomic deactivate→flush→activate ordering (partial-unique index).
- `OrgAIConfig` may not exist for an org yet — get-or-create/guard before setting a
  hold (check how `ai_settings.py` upserts config).

## Open questions / risks
- Whether `to_version_id` should also be accepted as a JSON body vs query — pick
  query for consistency with `classifier_type` (client already query-based).
