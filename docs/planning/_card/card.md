# Card — Public API write expansion v2 (freeform)

**Type:** feat · **Slug:** `public-api-write-v2` · **Branch:** `feat/public-api-write-v2`
**Source:** freeform (no GitHub issue) — handed off from `rereflect-next` on 2026-07-07.
**Builds on:** slice 1 = `public-api-write-crud`, merged 2026-07-06 (commit `20ac3ae`).

---

## Brief

Extend the public REST write surface that shipped in **slice 1** (`write` scope + `PATCH /api/public/v1/feedback/{id}` for `workflow_status` + record-only category/sentiment corrections).

This slice adds the **deferred low-risk edits** explicitly named in the slice-1 PRD (`PRD-LOCAL-LLM-CUSTOM-AI-PUBLIC-API.md` deferred list / `docs/planning/public-api-write-crud/prd.md:57-64`):

- **`tags` write** on the existing `PATCH /api/public/v1/feedback/{id}`
- **`is_urgent` write** on the same endpoint
- **`DELETE /api/public/v1/feedback/{id}`**

All under the existing flat `write` scope, org-scoped (cross-org → 404), reusing slice-1 helpers (timeline event, webhook emit, cache invalidation) and needing **no new DB migration** (columns already exist on the feedback model).

## Explicitly OUT of scope (defer again — name in the PRD)

- **Mutating the stored category/sentiment analyzer column** (`prd.md:59`). Slice 1 kept corrections *record-only* on purpose — writing the analyzer-derived column entangles the `AICorrection` signal store, health recompute, and cache-invalidation paths at once. Separate later slice.
- Customer write/CRUD, category-taxonomy CRUD, bulk write endpoints (`prd.md:60-62`).

## Known caveats (from rereflect-next dig)

1. **No internal-route precedent for `tags`/`is_urgent` writes** (`prd.md:58`) — analyzer-only today. Define write semantics fresh; mirror the ingest path's validation and the existing internal feedback-update route if one exists.
2. **`DELETE` needs the same cache-invalidation + timeline/webhook discipline** as slice-1 mutations; confirm whether a delete already exists on the internal route to reuse.
3. **Characterization-test** that existing status-change + correction behavior stays byte-identical (slice-1 refactored internal routes onto shared helpers `apply_status_change` / `create_ai_correction`).
4. **OSS/self-hosted/BYOK** — all unlocked, no plan gating. `CLAUDE.md`/`AI-TRACKING.md` billing sections are stale post-pivot.

## Reference implementations to mirror

- `services/backend-api/src/api/routes/public_api.py` — slice-1 `PATCH /feedback/{id}` + `require_scope("write")`.
- `services/backend-api/src/api/public/auth.py` — API-key auth + `require_scope` + org resolution.
- Slice-1 shared helpers `apply_status_change` / `create_ai_correction` (extracted in commit `7345f02`).
- The internal feedback-update + delete routes (JWT) — the closest write/delete precedent for request/response shape + cache invalidation.

## Why picked (moat fit)

Developer/self-host surface is a named moat pillar; `rereflect-next` rule 5 lists "public-API write/CRUD expansion" as a high-leverage follow-on. Freshest depth-first slice of work that landed 2026-07-06; unblocked, testable, zero business-model drag.
