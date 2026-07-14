# PRD — Public API CRUD v3 (bulk feedback writes + custom-taxonomy CRUD)

**Slug:** `public-api-crud-v3`
**Branch:** `feat/public-api-crud-v3`
**Status:** Draft (pre-review-gate)
**Author:** rereflect-begin-fast pipeline, 2026-07-14
**Source:** `rereflect-next` handoff — no GitHub issue (freeform)

---

## Problem Statement

The public REST API (`/api/public/v1`) is a named moat pillar for the open-source, self-hosted edition:
operators automate their own instance with their own API keys. Its **write** surface, shipped in two prior
slices (`public-api-write-crud`, `public-api-write-v2`), is entirely **single-item**: `POST /feedback`,
`PATCH /feedback/{id}`, `DELETE /feedback/{id}`. Two capabilities were explicitly deferred to "v2"
(AI-TRACKING.md:292): **bulk writes** and **custom/taxonomy CRUD**.

Consequences today:
- An operator triaging or resolving many feedback items via the API must issue one HTTP round-trip per
  item — painful at volume, and each single PATCH is already non-atomic (multiple commits internally).
- Custom categories (the org's taxonomy) can only be managed through the dashboard (`/api/v1/categories`,
  JWT + admin). There is **no** programmatic way to create/list/update/delete them — so an operator can't
  script their taxonomy or manage it from CI/IaC, despite everything else being API-driven.

**Who has the problem:** self-hosting operators / developers integrating Rereflect into their own tooling
(the public-API persona). Evidence it's real: the public write API exists and is used; these two gaps are
the documented, intentional remainder of that same workstream.

## Goals & Success Metrics

**Goal:** Make the two deferred public-write capabilities real, mirroring shipped internal behavior, with
honest partial-failure semantics.

Success (measurable, testable):
- A `write`-scoped API key can update status/tags/is_urgent for **N feedback items in one request** and
  receive a **per-item result** for each (updated / skipped / error) — verified by tests.
- **Partial-failure is honest and non-contagious:** a batch of `[good, good, bad]` ids returns
  2×`updated` + 1×`error`, the 2 good items are **persisted**, and the bad item's failure does not roll
  back or corrupt the others — verified by an explicit test.
- A `write`-scoped key can **create/list/update/delete** custom categories over the public API, with the
  same 409-duplicate / 404 / kind-validation semantics as the internal dashboard route — verified by tests.
- Both surfaces appear automatically in the public OpenAPI/Swagger (`/api/public/v1/docs`).
- **Zero regression** to the shipped single-item PATCH/DELETE and the internal categories CRUD
  (characterization-locked where shared code is touched).

Non-goals for metrics: adoption numbers (single-tenant OSS; we don't collect them).

## User Personas & Scenarios

- **Operator / developer (API persona).** Has an API key with `write` scope. Scenarios:
  1. Nightly job: resolve all feedback linked to a shipped release → one bulk call with the item IDs.
  2. Bulk re-tag or de-flag a set of items after a mis-classification → one bulk call, reads per-item results.
  3. Manage taxonomy from code/CI: create the org's custom pain-point categories on setup; rename or retire
     one later → taxonomy CRUD calls.

## Requirements

### Must-have

**M1 — Bulk feedback write endpoint.** `POST /api/public/v1/feedback/bulk` (`write` scope).
- Request: `{ "ids": [int, ...], "patch": { workflow_status?, resolution_note?, tags?, is_urgent?, correction? } }`.
  - `patch` reuses the **same field set + validation** as the single `PublicFeedbackUpdate`
    (tags ≤20 & ≤50 chars, `workflow_status` literal, `is_urgent` bool, optional `correction`,
    `extra="forbid"`). At least one mutating field required (else 422).
  - The `patch` is **uniform** — applied identically to every listed id (heterogeneous per-id patches are
    out of scope).
- **Cap 500 ids → 422** if exceeded (reject, don't truncate; matches `RUN_BATCH_MAX_CUSTOMERS`). Empty `ids`
  → 422.
- **Org-scoped**: only this org's feedback is touched; ids not found in the org are **skipped** (not errors,
  no 403/404 leak), mirroring the cohort `emails` skip semantics.
- **Best-effort within a single logical operation.** Status changes go through `apply_status_change` on the
  **whole matched list in one call + one commit** (the batch primitive, not a Python per-item loop);
  tags/is_urgent/correction applied per item. A per-item failure is captured, not fatal to the batch.
- Response `200`: `{ "matched": int, "updated": int, "skipped": int, "results": [ {"id": int, "status":
  "updated"|"skipped"|"error", "reason"?: str} ] }`. `results` covers **every input id** (including
  not-found → `skipped`, `reason:"not_found"`; and same-value no-op → `updated` with no field change, or a
  distinct `noop` — see Open Questions).
- Same side effects as the single PATCH, done **once per batch**: cache invalidation
  (`dashboard:{org}:*`, `analytics:{org}:*`), `feedback.status_changed` webhook per changed item, and the
  `workflow:status_changed` event with all changed ids.
- **Edge cases (must be pinned in tech-plan):**
  - **Duplicate ids** in `ids[]` → dedupe (preserve first occurrence), mirroring cohort `emails` dedupe;
    `results` has one entry per unique id.
  - **Non-contagious partial failure** — one item's per-item-field failure (e.g. a tag-cap violation that
    slips past request validation, or a correction write error) must not roll back another item's already
    applied change. See the field-boundary note below.
  - **Field boundary within an item** — `workflow_status` is applied via the batched `apply_status_change`
    (one call, one commit for the whole matched set) **before** the per-item tags/is_urgent/correction pass.
    A per-item result must be able to express that an item's status was updated while its tags errored ⇒
    the `results` entry carries an optional per-field breakdown (see OQ6), not a single opaque status.
  - **`results` ordering** follows the (deduped) input order.

