# Card — local-embedding-quality (freeform)

**Type:** feat · **Slug:** `local-embedding-quality` · **Branch:** `feat/local-embedding-quality`
**Source:** freeform task from `rereflect-next` handoff on 2026-07-24. No GitHub issue.
**Roadmap:** `AI-TRACKING.md` — **M5.4 "Local embedding quality"** (`[ ]` "parked / nice-to-have", no blocker stated)

---

## Brief (from rereflect-next handoff)

Ship **M5.4**: a better **local** embedding model as an opt-in default for the offline AI
Copilot's retrieval + template-matching, plugged into the existing embedding-provider layer
(`services/backend-api/src/services/embeddings/`, per-org `model_embeddings` in `org_ai_config`).

Constraints / gates:
- Keep the current default **byte-stable** for installs that don't opt in.
- Keep it **CPU-only / air-gappable** (document a pre-baked model-cache path like M5.1 did).
- The gate is an **honest offline eval**: build a small labeled retrieval/template-match set and
  show the new model **measurably beats** the current local default before promoting it — no
  absolute-accuracy marketing claims (matches the honest OSS brand).
- Avoid the `status-sync-realtime-mapping` and `feat/classifier-model-versioning-rollback`
  areas — both are in flight.

## Why this was picked (moat rationale)

- The one **unblocked** item left in the Local Model Layer. M5.0/M5.1/M5.2 are `COMPLETE`;
  M5.3 (per-org churn ML) is **data-gated** (~500 labels, gate under review); M5.4 has no blocker.
- Deepens the **fully-offline AI Copilot** moat and gets better as base models improve.
- The embedding-provider abstraction already ships (`local-embeddings-offline-copilot` merged),
  so this is a **depth-first follow-on**, not net-new plumbing.

## Known caveat (carried into the dig)

The hard part is **honest proof, not the swap.** Embedding/retrieval quality is harder to
benchmark than sentiment macro-F1 — needs a small labeled retrieval/template-match eval set to
show a measurable offline improvement, or it's just a model change dressed as a win. Must stay
CPU-friendly/air-gappable (a bigger model raises worker image size + inference latency) and keep
the current default byte-stable.

## Grounding pointers (from rereflect-next dig, pre-worktree — verify in Phase 2)

- Embedding layer: `services/backend-api/src/services/embeddings/{base.py,factory.py}`,
  `providers/` (e.g. `google.py`), `__init__.py`.
- Per-org override: `org_ai_config.model_embeddings` (`services/backend-api/src/models/org_ai_config.py`).
- Default resolution: `_default_embedding_model(provider)` in
  `services/backend-api/src/api/routes/ai_settings.py` (+ `EmbeddingStatusResponse`).
- Copilot consumers: `services/backend-api/src/api/routes/copilot_ws.py`,
  `services/backend-api/src/models/query_template_mapping.py`.
- Prior-art pattern to mirror: M5.1 sentiment-provider layer
  (`services/analysis-engine/src/analyzer/sentiment_providers/`) + its offline pre-bake path.

**NOTE:** `CLAUDE.md`'s billing / plan-gating / Stripe / Resend sections are STALE (pre-OSS-pivot).
All features are unlocked (MIT, self-hosted, BYOK). Do not gate this feature behind a plan tier.
