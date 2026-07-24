# Aspect spec — offline-packaging

**Parent PRD:** `../prd.md` (M5.4) · **Aspect 4 of 5** · **Sequencing: after `in-process-provider`**

## Problem slice & user outcome

The in-process local model must run air-gapped and must not bloat the default image for operators who
never opt in. Mirror the M5.1 `model-packaging` pattern. Outcome: default builds pull zero model
weights and make zero network calls; an operator who wants air-gap builds with one `--build-arg` and
runs fully offline.

## In-scope

- `services/backend-api` Dockerfile: wire `HF_HOME=/app/models` (or the repo's existing cache path),
  install CPU-only torch/sentence-transformers wheels (CPU wheel index), and add a **build-time
  pre-bake** gated by `ARG BAKE_EMBEDDING_MODEL=false` — a conditional `RUN` that downloads the local
  model weights only when `--build-arg BAKE_EMBEDDING_MODEL=true`. Default = zero network, zero weight
  bytes in the image.
- Document in `docs/SELF_HOSTING.md`: how to enable the local provider, the pre-bake build arg, and
  the runtime offline env (`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`), plus the honest image-size
  delta when baked.
- `CHANGELOG.md` + `AI-TRACKING.md` M5.4 entry updated on completion (honest: "opt-in local embedding
  model, CPU/offline, measurably beats baseline on our eval set, n=…").

## Out-of-scope

- The provider itself (Aspect 2) and the eval (Aspect 3).
- GPU wheels/inference.
- Baking the model into the default image (default stays lean).

## Acceptance criteria (testable)

1. Default `docker build` (no `--build-arg`) succeeds, pulls **no** model weights, and the resulting
   image makes no embedding-related network call at import/boot.
2. `docker build --build-arg BAKE_EMBEDDING_MODEL=true` bakes the weights into `HF_HOME`; running that
   image with `HF_HUB_OFFLINE=1` embeds successfully with **no** outbound network (verify offline).
3. `docs/SELF_HOSTING.md` documents enable + pre-bake + offline env + size delta; a reader can follow
   it end-to-end.
4. No regression to the default image's ability to run without the local provider selected.

## Dependencies & sequencing

- **Depends on `in-process-provider`** (needs the provider + model id to bake).
- Can run in parallel with `retrieval-eval-card`.

## Open questions / risks

- Confirm the existing M5.1 Dockerfile HF cache/ARG conventions and reuse them verbatim (same
  `HF_HOME`, same ARG style) so there's one packaging pattern, not two.
- CPU wheel index pinning for torch must match the existing M5.1 setup to avoid a second, conflicting
  torch install.
- Honest size delta: baked image is materially larger — state the number, don't hide it.