**M2 — Custom-taxonomy CRUD (public).** Mirror internal `/api/v1/categories/custom` onto
`/api/public/v1/categories` (or `/api/public/v1/custom-categories` — see Open Questions):
- `GET /categories` (`read` scope) — list, optional `?category_type=` filter, org-scoped.
- `POST /categories` (`write` scope) — create; `{name (1–100), description?, category_type ∈
  pain_point|feature_request|urgency|general}`; **409 on duplicate `(org, category_type, name)`**; 201.
- `PATCH /categories/{id}` (`write` scope) — partial update `{name?, description?, is_active?}`
  (`category_type` **not** editable); 404 if missing; 409 on rename collision.
- `DELETE /categories/{id}` (`write` scope) — **hard delete** (204), mirroring internal semantics, **plus**
  a non-blocking warning surfaced when the deleted name is referenced by any automation rule
  (`feedback_category_match`). Because 204 has no body, the warning is delivered via a response header
  (e.g. `X-Rereflect-Warning`) or the delete returns `200` with a warning body — see Open Questions.
- Public request models use `extra="forbid"` (public-hygiene parity with the feedback models), even though
  the internal models don't.

**M3 — No regression.** Shared code touched for M1/M2 (the single-PATCH helpers, `apply_status_change`,
`resolve_cohort` if used, internal categories logic) stays byte-behaviour-identical; lock with
characterization tests before refactoring.

**M4 — Docs & tracking (part of "done", as every prior public-API slice was).** Update the public-API
OpenAPI description/`SELF_HOSTING.md` for the two new capabilities, add a `CHANGELOG.md` entry, and mark
the bulk-writes + taxonomy-CRUD items resolved in `AI-TRACKING.md` (the deferral at line 292) and
`DEV-TRACKING.md`.

