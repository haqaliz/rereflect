# PRD — Per-Org Category Classifier (M5.2 v2)

**Status:** Draft (pre-gate)
**Slug:** `per-org-category-classifier`
**Branch:** `feat/per-org-category-classifier`
**Author:** engineering (via `rereflect-begin-fast`), 2026-07-11
**Milestone:** M5.2 category-head follow-on (the "immediate v2" named in
`docs/planning/per-org-corrections-classifier/prd.md:145`)

---

## Problem Statement

Rereflect already collects **category corrections** (`AICorrection.correction_type='category'`) every
time an operator overrides the AI-assigned pain-point or feature-request category on a feedback item —
via the dashboard and the public API (`routes/public_api.py:355-362`). Today that signal is **stored and
ignored**: the per-org self-improving classifier shipped in M5.2 trains on **sentiment corrections only**
(`corrections_classifier/labels.py:8`, `dataset.py:71`). M4.2's "fine-tuned classification" for
categories was deferred and never built (`AI-TRACKING.md:250`).

So an operator can correct the same miscategorization a hundred times and the categorizer never learns.
The keyword + LLM categorizers are static; corrections don't feed back. This is the open half of the
corrections flywheel that M5.2 was built to close.

**For whom:** self-hosting operators (OSS / BYOK) whose teams actively triage feedback and correct
categories — the same personas already using the sentiment classifier and the AI Accuracy tab.

**Evidence it's real:** the data path exists and is exercised (dashboard correction UI + public API
`PATCH .../feedback/{id}` with `field=pain_point|feature_request`); the M5.2 PRD explicitly scoped the
category head as the immediate v2 and out-of-scope for v1 (`prd.md:145,245`).

## Goals & Success Metrics

**Goal:** an org's own category corrections train a small, CPU-only, per-org category model that — in
shadow/auto — improves feedback categorization, using the same A/B-gated, reversible spine as sentiment.

