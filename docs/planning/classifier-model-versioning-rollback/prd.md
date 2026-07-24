# PRD — Durable Classifier Model Rollback + Versioning

**Slug:** `classifier-model-versioning-rollback`
**Branch:** `feat/classifier-model-versioning-rollback`
**Type:** feat (freeform; no GitHub issue — selected via `rereflect-next`, scope pivoted after Phase-2 dig)
**Status:** Draft — pending review gate
**Author:** Rereflect (via `rereflect-begin-fast`)
**Source:** `docs/planning/_card/card.md` + `docs/planning/classifier-model-versioning-rollback/understanding.md`

---

## Problem Statement

Rereflect's flagship moat is the **per-org self-improving classifier flywheel**
(M5.2 — sentiment/category/urgency heads trained on the org's own corrections,
auto-promoted weekly; `AI-TRACKING.md:37,63-65`). M5.2 already shipped a
**one-click rollback** (`POST /classifier/rollback`) and an A/B accuracy card, and
documents the promoted model as *"reversible via one-click rollback."*

**That reversibility is an illusion.** The Phase-2 dig found that the weekly
retrain job silently undoes every manual rollback:

- `retrain_all_orgs` runs **Mondays 06:30 UTC for every org**
  (`worker-service/src/tasks/classifier_training.py`; `celery_app.py:210-213`).
- Auto-promotion compares a fresh challenger against a **static heuristic** (VADER
  / keyword categorizers), **not** against the active model, and promotes iff
  `challenger_macro_f1 - heuristic_macro_f1 >= 0.02` (`evaluate.py:262`).
- `_promote` deactivates whatever row is currently active — including the one the
  operator just rolled back to — and inserts a **brand-new** active row
  (`classifier_training.py:182-232`). `classifier_mode` (`off|shadow|auto`) does
  **not** gate this; it's read only at predict time.
- There is **no pin / hold / freeze** anywhere in the codebase.

So in the common case (an org with enough corrections to have ever promoted a
model), a manual rollback is **erased within a week, with no notice.** The rollback
button advertises a safety net that does not hold.

Two secondary gaps compound it:

- **No true versioning.** Rollback only reactivates the single most-recent prior
  version; there is no way to see or choose among the stored versions. The accuracy
  route fetches only the active model (`_get_active_model`). M4.2's *"Model
  versioning: track model performance over time, rollback if accuracy drops"*
  (`AI-TRACKING.md:384`) is genuinely unbuilt.
- **No audit trail.** Rollback emits no `AuditLog`, unlike other admin mutations
  (`team.py` uses `audit_service.log_action`).

**Who has this problem:** self-hosting operators (admin/owner) running the M5.2
classifier flywheel who roll back a bad auto-promotion and reasonably expect it to
stick.

**Cost of the status quo:** the advertised rollback is worse than none — it
signals control the operator doesn't have. A model the operator explicitly rejected
returns to production within 7 days, unlogged.

## Goals & Success Metrics

- **G1 — A manual rollback is durable.** After an operator rolls back a
  classifier, the next weekly `retrain_all_orgs` run does **not** re-promote a
  challenger for that (org, classifier_type).
  - *Metric (tested):* given a held (org, type), running the promotion path leaves
    `is_active` on the operator's chosen version unchanged, and writes an
    `OrgClassifierEvalRun` with `decision="held"`.
- **G2 — The hold is legible and reversible.** The operator can see that
  auto-promotion is paused for a classifier and resume it in one click.
  - *Metric (tested):* `GET /classifier/accuracy` (or the versions endpoint)
    reports the hold state; a resume endpoint clears it; after resume, the
    promotion path can promote again.
- **G3 — Operators can see and choose among versions.** A version list surfaces
  every stored version with its metrics; rollback can target any valid prior
  version, not just the most recent.
  - *Metric (tested):* `GET /classifier/versions?classifier_type=` returns all
    stored versions newest-first with `id/fit_at/macro_f1/label_count/is_active`;
    rolling back to a specified in-org, same-type version activates exactly that
    one (one active row invariant preserved).
- **G4 — Rollback and hold changes are audited.** Each rollback, hold-engage, and
  resume writes an `AuditLog` row.
  - *Metric (tested):* a rollback produces an `AuditLog` with the actor, action,
    and `{classifier_type, from_model_id, to_model_id}` details.
- **G5 — Zero regression to the flywheel.** Un-held orgs behave byte-identically to
  today (train → A/B → auto-promote weekly). Predict-time behavior and the
  promotion margin are unchanged.
  - *Metric (tested):* existing worker promotion tests + `classifier_predict`
    tests pass unchanged; a non-held org still promotes on `delta >= 0.02`.

## User Personas & Scenarios

- **CS lead / operator (admin or owner), primary.** In Settings → AI → Accuracy,
  notices the auto-promoted sentiment model is misclassifying. Clicks **Roll back**
  → picks the prior version that was good → confirms. The card now shows
  **"Auto-promotion paused"** for sentiment. The following Monday the model is still
  their chosen version. Weeks later the card shows *"a newer candidate would beat
  your held version by +0.04"*; they click **Resume auto-promotion** and the
  flywheel takes over again.