### Should-have
- **S1 — `count_only`/dry-run** on bulk (query param) returning `{matched}` without mutating — matches the
  run-batch preview affordance. (Cheap; include if it doesn't bloat the slice.)
- **S2 — Automation-rule reference check reused** for both taxonomy `DELETE` warning and (optionally) a
  `PATCH` rename warning.

### Nice-to-have (explicitly deferrable)
- N1 — Bulk delete feedback via public API (`POST /feedback/bulk-delete`). Not requested; note as a natural
  follow-on.
- N2 — Filter-selector bulk (apply patch to a `GET /feedback` filter match). Rejected for this feature
  (accidental mass-edit risk); ids-only is safer.
- N3 — Max-count limit on custom categories (internal has none; don't introduce divergence here).

## Technical Considerations

- **Service:** `services/backend-api` only. No frontend, worker, or analysis-engine changes. **No new DB
  migration** (both build on existing `feedback_items` / `custom_categories` / `api_keys`).
- **Auth:** existing `verify_api_key` + `require_scope("read"|"write")`; comma-delimited scope string. No new
  scope.
- **Reuse:** `apply_status_change` + `dispatch_status_webhooks` (`workflow_service.py`), `create_ai_correction`
  (`ai_correction_service.py`), the `custom_categories` model + the internal category validation logic, and
  the automation-rule lookup used by `feedback_category_match`.
- **Routing trap:** register static bulk/collection routes **before** parametric `/{id}` routes in the public
  router (segment-actions documents this FastAPI ordering hazard).
- **OpenAPI:** the public router auto-filters `/api/public/v1/*` into its own OpenAPI + Swagger; new routes
  surface automatically. Update the public-API docs/OpenAPI description text as the shipped slices did.
- **Multi-tenancy:** every query filtered by `auth.organization_id`; cross-org ids/categories → skipped/404.

### API Contracts (summary)
| Method | Path | Scope | Notes |
|---|---|---|---|
| POST | `/api/public/v1/feedback/bulk` | write | ids[]≤500 + uniform patch → per-item results |
| GET | `/api/public/v1/categories` | read | list, `?category_type=` |
| POST | `/api/public/v1/categories` | write | create, 409 dup, 201 |
| PATCH | `/api/public/v1/categories/{id}` | write | name/description/is_active; 404/409 |
| DELETE | `/api/public/v1/categories/{id}` | write | hard delete + rule-reference warning |

## Risks & Open Questions

- **R1 — Partial failure honesty.** The single PATCH is non-atomic already; bulk multiplies this. Mitigation:
  per-item `results` array is the contract — we never claim transactional success. Status changes are the one
  field that IS batched atomically (one `apply_status_change` + commit); tags/urgent/correction are per-item.
  Document precisely which fields are all-or-nothing vs per-item.
- **R2 — Taxonomy delete/rename breaks automation rules** (categories are free-text, no FK). Mitigation:
  non-blocking warning when a deleted/renamed name is rule-referenced. We do **not** cascade or block —
  matches internal behavior, just makes it visible.
- **OQ1 — Path for taxonomy:** `/api/public/v1/categories` vs `/custom-categories`. Recommend `/categories`
  for brevity; confirm no collision with an existing public read path.
- **OQ2 — DELETE warning delivery:** 204-no-body can't carry a warning. Options: (a) `X-Rereflect-Warning`
  header on the 204; (b) return `200` + `{deleted:true, warning:...}` for the public route only. Recommend
  (a) to keep 204 semantics; decide in tech-plan.
- **OQ3 — Bulk no-op vs updated:** if a listed id is already at the target status with no other field change,
  report `updated` (idempotent success) or a distinct `noop`? Recommend counting it as `updated` (no error)
  but marking `status:"noop"` in `results` for transparency.
- **OQ4 — `correction` in a uniform bulk patch:** applying the same `correction.corrected_value` to many
  heterogeneous items is rarely meaningful. Recommend **allowing** it (parity) but documenting it as an
  advanced/rare use; it just records one AICorrection per item.
- **OQ5 — `count_only` (S1):** include now or defer? Low cost; lean include.
- **OQ6 — per-item vs per-field result granularity (the design knot).** Because status is batched-atomic and
  applied before the per-item fields, a single item can end up "status updated, tags errored." Decide in
  tech-plan whether each `results[i]` is a single `status` + optional `reason`, or carries a per-field map
  (`{status: "updated", fields: {workflow_status: "ok", tags: "error:too_long"}}`). Recommend the richer
  per-field shape only if a real failure path survives request-level validation; otherwise keep `results`
  per-item and rely on `extra="forbid"` + shared validators to make per-item field failures near-impossible
  (in which case document that status is the only batched-atomic field).

## Out of Scope

- **Customer create/delete via API** — resolved as incoherent (customers are derived aggregates of feedback;
  no create path exists anywhere). Customers remain implicitly created by feedback ingestion.
- **Customer bulk tag/owner via public API** — deferred to a separate feature (the user chose the two
  headline deferrals only).
- **Mutating the stored category/sentiment column** (vs record-only corrections) — remains deferred, as in
  the shipped slices.
- **Heterogeneous per-id bulk patches**, **filter-selector bulk** (N2), **bulk feedback delete** (N1),
  **frontend/UI changes**, **new API scopes**, **new DB tables/migrations**.
