# Understanding — Public API Write/CRUD Expansion

**Slug:** `public-api-write-crud` · **Branch:** `feat/public-api-write-crud` · **Date:** 2026-07-06
Synthesized from 3 read-only mapping agents (public-API layer, feedback-update/correction path, frontend scope UI).

---

## What the task is really asking

Add a **`write` scope + write endpoint(s)** to the *public* REST API (`/api/public/v1`), so a self-hosting operator can mutate existing feedback from their own systems via an API key — not just read/ingest. Slice 1 = single-entity feedback mutation. Customer/category-taxonomy CRUD and bulk writes are explicit v2.

## Affected areas (all in `services/backend-api` + `services/frontend-web`)

**Backend — public API layer (extend, low risk):**
- `src/api/routes/public_api.py` — router `APIRouter(prefix="/api/public/v1")` @ :39. Add a `@router.patch("/feedback/{id}", dependencies=[Depends(require_scope("write"))])`. The org-scoped fetch-then-404 idiom already exists verbatim @ :244–253; the ingest `POST /feedback` @ :260 is the closest write template. New request model mirrors `PublicFeedbackCreate` @ :73; reuse `PublicFeedbackItem` response model @ :45.
- `src/api/public/auth.py` — `verify_api_key` → `ApiKeyAuth(organization_id, scopes, key_row)`; `require_scope("write")` is **generic and already works** once `write` is grantable. Org comes from `auth.organization_id`.
- `src/api/routes/api_keys.py:31` — `_VALID_SCOPES = frozenset({"read", "ingest"})` → add `"write"`. This is the ONLY create-time gate (422 on unknown). No DB migration (scopes is a free-form `String(100)` comma list, `models/api_key.py:22`).
- Docs strings to update: `public_api.py:8–11` (module docstring scope table), `public_api.py:610–611` (OpenAPI `info.description` scope sentence). New route auto-appears in the scoped `/api/public/v1/openapi.json` + `/docs` (filtered by prefix, no wiring).

**Frontend — scope picker (small):**
- `app/(dashboard)/settings/api-keys/page.tsx` — scope checkbox list driven by inline `['read','ingest'] as const` @ :152; add `'write'`. The description ternary @ :167–171 is binary (read vs else) → convert to a 3-way lookup or `write` shows the ingest copy. `ScopeBadge` color map @ :53–65 needs a `write` entry or it falls back to gray.
- `lib/api/api-keys.ts:5` — `export type ApiKeyScope = 'read' | 'ingest';` → add `| 'write'`. The `create()` client @ :36–40 passes scopes through (no change).
- Docs: `docs/API.md:76–77` (scope list; :68 calls the API "read-only" — now inaccurate). `docs/SELF_HOSTING.md` ingest-key section is fine; note its HubSpot `crm.objects.contacts.write` mentions are unrelated.

## ⚠️ The finding that reshapes the feature (resolve in PRD)

There is **no single internal "feedback update service."** Mutation logic is inline in route handlers, and the three field groups behave very differently:

| Field group | Internal precedent to delegate to | Notes |
|---|---|---|
| **`workflow_status`** | `workflow.py:137 change_status` (`POST /api/v1/workflow/status`, bulk) | Clean path. Validates `VALID_STATUSES = [new, in_review, resolved, closed]`, records a timeline event via `workflow_service.create_workflow_event`, invalidates cache, dispatches the `feedback.status_changed` webhook + WS event. **Strongest, cleanest slice-1 win.** |
| **category / sentiment override** | `ai_corrections.py:102 submit_correction` (`POST /api/v1/ai-corrections`) | The dashboard override **only records an `AICorrection` training signal — it does NOT change the stored `*_category` / `sentiment_label` column.** Those columns are only ever written by the analyzer. So a public "override" that *also* mutates the stored value would be **net-new behavior** beyond what the dashboard does. There's no service wrapper — creation is inline; slice 1 should refactor it into a shared helper both routes call. |
| **`tags` / `is_urgent`** | **NONE** — no internal endpoint manually edits these | Only the analyzer/automations write them. Accepting a manual value = genuinely new mutation surface with no precedent. Lean toward **deferring to v2**. |

- The existing `PATCH /api/v1/feedback/{id}` (`feedback.py:592`) is a **re-analyze** (overwrites text, wipes+recomputes all AI fields) — **do NOT reuse it** for a field-level public PATCH; it destroys categorization.

## Open questions for the requirements interview (genuine product decisions)

1. **Scope granularity** — single `write` scope (recommend) vs per-resource scopes?
2. **Slice-1 field coverage** — status only (cleanest, real win) / status + assignment / + category&sentiment corrections (record-only signal, mirror dashboard) / + tags&is_urgent (net-new surface)?
3. **Category/sentiment semantics** — record-only correction (mirror dashboard) vs also mutate the stored column (net-new)?
4. **Idempotency shape** — PATCH with `exclude_unset`; repeated identical PATCH should converge (status set to same value = no-op or re-emit event?).

## Contradiction flagged vs the original card
The card assumed a public PATCH could "reuse the internal update + correction services" for status/category/tags/urgency uniformly. Reality: only **status** has a clean reusable path; **category/sentiment** reuse means recording a training signal (not mutating the field); **tags/urgency** have no internal precedent at all. The PRD must scope slice 1 around this, not paper over it.
