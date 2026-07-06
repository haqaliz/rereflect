# Understanding — Public API write expansion v2

**Phase 2 dig.** Slug `public-api-write-v2`. Freeform follow-on of slice 1 (`public-api-write-crud`, merged 2026-07-06). Synthesized from direct reads + 2 read-only mapping agents (public-write layer; feedback model + internal delete/update precedent).

## What this is really asking

Slice 1 gave the public API a `write` scope + `PATCH /api/public/v1/feedback/{id}` that can (a) move `workflow_status` and (b) record record-only category/sentiment corrections. This slice adds the three deferred **low-risk** mutations to that same surface:

1. `tags` write on `PATCH /feedback/{id}`
2. `is_urgent` write on `PATCH /feedback/{id}`
3. `DELETE /api/public/v1/feedback/{id}`

All under the existing flat `write` scope, org-scoped, **no new DB migration** (columns already exist).

## Affected areas — single service: `backend-api`

No frontend / worker / analysis-engine change needed (columns exist; API-key UI already exposes the `write` scope from slice 1).

| Concern | Location |
|---|---|
| Public PATCH route + request/response model | `src/api/routes/public_api.py:294-437` (`PublicFeedbackUpdate`, `public_update_feedback`, `PublicFeedbackItem`:46-63) |
| Public OpenAPI/docs scope strings | `public_api.py:8-12` (scope table), `:753-758` (`info.description`), `:334-339` (PATCH `description=`) |
| API-key auth + org resolution | `src/api/public/auth.py:49` (`ApiKeyAuth.organization_id`), `verify_api_key`, `require_scope` |
| Valid scopes registry | `src/api/routes/api_keys.py:31` `_VALID_SCOPES = {"read","ingest","write"}` |
| Feedback model | `src/models/feedback.py:10` `id` int PK · `:22` `tags = Column(JSON, nullable=True)` · `:23` `is_urgent = Column(Boolean, default=False)` (Python-side default only, no server_default) |
| Internal DELETE precedent | `src/api/routes/feedback.py:497-550` (`delete_feedback`) |
| Cache invalidation | `src/services/cache_service.py:72` `cache_invalidate(pattern)` — always the pair `dashboard:{org}:*` + `analytics:{org}:*` |
| Real-time event | `src/services/event_emitter.py` `emit_event(org_id, event_type, data)` |
| Tests to extend | `tests/test_public_api_write.py` (slice-1 PATCH classes), `tests/test_feedback.py:261-305` (internal delete) |

## How the extension maps onto slice-1 patterns

**Tags / is_urgent (PATCH):** add optional fields to `PublicFeedbackUpdate`, apply inline, `db.commit()`, then the same best-effort side-effect trio the internal mutations use (`cache_invalidate` ×2 + `emit_event`). No `apply_status_change`-style helper — these two carry no workflow/timeline semantics. Add `tags` to the `PublicFeedbackItem` response so the write echoes back.

**DELETE:** the internal `delete_feedback` (`feedback.py:497`) already encapsulates correct behavior: org-scoped load → 404 → capture `customer_email` → `db.delete`+commit → **archive the customer's health record if this was their last feedback** → `cache_invalidate` ×2 → `emit_event("feedback:deleted")`. It does **not** dispatch a webhook and does **not** null `SlackAlertLog` refs (that cascade lives only in bulk-delete). Clean move (mirroring slice-1's helper extraction, commit `7345f02`): **extract `delete_feedback_item(db, fb, org_id)`**, refactor the internal route onto it under characterization tests, then call it from the public DELETE behind `require_scope("write")`, returning `204`.

## Key design decisions / ambiguities (for the PRD interview)

1. **Omitted vs "clear" semantics (the one real design call).** `PublicFeedbackUpdate` uses `Optional[...] = None` and treats `None` as "no change", so it *cannot* distinguish "clear all tags" (`[]`) from "leave unchanged" (omitted). To support clearing, switch to `model_fields_set` / `exclude_unset` checks. **Recommendation:** adopt `model_fields_set` so `tags: []` clears and omitted `tags` is untouched; `is_urgent` (bool) is unambiguous. Existing `workflow_status`/`correction` behavior must stay byte-identical.
2. **⚠️ SQLAlchemy `JSON` change-tracking trap.** `tags` is a plain `JSON` column — mutating the list in place is not dirty-tracked. Must **assign a new list object** (or call `flag_modified(fb, "tags")`) before commit, or the write silently no-ops. This belongs in the plan as an explicit step + a regression test.
3. **Tags validation (new semantics — no internal precedent).** Analyzer sets tags today (`worker/analysis.py:460`, max 5, list of strings). Define fresh: list-of-strings only, strip/trim, dedupe?, a max count and max element length. Settle the cap in the PRD (mirror analyzer's 5, or looser for manual?). Reject non-string elements → 422.
4. **`is_urgent` has no targeted-edit precedent** — internal PATCH resets it to `False` then re-analyzes; otherwise only rule-set (`has_urgent_keyword and is_very_negative`). A manual override is genuinely new; confirm it should persist without being clobbered by re-analysis (it won't be unless the item is re-analyzed).
5. **"Nothing to update" guard** (`public_api.py:347`) must widen to include `tags` / `is_urgent`.
6. **DELETE response** = `204 No Content`, org-scoped `404` on miss (no cross-tenant leak), idempotency note.
7. **Atomicity** (carried from slice 1): each concern commits separately; keep best-effort side effects; document non-atomicity.

## Contradictions / flags

- None between brief and code. "No internal precedent for tags/is_urgent writes" is **confirmed** — only analyzer assignment exists.
- Stale `CLAUDE.md`/`AI-TRACKING.md` billing/plan-gate sections do not apply (OSS, all unlocked). No plan gate on `write`.

## Out of scope (defer again — matches slice-1 PRD `:59-62`)

Mutating the stored category/sentiment analyzer column; customer/taxonomy CRUD; bulk writes; a separate `delete` scope (reuse `write`).
