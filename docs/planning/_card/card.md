# Card — Per-org classifier model versioning + rollback

**Type:** feat (freeform; no GitHub issue — selected via `rereflect-next`)
**Slug (branch):** `feat/classifier-model-versioning-rollback`
**Source:** `rereflect-next` recommendation handoff (this session).

---

## Brief (from `rereflect-next`)

Build **per-org classifier model versioning + rollback**, the two unchecked M4.2
items at `AI-TRACKING.md:384-385`:

- `[ ]` **A/B comparison:** show fine-tuned vs default model accuracy side-by-side.
- `[ ]` **Model versioning:** track model performance over time, rollback if
  accuracy drops.

This deepens the M5.2 flagship self-improving-classifier moat
(`AI-TRACKING.md:37` — "corrections flywheel… Track A — flagship moat"). M5.2
auto-promotes a challenger when it beats the incumbent on held-out corrections,
but promotion is **one-directional** — there is no safety net when a promoted
model later degrades on live data, and no operator-facing version history.

## Why this is unblocked (data already exists)

- `services/backend-api/src/models/org_classifier.py`
  - `OrgClassifierModel` — "versioned per-org corrections classifier artifact".
    Stores every trained version with `macro_f1` / `precision` / `recall` /
    `accuracy` / `label_count` / `fit_at` / `is_active`. Partial-unique index
    `uq_org_classifier_one_active` = at most one active model per
    `(organization_id, classifier_type)`.
  - `OrgClassifierEvalRun` — "shadow-mode A/B eval history — incumbent vs
    challenger, one row per run". Stores `incumbent_macro_f1`,
    `challenger_macro_f1`, `macro_f1_delta`, `decision`
    (`promoted | retained | skipped`), `n`, `created_at`.

## Current state / caveats to resolve in the dig

1. **A/B comparison is LARGELY ALREADY SHIPPED.**
   `services/backend-api/src/api/routes/classifier_accuracy.py`
   (`GET /classifier/accuracy`) already returns the active model's metrics **and**
   the eval-run history (`incumbent_macro_f1` vs `challenger_macro_f1` vs
   `macro_f1_delta`), and `ClassifierAccuracyCard.tsx` renders it. So the core of
   this feature is **version-list + rollback**, extending that card — NOT
   rebuilding comparison. Read `classifier_accuracy.py` +
   `ClassifierAccuracyCard.tsx` first.
   - The accuracy route only fetches the **active** model (`_get_active_model`,
     `is_active=True`) — it never lists the version history of
     `OrgClassifierModel` rows. That version-history surface is the gap.

2. **No rollback endpoint exists anywhere** (`grep` finds only `db.rollback()`
   transaction calls). M4.2's "rollback if accuracy drops" is fully unbuilt.

3. **Rollback vs. auto-promotion interaction (the one real design question).**
   The worker's scheduled fit (`services/worker-service/src/tasks/classifier_training.py`)
   auto-promotes a winning challenger, so a manual rollback could be re-overwritten
   by the next scheduled fit. Decide in the PRD/dig: a "pin / hold auto-promotion"
   flag vs. at-minimum honest UI copy stating the next scheduled fit may re-promote.

4. **Rollback write safety.** Reactivating a prior version must be atomic against
   `uq_org_classifier_one_active` (deactivate current + activate target in one
   transaction) and strictly **org-scoped** (never activate another org's model).

## Suggested first slice (from handoff)

1. `GET /classifier/versions?type=` — list all `OrgClassifierModel` rows per
   `classifier_type` (version, `fit_at`, metrics, `is_active`). RED→GREEN.
2. Frontend version-history table + "Roll back to this version" action, extending
   the existing `ClassifierAccuracyCard`.
3. `POST /classifier/versions/{id}/activate` (rollback) — atomic `is_active` flip
   honoring the one-active constraint, org-scoped, with a timeline/audit event.

## Fit / brand

OSS / self-host / BYOK; honesty brand (renders persisted macro-F1s, no fabricated
numbers). "Your model, your data, your version history — revert if it slips."

**NOTE:** `CLAUDE.md`'s billing / plan-gating / Stripe / Resend sections are STALE
(pre-OSS-pivot). All features are unlocked (MIT, self-hosted, BYOK). Do **not**
gate this feature behind a plan tier.
