# Understanding — durable classifier model rollback + versioning

**Phase 2 dig output.** Scope pivoted (user-approved) after the dig found the
originally-recommended feature already shipped. See `_card/card.md` for the
original brief and the contradiction.

## What is ALREADY shipped (do not rebuild)

Commits `a630c9c` + `cea261b` (M5.2 settings), documented `AI-TRACKING.md:63-65`:

- **A/B comparison** — `GET /api/v1/settings/ai/classifier/accuracy?classifier_type=`
  returns the active model's macro-F1 + last-4 `OrgClassifierEvalRun` rows
  (incumbent vs challenger vs delta). Rendered by
  `ClassifierAccuracyCard.tsx` ("Recent shadow-mode evaluations").
- **One-click rollback** — `POST /classifier/rollback?classifier_type=` deactivates
  the active model and reactivates the **most-recent prior inactive** version
  (or disables if none). Atomic deactivate→flush→activate→commit; honors the
  `uq_org_classifier_one_active` partial-unique index. Admin/owner gated. Tests:
  `tests/test_classifier_rollback.py`. Frontend "Roll back" button (no confirm,
  no toast, fires immediately).

The `[ ]` at `AI-TRACKING.md:384` (M4.2 "Model versioning… rollback") is a **stale
checkbox** — M5.2 delivered the basic version.

## The real, unbuilt problem (this feature)

The shipped rollback is **not durable, is one-step, and is unaudited**:

### 🔴 P1 — The weekly job silently reverts every manual rollback
- `retrain_all_orgs` (worker) runs **Mondays 06:30 UTC for every org**
  (`worker-service/src/tasks/classifier_training.py`; beat key
  `retrain-classifier-weekly`, `celery_app.py:210-213`).
- Auto-promotion compares a fresh challenger against a **static production
  heuristic** (VADER / keyword categorizers) built by `_dataset_and_incumbent_for`
  — **NOT** against the currently-active `OrgClassifierModel`. Promote iff
  `challenger_macro_f1 - heuristic_macro_f1 >= 0.02` (`evaluate.py:262`,
  `MARGIN=0.02`).
- `_promote` (`:182-232`) deactivates whatever row is currently `is_active`
  (i.e. the one the operator just rolled back to) and **inserts a brand-new active
  row**. So in the common case (org has enough corrections that a model was ever
  promoted, challenger still beats the heuristic) the manual rollback is
  **silently discarded within a week**.
- `classifier_mode` (`off|shadow|auto`) does **NOT** gate training/promotion — it's
  read only at PREDICT time (`classifier_predict.py:281-287`). Setting an org to
  `off`/`shadow` does not stop `is_active` from being flipped by the weekly job.
- **There is no pin / hold / freeze / auto_promote flag anywhere** (confirmed grep
  across `OrgClassifierModel` + `OrgAIConfig` + training path).

### 🟡 P2 — One-step, not true versioning
- Rollback only reaches the single most-recent prior version. No
  `GET /classifier/versions` (the accuracy route only fetches the **active**
  model, `_get_active_model`). Operators can't see or choose among N stored
  versions. M4.2:384's "track model performance over time" is genuinely unbuilt.
- Multiple inactive versions per (org, type) DO coexist in the DB (partial-unique
  only fires on `is_active`), so the data for a version list exists.
- **Retention caveat:** `purge_old_classifier_models` is folded into the weekly run
  (`classifier_training.py:~428`). Version history + rollback targets are only as
  deep as the purge keeps — and a pinned/rolled-back version **must not be
  purged**. Reconcile in the plan.

### 🟡 P3 — No audit trail
- Rollback emits no `AuditLog`. The helper exists:
  `src/services/audit_service.py::log_action(db, org_id, user_id, user_email,
  action, target_type, target_id, details, request)` — used by `team.py`
  (`role_changed`, etc.). Rollback currently injects only `current_org`, not
  `current_user`/`Request`, so adding audit needs those two params.

## Target scope (this feature)

1. **Durable hold** — a mechanism so a manual rollback survives the weekly job.
   Leading design: a per-(org, classifier_type) "auto-promotion hold" that the
   worker's `retrain_org`/`_promote` checks and skips (still logging an
   `OrgClassifierEvalRun` with an honest `decision` like `held`). Rolling back
   engages the hold by default (rollback implies distrust of auto-promotion);
   operator explicitly resumes auto-promotion to clear it. **Must be mirrored to
   the worker model copy + migration** (parity test:
   `worker-service/tests/test_model_parity_classifier.py`).