**Success metrics (first slice — see Out of Scope for the data-gated exit):**
- **Spine parity:** the category head trains → shadow-A/B-evaluates → promotes-only-if-better (≥ `MARGIN`
  macro-F1) → is one-click reversible, proven end-to-end under test with seeded/synthetic category
  corrections (mirrors how M5.2 sentiment shipped). **Pinned fixture (resolves critique #2):** (a) an org
  with ≥2 category classes, ≥`MIN_LABELS` corrections, and a deliberately-beatable keyword incumbent →
  asserts a `promoted` eval-run with `macro_f1_delta ≥ MARGIN`; (b) a below-gate org → `skipped`; (c) a
  single-class org → `retained`, no crash.
- **Byte-stability:** with `category_classifier_mode ∈ {off, shadow}`, stored category output
  (`pain_point_category` / `feature_request_category`) is **byte-identical** to today
  (characterization-locked).
- **Independent control:** enabling the category head never changes sentiment behavior, and vice versa.
- **Honest surface:** Settings → AI shows a category accuracy card stating the incumbent-vs-challenger
  macro-F1, the delta, and `n`; the mode toggle is off by default.

## User Personas & Scenarios

- **CS/Support lead (operator):** corrects pain-point categories weekly; wants the categorizer to stop
  repeating the same mistakes. Turns `category_classifier_mode` to `shadow`, watches the accuracy card,
  flips to `auto` when the challenger beats the keyword incumbent, rolls back if it regresses.
- **Self-hoster / admin:** wants the whole thing local and CPU-only, no new cloud dependency, and to see
  honestly whether their org has enough category corrections to activate (readiness readout from M5.0).

## Requirements

### Must-have
1. **Task-generic spine.** Parameterize the analysis-engine `corrections_classifier` package so it trains
   and evaluates a `classifier_type='category'` model without breaking the sentiment path (byte-stable):
   `dataset.py` (label filter + `correction_type`), `trainer.py` (artifact `classifier_type`),
   `evaluate.py` (`labels = SENTIMENT_LABELS → param`), plus a dynamic label vocabulary.
2. **One unified category head with dynamic labels.** Labels = the set that actually appears in the org's
   category corrections (`corrected_value`), derived from the dataset — **not** a fixed built-in tuple and
   **not** a `CustomCategory` reconciliation. This absorbs custom categories the operator already corrects
   toward, for free.
3. **Category dataset builder.** `build_category_dataset(org_id, db)` querying
   `correction_type='category'`, `signal='correction'`, `corrected_value IS NOT NULL`, joined to feedback
   text same-org (mirrors `dataset.py:64-73`).
4. **Category incumbent.** The deterministic **keyword categorizer** (`analyzer/categorizer.py`) is the
   A/B incumbent (cheap, no LLM, no `CustomCategory` merge needed on the analysis-engine path). Injected
   into `evaluate()` as `incumbent_predict`.
5. **Worker training loop.** Extend `retrain_all_orgs` to run per `classifier_type ∈ {"sentiment",
   "category"}` (not a parallel task); make `_CLASSIFIER_TYPE` a parameter; suffix the per-org Redis lock
   key with the type so the two heads don't serialize each other. Reuse the atomic-promote flush-order,
   eval-run insert, decision path, and 90-day purge unchanged.
6. **Category-aware predict-seam.** `apply_classifier_override` gets a category branch: on `auto`+override,
   write `pain_point_category` **or** `feature_request_category` chosen by which built-in vocab the
   predicted label belongs to; **bypass** `score_from_proba` (no signed axis — store confidence = max
   proba, or leave score untouched). Add category call-sites: backend shadow-only
   (`routes/feedback.py:~147`, after the categorizer block) and worker authoritative-auto
   (`tasks/analysis.py:427-429, 604-606`).
   **Unambiguous-routing rule (no silent mis-write):** in `auto`, override **only** when the predicted
   label is in exactly **one** built-in vocab. A label in **neither** (e.g. a custom category) or in
   **both** is shadow-logged only — never written to a guessed field. (Resolves critique #1.)
7. **Per-type mode.** Add `category_classifier_mode` (off|shadow|auto) to `OrgAIConfig` (Alembic +
   both service ORM mirrors). `resolve_classifier` reads the per-type mode. AI settings GET/PATCH validate
   and persist it (mirror the sentiment `classifier_mode` validation + sklearn guard,
   `routes/ai_settings.py:519-541`).
8. **Frontend surface.** Thread `classifier_type` through `lib/api/classifier-accuracy.ts`; render a
   second `ClassifierAccuracyCard classifierType="category"` on the AI Accuracy tab; add a category mode
   `<Select>` in `AISettingsGeneral.tsx`; type-appropriate copy.

### Should-have
- Readiness readout: the M5.0 `ai-readiness` card notes category-correction volume vs the activation
  threshold (reuse the existing pattern; category may already be surfaced via `by_type`).
- Eval-run `notes` distinguish category-specific skip reasons (e.g. "held-out missing class" is expected
  more often with an open label set).

### Nice-to-have (explicitly deferred — see Out of Scope)
- Separate per-kind heads; `CustomCategory` vocab reconciliation; urgency head; multi-label per item.

## Technical Considerations

- **Services changed:** analysis-engine (spine), worker-service (trainer + seam + mirrors), backend-api
  (migration + config + settings + seam call-site), frontend-web (accuracy card + mode toggle).
- **Schema:** **one** new column `org_ai_config.category_classifier_mode`. The `org_classifier_models` /
  `org_classifier_eval_runs` tables and `AICorrection` are **already type-generic** (`classifier_type`
  discriminator, partial-unique active row per `(org, classifier_type)`, `correction_type='category'`
  already flows) — no new tables, no correction-schema change.
- **Multi-tenancy:** every query scoped by `organization_id`; artifacts per-org (or `org_id=NULL` global
  base as sentiment already supports); text join is same-org to prevent cross-org leakage
  (`dataset.py:66-68`).
- **CPU-only / offline:** TF-IDF + logistic regression via already-installed scikit-learn; no GPU, no
  cloud. Byte-stable default paths.
- **Reversibility:** every promotion writes an eval-run and is one-click rollback per `(org, type)`
  (`routes/classifier_accuracy.py` already type-parameterized).
- **Leakage-free eval:** reuse `evaluate()` — `train_fn` is called by evaluate on the train split only;
  the promoted artifact is retrained on all rows in `_promote` (`classifier_training.py:98-147`).

## Risks & Open Questions

- **Thin data (primary risk).** Category corrections are sparser than sentiment; many orgs won't clear
  `MIN_LABELS=20`, and the open label set makes the "held-out missing class" guard fire more often →
  head stays `retained`/never promotes. *Mitigation:* off-by-default, honest readiness readout, prove the
  spine on synthetic data (this slice's exit), keep the keyword incumbent as the floor.
- **Label routing ambiguity.** A predicted label that is a **custom** category (not in either built-in
  vocab) has no obvious pain-point-vs-feature target field. *Resolution:* route by built-in-vocab
  membership; for labels in neither built-in set, default to `pain_point_category` (documented) and flag
  as an open question for the per-kind v3.
- **One prediction per item.** The unified head can't independently set both category fields on a
  dual-nature item — accepted limit of Option A; per-kind heads are the deferred follow-on.
- **Incumbent/label-space mismatch (rigged-A/B hazard — critique #3).** The dynamic label set is drawn
  from corrections (which may include custom categories), but the keyword incumbent can only emit
  **built-in** labels (`core.py` never calls `add_custom_categories`). On an org whose corrections include
  custom categories, the incumbent structurally cannot predict those classes → its macro-F1 is artificially
  depressed → the challenger "wins" too easily and `auto` could promote a weak model. **Resolution (must-
  have):** score the A/B **only over the label subset the incumbent can produce** (intersection of the
  eval labels with the built-in vocab) — i.e. don't credit the challenger for classes the incumbent was
  never able to guess. Document this honestly on the accuracy card ("evaluated on labels the baseline can
  produce"). Owned by `category-core` (eval) + `worker-trainer` (incumbent).
- **Score semantics.** Category has no signed score; decide store-max-proba vs leave-null (leaning: leave
  the existing category field's companion score untouched; category has none today).

## Out of Scope

- Category / pain-point / feature-request **separate per-kind** classifier heads (the v3 follow-on;
  requires recording the corrected field on `AICorrection`).
- **Urgency** head.
- `CustomCategory` vocab reconciliation as an explicit label-space source (dynamic-from-data covers it
  implicitly).
- Multi-label prediction (both fields on one item).
- "Promoted on a real org's held-out category corrections" — the **data-gated later exit**, not this PR.
- Any change to how corrections are *captured* (dashboard/public-API correction UX is unchanged).

## Roadmap bookkeeping (on completion)
Flip the M5.2 line in `AI-TRACKING.md` to note the category head shipped (spine + unified category head,
dynamic labels; per-kind + real-org promotion remain deferred), and add a "Current AI Capabilities" row.