- **Member (non-admin).** Sees the accuracy + version history read-only; the
  rollback/hold/resume controls are absent (403 on the endpoints), as today.

## Requirements

### Must-have
- **M1 — Auto-promotion hold (config flag).** Per-type booleans on `OrgAIConfig`
  (`sentiment_autopromote_hold`, `category_autopromote_hold`,
  `urgency_autopromote_hold`), default `false`. Mirrored to the worker
  `OrgAIConfig`/config read + Alembic migration; parity maintained.
- **M2 — Worker honors the hold.** In `retrain_org`, when the (org, type) is held:
  still train + evaluate the challenger, write an `OrgClassifierEvalRun` with
  `decision="held"` and the computed `macro_f1_delta`, but **do not** call
  `_promote` / flip `is_active`. Un-held path unchanged.
- **M3 — Rollback engages the hold.** `POST /classifier/rollback` sets the
  matching `<type>_autopromote_hold = true` in the same transaction as the
  `is_active` flip **when it reactivates a prior version**. A **disable-only**
  rollback (no prior version exists → `has_model=false`) does **NOT** engage the
  hold — freezing the flywheel for an org that has no model would permanently block
  it from ever training a first one (see R5). (Rollback semantics otherwise
  unchanged: atomic deactivate→flush→activate, one-active invariant.)
- **M3a — Race guard vs. the concurrent weekly job (durability crux).** The worker
  and the rollback endpoint run in separate processes/transactions, so a rollback
  fired while `retrain_all_orgs` is mid-run must not be clobbered by `_promote`.
  The worker must check the hold **as late as possible**: after acquiring the
  per-(type,org) Redis refit lock, re-read the `OrgAIConfig` row (row-locked,
  `SELECT … FOR UPDATE` on Postgres) immediately before `_promote`, and abort the
  promote if held. The check-hold and the deactivate→insert live in one worker
  transaction. *Tested:* a hold committed before `_promote`'s config re-read leaves
  the active version unchanged.
- **M4 — Roll back to a chosen version.** Extend rollback to accept an optional
  target version id (query/body). When provided, validate the target is same-org,
  same-`classifier_type`, and not already active; activate exactly it. When absent,
  preserve today's "reactivate most-recent prior" default. Reject a target from
  another org/type with 404 (no cross-org leak).
- **M5 — Resume auto-promotion.** `POST /classifier/resume?classifier_type=` clears
  the hold (idempotent; 200 even if not held). Admin/owner only.
- **M6 — Version list endpoint.** `GET /classifier/versions?classifier_type=`
  returns all stored versions for the (org, type), newest-first, each with `id`,
  `fit_at`, `macro_f1`, `label_count`, `is_active`. Includes the current hold
  state for the type. Admin/owner? — **read allowed for all roles** (matches the
  read-only accuracy card); mutations stay admin/owner.
- **M7 — Audit logging.** `log_action` on rollback (`classifier_rolled_back`),
  hold-engage (implicit in rollback details), and resume
  (`classifier_autopromote_resumed`), with `target_type="org_classifier_model"`
  and `details={classifier_type, from_model_id, to_model_id, held}`. Requires
  injecting `current_user` + `Request` into these routes.
- **M8 — `classifier_type` validation.** The rollback/resume/versions endpoints
  reject an unknown `classifier_type` with **400** (whitelist
  `{sentiment, category, urgency}`), replacing today's silent-empty/404 behavior.
- **M9 — Frontend.** Extend `ClassifierAccuracyCard`: a **version-history table**
  (fit_at, macro-F1, labels, active badge, "Roll back to this" per non-active row),
  a persistent **"Auto-promotion paused"** indicator + **Resume** button when held,
  and a **confirm dialog** (plain `Dialog`, no AlertDialog) + `sonner` toast on all
  three actions. Admin/owner gates the mutating controls.

- **M10 — Operator docs + tracking.** Update `AI-TRACKING.md` (check the M4.2:384
  "Model versioning… rollback" box; add a durable-rollback note under M5.2),
  `SELF_HOSTING.md` (hold/resume behavior + the Mon 06:30 UTC promotion cadence the
  hold pauses), and `CHANGELOG.md`.

### Should-have
- **S1 — Stale-hold nudge.** When held and the latest `decision="held"` eval run
  shows a positive delta over the active version, surface *"a newer candidate would
  beat your held version by +X — Resume?"* on the card. (Data already produced by
  M2; this is presentation.)
- **S2 — Purge safety note.** Confirm the rolled-back/active version is never
  purged. Because the 90-day purge deletes only `is_active=False` rows
  (`purge_old_classifier_models`, `classifier_training.py:436-458`) and the
  held version stays `is_active=True`, this holds **without** code change — assert
  it with a test rather than adding logic.

