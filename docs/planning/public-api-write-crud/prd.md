# PRD — Public API Write Scope & Feedback Mutation (slice 1)

**Slug:** `public-api-write-crud` · **Branch:** `feat/public-api-write-crud` · **Date:** 2026-07-06
**Status:** Draft (pre-plan review gate)
**Source:** Freeform task from the `rereflect-next` handoff (no GitHub issue). Verified unbuilt against the code.

---

## Problem Statement

Rereflect's public REST API (`/api/public/v1`) is **read + ingest only**. An operator with an API key can pull feedback/customers/analytics (`read` scope) and submit new feedback (`ingest` scope), but there is **no way to mutate an existing feedback item** — mark it resolved, or correct a mislabeled category/sentiment — from their own systems.

For an open-source, self-hosted, BYOK product the developer surface *is* a core moat lever (`AI-TRACKING.md` strategic decisions), and today it is one-directional. Operators who triage feedback in an external tool (a ticketing system, a script, a cron) cannot write the outcome back to Rereflect via the API; they must use the dashboard UI. This blocks automation and closed-loop workflows.

**Evidence it's real (code, not assumption):**
- `api_keys.py:31` — `_VALID_SCOPES = frozenset({"read", "ingest"})`; there is no `write` scope.
- `public_api.py` — every route is a GET behind `require_scope("read")` **except** the single ingest `POST /feedback`.
- `docs/API.md:68` describes the public API as "read-only."

## Goals & Success Metrics

**Goal:** A self-hoster can, using only a public API key, (a) change a feedback item's workflow status and (b) submit a category/sentiment correction — through the *same* internal code paths the dashboard uses, with full multi-tenant isolation.

**Success criteria (testable):**
- A `write`-scoped key can `PATCH /api/public/v1/feedback/{id}` to set `workflow_status`, and the change produces the identical side effects as the dashboard status change (timeline event + `feedback.status_changed` webhook + cache invalidation).
- A `write`-scoped key can submit a category or sentiment correction via the API, producing an `AICorrection` row identical in shape to a dashboard correction (`signal='correction'`), and **without** mutating the stored analyzer value.
- A `read`- or `ingest`-only key receives `403` on any write endpoint; a key cannot touch another org's feedback (`404`, not `403`, on cross-tenant IDs).
- The new `write` scope is grantable in the API-keys UI and appears in the public OpenAPI docs.
- All behavior covered by TDD (RED→GREEN→REFACTOR); backend `pytest` + frontend `npm run test`/`lint` green.

## User Personas & Scenarios

- **Self-hosting operator / developer.** Runs Rereflect on their own infra, automates triage. Scenario: a nightly script closes feedback items that were resolved in their support tool → `PATCH .../feedback/{id}` with `{"workflow_status": "resolved"}`.
- **Data/ML tinkerer.** Bulk-reviews AI categorizations and wants to feed corrections back as training signal from a notebook → API category correction, same signal store as the dashboard.

## Requirements

### Must-have (slice 1)
1. **`write` scope.** Add `"write"` to `_VALID_SCOPES` (`api_keys.py:31`). Grantable at key creation (default remains `["read"]`). No DB migration (scopes is a free-form comma string, `api_key.py:22`).
2. **`PATCH /api/public/v1/feedback/{id}`** behind `require_scope("write")`:
   - **`workflow_status`** (optional): validated against `VALID_STATUSES = [new, in_review, resolved, closed]`. Delegates to the **shared status-change logic** extracted from `workflow.py:137 change_status` — must produce the timeline event (`workflow_service.create_workflow_event`), the `feedback.status_changed` webhook dispatch, cache invalidation, and WS event, exactly as the internal path does.
   - **category / sentiment correction** (optional): records an `AICorrection` via a **shared helper** extracted from `ai_corrections.py:102 submit_correction` (`correction_type ∈ {category, sentiment}`, `entity_type='feedback_item'`, `entity_id={id}`, `signal='correction'`, `original_value=<current stored value>`, `corrected_value=<new>`, org+key-derived). **Record-only** — the stored `*_category` / `sentiment_label` column is NOT mutated (mirrors the dashboard).
   - Org-scoped fetch-then-404 (copy the idiom at `public_api.py:244–253`). Cross-tenant id → `404`.
   - PATCH semantics: `model_dump(exclude_unset=True)`; omitted fields untouched; empty body → `400` (nothing to update).
   - Returns the updated `PublicFeedbackItem` (existing response model @ `public_api.py:45`).