2. **Version history + roll-back-to-version** — `GET /classifier/versions?type=`
   lists all stored `OrgClassifierModel` rows (version, `fit_at`, metrics,
   `is_active`, pinned?); extend rollback to target a specific version id (not
   just most-recent-prior). Frontend version table + confirm dialog + toast.
   Ensure pinned/rolled-back versions are purge-exempt.
3. **Audit** — `log_action` on rollback + hold changes (inject `current_user` +
   `Request`).

## Key files (authoritative)

| Layer | File |
|---|---|
| Model (backend) | `services/backend-api/src/models/org_classifier.py` |
| Model (worker mirror) | `services/worker-service/src/models/__init__.py:845-898` |
| Route + schema | `src/api/routes/classifier_accuracy.py`, `src/schemas/classifier_accuracy.py` |
| Auth deps | `src/api/dependencies.py` (`require_admin_or_owner`, `get_current_org`, `get_current_user`) |
| Audit | `src/services/audit_service.py::log_action` |
| Worker training/promotion | `services/worker-service/src/tasks/classifier_training.py` (`retrain_org`, `_promote`, `_dataset_and_incumbent_for`), `analysis-engine/.../corrections_classifier/evaluate.py` |
| Beat schedule | `worker-service/src/celery_app.py:210-213` (Mon 06:30 UTC) |
| Frontend card | `services/frontend-web/components/settings/ClassifierAccuracyCard.tsx` |
| Frontend client | `services/frontend-web/lib/api/classifier-accuracy.ts` (axios `apiClient`) |
| Frontend mount | `app/(dashboard)/settings/ai/page.tsx` (Accuracy tab, 3× sentiment/category/urgency; inside `<Suspense>`) |

## Conventions to follow

- **Tests:** backend self-contained helpers (`_make_org`/`_make_user`/`_headers`/
  `_make_model`) + `client`/`db` (SQLite in-memory, partial index exercised via
  `sqlite_where`). Frontend **vitest**, mock the axios module (`@/lib/api-client`),
  component tests via `@testing-library/react` + reuse
  `ClassifierAccuracyCard.test.tsx` fixtures.
- **Package manager: pnpm** (`pnpm --filter frontend-web test` / `lint`). CLAUDE.md's
  `npm run` is stale.
- **`classifier_type`** ∈ `sentiment | category | urgency`; currently **unvalidated**
  in the route (String(30), no whitelist) — consider validating in this feature.
- **No `alert-dialog.tsx`** primitive — confirm dialogs use plain `Dialog`
  (pattern: `components/customers/ConfirmSuggestionDialog.tsx`). `Toaster` is
  already global; use `toast` from `sonner`.
- **Theming:** CSS tokens only (`var(--chart-1)`, `var(--destructive)`,
  `color-mix(in oklch, …)`); no hardcoded colors. `<Suspense>` boundary on the AI
  settings page must not be broken.
- **Numeric(5,4)** columns return `Decimal` → cast to `float` in responses.
- **Model parity:** any new column on `OrgClassifierModel`/config must be added to
  BOTH the backend and worker mirror + a migration; parity tests will catch drift.

## Open questions for the interview (Phase 3)

1. **Hold granularity:** pin the specific active *model row* (`is_pinned` on
   `OrgClassifierModel`) vs. a per-type *config* flag
   (`OrgAIConfig.<type>_autopromote_hold`)? (Config flag is simpler to reason about
   and survives model swaps; row-pin ties the intent to an artifact.)
2. **Does rollback auto-engage the hold?** (Recommended yes — durable by default.)
   And how does the operator resume auto-promotion — an explicit "Resume
   auto-promotion" control?
3. **Worker behavior when held:** skip training entirely, or still train + eval but
   log `decision="held"` and don't flip `is_active`? (Latter keeps the A/B signal
   visible so the operator can decide to resume.)
4. **Version list depth + retention:** how many versions to show; guarantee a
   pinned/active version is never purged; does the version list need per-version
   metrics beyond `macro_f1`?
5. **Roll-back-to-version target:** keep the simple "undo last" default AND add
   "roll back to version {id}"? Validate the id is same-org + same-type + inactive.
6. **Audit scope:** log rollback + hold-set + hold-clear; what `action` strings +
   `details` payload (from_model_id, to_model_id, classifier_type, hold state)?
7. **`classifier_type` validation:** reject unknown types (400) as part of this, or
   leave the silent-empty behavior?