### Nice-to-have
- **N1 — Held state on the churn/AI readiness surfaces** (out unless trivial).

## Technical Considerations

**Services changed:** `backend-api` (model, migration, routes, schema, audit),
`worker-service` (config mirror + `retrain_org` hold check), `frontend-web` (card +
client). `analysis-engine` unchanged (promotion *policy* untouched — G5).

**Data model (Alembic, one migration):** add three nullable
`Boolean` columns to `org_ai_config` (`sentiment_autopromote_hold`,
`category_autopromote_hold`, `urgency_autopromote_hold`), `server_default=false`,
default `false`. Mirror the columns in the worker's `OrgAIConfig` definition. Single
head; new `down_revision` = current head (run live `alembic heads` — do NOT grep
version files, per repo memory).

**Model parity:** `OrgClassifierModel`/`OrgClassifierEvalRun` are unchanged (no new
columns there — the hold lives on config), so the classifier-model parity test is
unaffected; the `OrgAIConfig` mirror in the worker must gain the three columns and
stay in sync.

**API contracts (all under `/api/v1/settings/ai`, existing router):**
- `GET  /classifier/versions?classifier_type=` → `{ classifier_type, hold: bool,
  versions: [{id, fit_at, macro_f1, label_count, is_active}] }` (read: any role).
- `POST /classifier/rollback?classifier_type=[&to_version_id=]` → engages hold,
  activates target (or most-recent-prior), audits. `ClassifierAccuracyResponse`
  (extended with `hold`). Admin/owner.
- `POST /classifier/resume?classifier_type=` → clears hold, audits. Admin/owner.
- Unknown `classifier_type` → 400 on all three.

**Auth/multi-tenancy:** all queries org-scoped via `current_org.id`; cross-org
target ids invisible → 404. Mutations `require_admin_or_owner`.

**Worker interaction (the crux):** `retrain_org` reads the org's config for the
type; if held, run train+eval, `_insert_eval_run(decision="held")`, skip `_promote`.
`retrain_all_orgs` still iterates all orgs (unchanged); only the promote step is
gated. Redis refit-lock behavior unchanged.

**Frontend:** `ClassifierAccuracyCard` (`'use client'`, inside the AI page's
`<Suspense>`); axios `apiClient` (auto-auth); `sonner` toast (global Toaster);
confirm via `Dialog` (pattern: `ConfirmSuggestionDialog.tsx`); theme tokens only
(`var(--chart-1)`, `color-mix(in oklch, …)`). pnpm: `pnpm --filter frontend-web
test|lint`.

**Testing:** backend self-contained helpers + SQLite in-memory `client`/`db`
(partial index exercised via `sqlite_where`); worker promotion test extended for the
held branch; frontend vitest (mock `@/lib/api-client`) + component test reusing
`ClassifierAccuracyCard.test.tsx` fixtures.

## Risks & Open Questions

- **R1 — Held-and-forgotten → stale model.** Mitigated by M2 (keep logging held
  eval runs) + S1 (nudge when a challenger would beat the held version). Accepted:
  we notify, we don't auto-resume (auto-resume would re-introduce the silent
  override this feature exists to kill).
- **R2 — Worker/back-end config drift.** The three new columns must land in both
  `OrgAIConfig` definitions + migration; the worker reads its own mirror. Parity
  test / characterization guards this.
- **R3 — `to_version_id` targeting a purged version.** A version id from a stale UI
  could be gone (90-day purge). Endpoint returns 404; the card refetches the list.
- **R4 — Behavior when held but the operator never rolled back** (e.g. they hit
  Resume then nothing): resume is idempotent; no active-model change. Fine.
- **R5 — Disable-only rollback must not permanently freeze a modelless org.**
  Resolved by M3: the hold engages only on reactivate-a-prior, never on
  disable-only. A disabled org keeps auto-training a first model as today.
- **R6 — Scope-choice acknowledged (the hard question).** This feature makes the
  *manual escape hatch* durable; it does **not** prevent a bad auto-promotion from
  reaching production unattended in the first place (that would need shadow-first /
  promote-then-approve gating — a larger redesign, deliberately out of scope). We
  are choosing "make the escape hatch real" over "prevent the fire." Named so the
  choice is explicit, not accidental.
- **Open:** should `resume` also trigger an immediate off-schedule retrain, or wait
  for Monday? *Default:* wait for the scheduled run (no ad-hoc trigger) — keeps
  scope tight; revisit if operators ask.

## Out of Scope

- Changing the promotion **algorithm**, the `0.02` margin, `MIN_LABELS`, or the
  static-heuristic incumbent choice.
- Predict-time `classifier_mode` (`off|shadow|auto`) semantics — untouched.
- A model-diff / feature-weight inspection UI; per-version freeform notes.
- Auto-resume / time-boxed holds; an ad-hoc "retrain now" button.
- Any change to `OrgClassifierModel`/`OrgClassifierEvalRun` columns (hold lives on
  config).
- Industry benchmarks, per-org churn ML (M5.3, data-gated) — unrelated.
