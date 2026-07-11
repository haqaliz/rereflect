# Card — feat/per-org-category-classifier (freeform)

**Type:** feat
**Slug/id:** per-org-category-classifier
**Source:** Freeform — no GitHub issue. Brief is the `rereflect-next` recommendation (2026-07-11).
**Branch:** feat/per-org-category-classifier

> Supersedes the prior M5.2 (`per-org-corrections-classifier`) card that shipped 2026-07-11.
> This is the M5.2 **category-head v2** follow-on.

---

## Brief (the pick from rereflect-next)

Extend the just-shipped **M5.2 per-org self-improving classifier** from **sentiment** to a
**category head** — pain-point / feature-request / urgency classification, trained per-org on the
org's own feedback text + its `AICorrection` **category** corrections, using the same TF-IDF +
logistic-regression spine, the same shadow-A/B gate, the same off/shadow/auto seam, and the same
Settings accuracy + one-click rollback surface that sentiment already has.

This is the **explicitly-named "immediate v2"** of M5.2 and closes M4.2's long-deferred
"fine-tuned classification."

### Why (grounded)
- **Named next slice of the flagship moat.** `docs/planning/per-org-corrections-classifier/prd.md:145`
  lists the "Category classifier head (pain-point + feature-request) … the immediate **v2**," and
  `:245` puts it out-of-scope for v1. `AI-TRACKING.md:350` records M5.2 shipped with the note
  "category head is the v2 follow-on."
- **Unblocked; spine already built.** `services/analysis-engine/src/analyzer/corrections_classifier/`
  (dataset → trainer → evaluate → predict → metrics/labels), the worker retrain orchestration, the
  predict-seam (off/shadow/auto), and the Settings accuracy/rollback UI all shipped this week
  (commits `886db52`..`24b3621`). `labels.py` hard-codes `SENTIMENT_LABELS` — the only sentiment-locked
  piece. Category-correction data is already collected: `AICorrection.by_type` includes real
  `category` rows (`AI-TRACKING.md:315`).
- **Fits OSS / self-hosted / BYOK moat.** CPU-only, offline, per-org, small-and-honest, gets better
  the more it is corrected (`AI-TRACKING.md:299-312`). No cloud/cross-tenant dependency.

### Known caveat (carried into the dig / PRD — do not be surprised)
Category is harder than 3-class sentiment:
1. **Dynamic label set per org** — built-in taxonomies ∪ active `CustomCategory` rows — needs vocab
   reconciliation (`prd.md:145`).
2. **Pain-point vs feature-request disambiguation** (are these one multi-class head, or separate heads?).
3. **Thinner correction volume** per category than sentiment → more orgs stay below the `MIN_LABELS`
   activation gate.

**Mitigation / first slice:** ship a **fixed built-in category label set** first, reusing the spine
parameterized by task (rather than hard-coding `SENTIMENT_LABELS`), keeping default analyzer output
byte-stable and every promotion A/B-gated and reversible. **Defer** dynamic `CustomCategory` vocab
reconciliation and pain-vs-feature disambiguation to a second slice.

### Roadmap position
- M5.0 (readiness), M5.1 (sentiment provider layer), **M5.2 (sentiment corrections classifier) — SHIPPED 2026-07-11.**
- M5.3 (per-org churn ML) — **blocked**: needs ~500 churn labels/org (`AI-TRACKING.md:321,359`). Not this work.
- M5.4 (local embedding quality) — parked / nice-to-have.
- **This work = the M5.2 category-head v2.**

### Cross-cutting M5 principles (must hold — AI-TRACKING.md:309-311)
- **CPU-only**, no GPU ever required.
- Default analyzer paths stay **byte-stable** (challenger runs in shadow; promotion is opt-in per org, reversible).
- No central / cross-tenant data.
- Models small, described **honestly**.
- Every model swap is **A/B-gated and reversible**.

### Related roadmap neighbours (context, not in scope)
- **M3.3** — Human-in-the-Loop corrections (the data source; `AICorrection`, AI Accuracy tab).
- **M5.2 sentiment** — the spine this parameterizes.
- **Custom AI (M4.2)** — per-org `CustomCategory` taxonomies injected into the analyzer prompt/keyword
  categorizers; the dynamic-label-set piece this must eventually reconcile with.
