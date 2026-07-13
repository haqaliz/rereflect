# Card — feat/urgency-classifier-head (freeform, no GitHub issue)

**Type:** feat
**Slug:** urgency-classifier-head
**Branch:** feat/urgency-classifier-head
**Source:** `rereflect-next` handoff (2026-07-13). No GitHub issue — freeform.

## Brief (from rereflect-next handoff)

Extend the **M5.2 per-org corrections flywheel** with an **urgency classifier head** — the
next head after the shipped **sentiment + category** heads (AI-TRACKING M5.2, v3 deferral at
line 366–367: *"separate per-kind heads (needs recording the corrected field on `AICorrection`),
an urgency head, and multi-label per item."*).

The classifier spine is already generic and proven — reuse it rather than build greenfield:
- `services/analysis-engine/src/analyzer/corrections_classifier/dataset.py` — `fetch_correction_rows(org_id, db, *, correction_type=...)` is generic; sentiment/category are two callers.
- `corrections_classifier/trainer.py` — `train_classifier(..., classifier_type=...)` (default `"sentiment"`, byte-stable), writes `classifier_type` into the serialized model.
- 3-tier predict loader + per-org Redis advisory lock (worker retrain orchestration).
- Type-aware `ClassifierAccuracyCard` (frontend, `classifierType` prop) + independent mode toggle on the AI Settings tab.

The **category head shipped 2026-07-11** by threading exactly this `classifier_type` pattern
end-to-end. Urgency is the same shape.

## Slice 1 is the capture seam (the named prerequisite / caveat)

Urgency corrections are **not captured as a training signal today**. `AICorrection.correction_type`
enumerates `copilot_response | sentiment | category | churn_risk | response_suggestion` — **no
`urgency`**. Toggling `is_urgent` writes nothing to `ai_corrections`:
- `services/backend-api/src/api/routes/feedback.py` sets `is_urgent` heuristically
  (`has_urgent_keyword and is_very_negative`, ~line 112) and clears it (~line 665) without recording a correction.
- Public API `PATCH /api/public/v1/feedback/{id}` accepts `is_urgent` but records no urgency signal.

So **slice 1 = the capture seam**: when a user overrides `is_urgent` (dashboard flag toggle +
public-API PATCH), record an `AICorrection(correction_type="urgency", signal=...)`, mirroring how
sentiment/category corrections are recorded (`src/services/ai_correction_service.py`,
`src/api/routes/ai_corrections.py`). Small and well-precedented — **not** a hard data gate — but the
head has zero training signal until it lands, so it must come first.

## Then: add `"urgency"` as a `classifier_type` end-to-end

- dataset builder → train → predict override at the ingest seam, with off/shadow/auto mode
  (mirror `category_classifier_mode`).
- Keep it local/sklearn and BYOK-agnostic.
- Honest UI copy ("your model, trained on your corrections").

## Guardrails / out of scope

- **Avoid the `churn_risk` head** — that one is gated on the M5.3 ~500-label requirement (different head).
- Fits OSS/self-hosted/BYOK; single-tenant-clean; gets better as corrections accumulate.
- Multi-label per item and per-kind head splitting remain deferred (M5.2 v3).

## Relevant files (dig starting points)

- `services/analysis-engine/src/analyzer/corrections_classifier/{dataset,trainer,__init__}.py`
- `services/analysis-engine/src/analyzer/categorizer.py` (urgency category entries ~line 483)
- `services/analysis-engine/src/analyzer/core.py` (urgency sort ~line 310)
- `services/backend-api/src/models/ai_correction.py`
- `services/backend-api/src/services/ai_correction_service.py`
- `services/backend-api/src/api/routes/ai_corrections.py`
- `services/backend-api/src/api/routes/feedback.py` (is_urgent set/clear)
- `services/backend-api/src/api/routes/public_api.py` (PATCH is_urgent)
- `services/worker-service/src/tasks/` (per-org classifier retrain orchestration)
- `services/frontend-web/` — AI Settings tab, `ClassifierAccuracyCard`, mode toggle
- Reference shipped precedent: `docs/planning/per-org-category-classifier/`, `docs/planning/per-org-corrections-classifier/`
