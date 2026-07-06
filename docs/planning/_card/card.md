# Card — Public API Write/CRUD Expansion (freeform)

**Type:** feat · **Slug:** `public-api-write-crud` · **Branch:** `feat/public-api-write-crud`
**Source:** Freeform task from the `rereflect-next` recommendation handoff (verified against the code — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-06

---

## Brief

Add a **write scope + write/CRUD endpoints to the public REST API** (slice 1).

Today the public API is **read + feedback-ingest only**. Verified against the code:
- `services/backend-api/src/models/api_key.py:22` — `scopes` column comment says `read,ingest`.
- `services/backend-api/src/api/routes/api_keys.py:31` — `_VALID_SCOPES = frozenset({"read", "ingest"})` — no `write` scope exists.
- `services/backend-api/src/api/routes/public_api.py` — every route is a GET behind `require_scope("read")` **except** the single ingest `POST /feedback` behind `require_scope("ingest")`.

There is **no way to mutate an existing entity** (feedback status, category, tags, urgency) via an API key. This slice closes that gap.

### Core capability (slice 1)
- **New `write` scope** — added to `_VALID_SCOPES`, the API-key model/UI, and the OpenAPI docs. `scopes` is a comma-string column, so **no DB migration** is needed for the scope value itself.
- **Public feedback mutation** — e.g. `PATCH /api/public/v1/feedback/{id}` to update status / category-override / tags / urgency flag, behind `require_scope("write")`, org-scoped and idempotent.
- **Reuse the internal update + M3.3 human-in-the-loop correction services** — category/sentiment changes are already modeled as training signals (`AI-TRACKING.md:210–216`). A public `PATCH` must feed the **same** correction store, **not** a parallel path that bypasses it.
- **Frontend:** surface the `write` scope in the API-key creation UI + docs (the AI Settings / API keys page), and the public OpenAPI docs at `/api/public/v1/docs`.

### Explicit non-goals / deferred to v2 (name in the plan)
- Customer write/CRUD (`PATCH /customers/{email}`, health-weight override, CS notes) — v2.
- Category taxonomy CRUD via public API — v2.
- Bulk write endpoints — v2 (slice 1 is single-entity).
- Webhook-management writes beyond what already exists — out of scope.

---

## Key caveats (from rereflect-next dig)

1. **Do not bypass the correction store.** Category/sentiment writes are human-in-the-loop training signals (M3.3, `AI-TRACKING.md:212–213`). The public `PATCH` must route through the existing correction/update services so the training signal is preserved.
2. **Scope granularity is a design decision** — single `write` scope (recommended for slice 1) vs per-resource scopes. Settle in the PRD.
3. **Every write must be org-scoped + idempotent.** The API key resolves the org (see the `require_scope` / public auth layer in `services/backend-api/src/api/public/auth.py`); the mutated row must be filtered by that org, and repeated identical PATCHes must converge.
4. **OSS/self-hosted/BYOK** — all features unlocked, no plan gating. The plan-gating / billing sections in `CLAUDE.md` and `AI-TRACKING.md` are stale post-pivot.

---

## Reference implementations to mirror
- `services/backend-api/src/api/routes/public_api.py` — the existing public read endpoints + `require_scope("read")` structure and the OpenAPI/docs generation to extend.
- `services/backend-api/src/api/public/auth.py` — the API-key auth + `require_scope` dependency + org resolution.
- `services/backend-api/src/api/routes/api_keys.py` (`_VALID_SCOPES`, scope validation) + `src/models/api_key.py` — where the `write` scope is registered.
- The internal feedback-update route + the M3.3 correction service (category/sentiment corrections) — the services the public PATCH must delegate to.
- `POST /feedback` ingest endpoint (`public_api.py` + `public/auth.py`) — the closest existing write precedent (scope-gated, org-scoped) for request/response shape.

---

## Why this was picked (moat fit)
- Deepens the **developer-surface** moat — a named moat lever — which is currently one-directional (read/ingest only).
- Perfect fit for OSS/self-hosted/BYOK: operators automate Rereflect (mark resolved, correct a category, tag in bulk) from their own systems.
- Depth-first, unblocked follow-on of a `COMPLETE` capability (the public REST API, `AI-TRACKING.md:287`); internal mutation paths already exist.
