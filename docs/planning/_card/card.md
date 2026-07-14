# Card — feat/public-api-crud-v3 (freeform, no GitHub issue)

**Type:** feat
**Slug:** public-api-crud-v3
**Branch:** feat/public-api-crud-v3
**Source:** `rereflect-next` handoff (2026-07-14). No GitHub issue — freeform.

## Brief (from rereflect-next handoff)

Extend the shipped public write API with the remaining v2 deferrals that are clean under
self-hosting. Two shipped predecessors define the lineage:

- `docs/planning/public-api-write-crud/` — added the `write` scope + `PATCH /api/public/v1/feedback/{id}`
  (workflow_status change via shared `apply_status_change`; record-only category/sentiment
  `AICorrection` training signals). Shipped 2026-07-06.
- `docs/planning/public-api-write-v2/` — `PATCH` also accepts `tags` + `is_urgent`; added
  `DELETE /api/public/v1/feedback/{id}`. Shipped 2026-07-07.

Both explicitly park the remainder (AI-TRACKING.md:292):
> **Deferred (v2):** mutating the stored category/sentiment column, **customer/taxonomy CRUD, bulk writes**.

This feature builds the **bulk writes** and **custom-taxonomy CRUD** slices.

## Why this, why now (moat grounding)

- The public API / developer surface is an explicitly-named moat pillar (the self-host
  programmability story). It fits OSS/self-hosted/BYOK and is single-tenant-clean.
- It's a clean, unblocked follow-on to shipped work with a crisp testable first slice —
  unlike M5.3 churn ML (hard-blocked at ~500 labels) or the narrow flywheel per-kind split.

## Scope (slices)

**Slice 1 (first): bulk feedback writes.**
- Bulk status/tag/urgent writes over `/api/public/v1`, under the existing `write` scope,
  org-scoped (cross-org → 404 / skipped-per-item).
- Reuse the shared `apply_status_change` helper **per item**.
- Return a **per-item results array** (id → ok/error). The single-item `PATCH` is explicitly
  best-effort / non-atomic (AI-TRACKING.md:292), so the bulk endpoint must report partial
  failure rather than pretend to be transactional.

**Slice 2: custom-taxonomy (custom-category) CRUD.**
- CRUD over the org's custom pain-point / feature-request / urgency categories, backed by
  the existing per-org custom-taxonomy config (OrgAIConfig custom categories — verify exact
  model in the dig).

## Open questions / caveats (carry into PRD)

- **Customer-record CRUD is NOT a commitment.** Customers are implicit via `customer_email`
  on feedback + a derived `customer_health_scores` row — there may be nothing coherent to
  "create." Treat as an open question in the dig; confirm before speccing.
- **Bulk atomicity:** decide per-item best-effort vs all-or-nothing. Lean per-item + explicit
  results (matches the shipped non-atomic single PATCH). Define the cap (existing bulk
  precedents cap at 500 — e.g. segment-actions cohort).
- **Taxonomy CRUD blast radius:** custom categories feed the analyzer prompt + keyword
  categorizers + (now) the per-org category classifier's label vocab (M5.2). Editing/deleting
  a category mid-flight must not corrupt those. Understand the consumers before allowing delete.

## Guardrails / out of scope

- Fits OSS/self-hosted/BYOK; single-tenant-clean; no hosted-SaaS / plan-gating assumptions.
- No new scope beyond the existing `write` scope unless the dig shows a real need.
- Mutating the *stored* category/sentiment column (vs record-only correction) remains deferred
  unless the dig surfaces a strong reason.

## Relevant files (dig starting points)

- `services/backend-api/src/api/routes/public_api.py` — public v1 router (PATCH/DELETE feedback, API-key scopes)
- `services/backend-api/src/api/routes/feedback.py` — internal status/tags/urgent + `apply_status_change`
- `services/backend-api/src/services/` — `apply_status_change` helper, ai_correction_service
- `services/backend-api/src/models/` — API key / scopes model, OrgAIConfig (custom categories), feedback, customer_health_scores
- `services/backend-api/src/api/routes/segment_actions` or `customers` bulk endpoints — bulk cohort precedent (500 cap, per-item shape)
- Reference shipped precedent: `docs/planning/public-api-write-crud/`, `docs/planning/public-api-write-v2/`, `docs/planning/segment-actions/`
