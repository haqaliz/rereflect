# Card — feat/per-org-corrections-classifier (freeform)

> **Source:** freeform task (no GitHub issue). Brief derived from the `rereflect-next`
> recommendation (2026-07-10) and `AI-TRACKING.md` **M5.2**. The issue number lives in
> the branch/PR; this card is the single source for later phases.

## Task

Build **M5.2 — Corrections flywheel: per-org self-improving classifiers** (Track A, the
flagship moat of the active M5 "Local Model Layer" block). Close the loop that has been
open since M3.3: `AICorrection`s are collected but **never trained on** (verified by grep —
`AICorrection` appears only in model/service/readiness/public-API-write code, no training
consumer; M4.2's "fine-tuned classification" was deferred, `AI-TRACKING.md:249`).

## What M5.2 says (AI-TRACKING.md:349-357)

- Train a **small per-org model** (SetFit / logistic-regression-on-embeddings via the
  already-installed `sentence-transformers`) on the org's feedback + `AICorrection`s — on
  the **worker**, **CPU-only**, **scheduled**.
- Per-org **shadow A/B** on held-out corrections; **auto-promote the challenger only when it
  beats the incumbent** by a margin; operator sees the delta and can **roll back**.
- **Activates per org** once corrections ≥ the threshold surfaced by M5.0
  (`CORRECTION_VOLUME_TARGET`).
- Honesty framing: "your model, trained on your data, promoted only when measurably better."
- **Exit (real):** ≥1 design-partner org has a promoted per-org model beating the default on
  their own held-out data.

## Why this is the pick (moat + shipped-state grounding)

- Both prerequisites shipped **today** (2026-07-10) on local master (unpushed):
  - **M5.0** — readiness gate that decides per-org activation:
    `GET /api/v1/analytics/ai-readiness` (`AI-TRACKING.md:313-323`).
  - **M5.1** — pluggable analyzer provider-layer **spine** M5.2 mirrors:
    `analysis-engine/src/analyzer/sentiment_providers/` (ABC + factory + per-org
    `resolve_*` in backend & worker mirrors) (`AI-TRACKING.md:325-347`).
- It **is** the OSS/self-hosted/BYOK moat verbatim (`AI-TRACKING.md:298-311`): per-org,
  local, CPU-only, no cross-tenant data, self-improving, gets better as base embedding
  models improve. Heavy stack (`sentence-transformers`, `scikit-learn`, `bertopic`) already
  installed; per-org fitting already exists shallowly in `churn_calibrator.py` (isotonic per
  org at `MIN_LABELS=20`) — a proven pattern to mirror.

## Cross-cutting M5 principles (must hold — AI-TRACKING.md:309-311)

- **CPU-only**, no GPU ever required.
- Default analyzer paths stay **byte-stable** (challenger runs in shadow; promotion is opt-in
  per org and reversible).
- No central / cross-tenant data.
- Models small, described **honestly**.
- Every model swap is **A/B-gated and reversible**.

## Known caveat (carry into the dig / PRD — do not be surprised)

M5.2 is **soft-gated** on correction volume (`CORRECTION_VOLUME_TARGET`, marked "explicitly
unvalidated v1" in M5.0, `AI-TRACKING.md:320`). Real *auto-promotion in production* needs a
design-partner org with enough corrections. **But** unlike M5.3's hard ≥500 churn-label gate,
this threshold is tunable and the **buildable/testable first slice** — CPU training pipeline +
shadow-A/B-on-held-out-corrections + promote-only-if-better + rollback mechanics — can be built
and proven end-to-end with **seeded/synthetic corrections**, independent of any live org's
volume. Only the "promoted on a real org's held-out data" exit is data-dependent. Scope the
first slice accordingly; treat "promoted on a real org" as the later exit, not the first PR.

## Related roadmap neighbours (context, not in scope)

- **M5.3** — per-org churn ML model — hard-gated at ≥500 churn labels/org (deferred).
- **M5.4** — local embedding quality — parked / nice-to-have.
- **M3.3** — Human-in-the-Loop corrections (the data source; `AICorrection`, correction
  dashboard, AI Accuracy tab).
- **M5.0/M5.1** — the just-shipped readiness gate + sentiment provider spine (the platform
  this builds on).
