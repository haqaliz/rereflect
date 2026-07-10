# Aspect Spec — predict-seam-resolver

**Parent PRD:** `../prd.md` (M5.2 per-org-corrections-classifier)
**Sequence:** after `data-layer` + `training-and-eval-core`; parallel with worker-trainer.

## Problem slice / outcome

Wire the trained per-org model into the live analysis path with `off`/`shadow`/`auto` semantics, a
three-tier load fallback, and shadow logging — mirroring exactly how M5.1's `resolve_sentiment_provider`
+ provider injection works at the two sentiment call-sites. Default `off` keeps analyzer output
byte-identical.

## In-scope

1. **`resolve_classifier(org_id, classifier_type, db) -> ResolvedClassifier | None`** — mirrored in
   **both** `backend-api/src/services/` and `worker-service/src/services/`; reads
   `OrgAIConfig.classifier_mode` via `getattr(config, 'classifier_mode', 'off')`; returns `None` for
   `off`/missing/invalid; **never raises**.
2. **Model loader** with **three-tier fallback**: org active → global active (org_id IS NULL) →
   **incumbent** (None → caller keeps analyzer value); corrupt `model_json` → warn + incumbent (copy
   `probability_updater._deserialize_model` defensiveness). Predict via aspect B's `predict()` +
   `score_from_proba()`.
3. **Per-org cache**: an org-scoped cache key (not provider-name only) with invalidation when a newer
   `fit_at`/model id is active.
4. **Call-site injection** at both sentiment sites — worker `tasks/analysis.py`
   (`_apply_keyword_analysis` / `_analyze_feedback_item` after incumbent set, before commit) and backend
   `routes/feedback.py` inline path:
   - `off` → no-op (byte-stable; assert unchanged output).
   - `shadow` → compute challenger label+score, **log** (an `org_classifier_eval_runs` shadow row or a
     lightweight prediction log), do **not** touch `feedback.sentiment_label/score`.
   - `auto` → if a promoted active model exists, set `feedback.sentiment_label` = challenger label and
     `feedback.sentiment_score` = `score_from_proba(...)` before commit; else no-op.
5. Shared predict/log helper invoked from both call-sites (avoid worker/backend drift), matching how
   `sentiment_resolver` is duplicated.

## Out-of-scope

- Training/scheduling (B/C). Settings API + UI (E). Category task (v2).

## Acceptance criteria (testable)

- `off` (default): `_apply_keyword_analysis` output byte-identical to pre-change (characterization test).
- `shadow`: stored `sentiment_label/score` unchanged; a shadow prediction is logged.
- `auto` with a promoted model: stored `sentiment_label` overridden, `sentiment_score` = mapped value in
  [-1,1]; downstream health/trend read a coherent score (characterization on health_score_service input).
- `auto` with no promoted model / corrupt artifact / no config row → incumbent value retained (three-tier
  fallback), never raises.
- `resolve_classifier` never raises on missing column / missing row / bad value (un-migrated-DB test).
- Cache returns the newer model after a promotion (invalidation test).

## Dependencies & sequencing

- **Blocked by:** data-layer (schema), training-and-eval-core (`predict`, `score_from_proba`).
  **Blocks:** none. Coordinates with worker-trainer (reads its rows) but independently testable with a
  hand-inserted active model row.

## Open questions / risks

- Shadow log destination: reuse `org_classifier_eval_runs` vs a dedicated prediction log — recommend a
  lightweight prediction log or fold into eval_runs (confirm in tech-plan; keep it cheap, per-item).
- Backend inline create-time path vs worker: to avoid double-write, decide whether promotion override
  happens only in the worker (authoritative) and the inline path stays incumbent, or both. Recommend the
  worker owns `auto` override; inline stays incumbent + shadow-logs only. Confirm in tech-plan.