3. **Refactor internal routes to shared helpers** so both the internal (JWT) route and the public route call one implementation — no duplicated/divergent write logic. Internal behavior must be byte-for-byte unchanged (characterization test).
4. **Frontend scope picker.** Add `'write'` to `ApiKeyScope` (`api-keys.ts:5`), the scope checkbox array (`api-keys/page.tsx:152`), a 3-way description (fix the binary ternary @ :167–171), and a `write` color in `ScopeBadge` (@ :53–65).
5. **Docs.** Update the public-API scope list + OpenAPI `info.description` (`public_api.py:610–611`, module docstring `:8–11`) and `docs/API.md:68,76–77`.

### Should-have
- Idempotency: setting `workflow_status` to its current value is a no-op that does **not** emit a duplicate webhook/timeline event (or emits deliberately — decided in plan; default: no-op skip).
- A `PublicFeedbackUpdate` request model with clear field validation + OpenAPI examples.

### Nice-to-have
- `assigned_to` on the same PATCH (delegating to `workflow.py assign`). Only if it doesn't expand the slice materially.

### Out of scope (v2 — name explicitly)
- **`tags` / `is_urgent` manual edits** — no internal precedent; analyzer-only today. Deferred.
- **Mutating the stored category/sentiment column** — record-only in slice 1.
- **Customer write/CRUD** (`PATCH /customers/{email}`, health-weight override, CS notes).
- **Category-taxonomy CRUD** via public API.
- **Bulk write endpoints** (slice 1 is single-entity).
- **Webhook-management writes** beyond what exists.
- **DELETE** endpoints.

## Technical Considerations

- **Services changed:** `services/backend-api` (routes + shared helpers + scope allowlist), `services/frontend-web` (scope picker + type + docs). No worker/analysis-engine change. No Alembic migration.
- **Architecture fit:** Extends the existing public router (`APIRouter(prefix="/api/public/v1")`, `public_api.py:39`). `require_scope("write")` is already generic — works once `write` is in the allowlist. Org from `auth.organization_id` (`public/auth.py`).
- **Key refactor risk:** Extracting `change_status` and `submit_correction` internals into shared service functions. Both currently inline in route handlers. Mitigate with characterization tests on the internal routes before refactoring (RED captures current behavior).
- **Multi-tenancy:** every write query filtered by `organization_id`; cross-tenant → 404. Non-negotiable, TDD-covered.
- **OpenAPI:** new PATCH auto-appears in the scoped `/api/public/v1/openapi.json` (prefix-filtered, no wiring); only the scope description sentence is a manual edit.
- **OSS/self-hosted/BYOK:** all unlocked, no plan gating. (The billing/plan-gate sections in `CLAUDE.md` + `AI-TRACKING.md` are stale post-pivot — do not add a `require_feature` gate.)

## API Contract (proposed)

```
PATCH /api/public/v1/feedback/{feedback_id}
Auth:  Bearer rrf_...  (scope: write)
Body (all fields optional, ≥1 required):
{
  "workflow_status": "resolved",              // one of new|in_review|resolved|closed
  "resolution_note": "closed via API",        // optional, forwarded to the status-change event
  "category_correction": {                    // optional
    "field": "pain_point" | "feature_request" | "sentiment",
    "corrected_value": "billing"
  }
}
200 → PublicFeedbackItem (updated)
400 → empty body / invalid status / invalid correction field
403 → key lacks 'write' scope
404 → feedback not found in this org
```
> Exact body shape (flat vs nested correction) is finalized in the tech-plan; the interview locked the *semantics*, not the wire format.

## Risks & Open Questions

- **R1 — Divergent write paths (the primary failure mode).** Mitigated by requirement #3 (shared helpers) + characterization tests on the internal routes.
- **R2 — Correction UX mismatch.** API users may expect the stored category to change and be surprised it doesn't. Mitigated by clear OpenAPI docs stating it records a training signal. (Product decision: record-only, confirmed.)
- **OQ1 — Idempotency on same-value status:** no-op skip vs re-emit. Default no-op; confirm in plan.
- **OQ2 — Wire format for the correction sub-object** (flat fields vs nested). Plan decides.

## Decisions locked (requirements interview, 2026-07-06)
1. Slice-1 coverage = **status + category/sentiment corrections**; tags/is_urgent deferred.
2. Correction semantics = **record-only** `AICorrection`, stored value unchanged (mirror dashboard).
3. Permission model = **single `write` scope**.
