# Understanding — feat/public-api-crud-v3

**Phase 2 deep-dig synthesis (3 read-only agents).** Backend-only feature on `services/backend-api`.

## What the task is really asking

Close the two remaining "public write API v2" deferrals (AI-TRACKING.md:292): **bulk feedback writes**
and **custom-taxonomy CRUD** over `/api/public/v1`, under the existing `write` scope. Deepens the
developer-surface moat pillar for OSS self-hosters. No new DB tables required — both build on shipped
models.

## Ground truth from the dig

### Public write surface (mirror this)
- **Auth**: `src/models/api_key.py` (`ApiKey`, scopes = comma-delimited string `"read,ingest,write"`).
  `src/api/public/auth.py`: `verify_api_key` → `ApiKeyAuth{organization_id, scopes, key_row}`;
  `require_scope("write")` dependency (403 if missing). Cross-org access → **404** (org-scoped re-query;
  no 403 leak).
- **Existing single PATCH** `PATCH /api/public/v1/feedback/{id}` (`public_api.py:365-532`): request model
  `PublicFeedbackUpdate` with `extra="forbid"`; fields `workflow_status | resolution_note | correction |
  tags | is_urgent`. Tag caps: ≤20 tags, ≤50 chars each, trim+dedupe. Records category/sentiment/**urgency**
  `AICorrection`s (record-only — stored column unchanged). **Non-atomic: 3+ separate commits per call**
  (documented, tolerated because AICorrection is append-only).
- **`apply_status_change`** (`src/services/workflow_service.py:15-50`): already a **batch primitive** — takes
  a `List[FeedbackItem]`, no-op-skips same-status, does NOT commit/webhook/invalidate (caller does). The
  internal bulk endpoint `POST /api/v1/workflow/status` (`workflow.py:141-199`) passes the whole list in
  one call + single commit + one webhook/cache/emit pass. **→ Bulk should do the same: one list call, one
  commit — not a Python per-item loop.**
- **No per-item error envelope exists** in the public router today. Internal bulk endpoints just return
  aggregate counts (`{"updated": n}`, `{"deleted_count": n}`). New convention needed.

### Bulk precedent (segment-actions) — the shape to reuse
- `src/schemas/cohort.py`: `Cohort` = **exactly one of** `emails[]` XOR `filter{segment,risk_level,search,include_archived}`
  (422 if both/neither); `BulkActionSummary{matched, updated, skipped, errors[]}`.
- `src/services/cohort_service.py`: `resolve_cohort` (org-scoped; unknown/cross-org emails **skipped**, not
  errors); `count_cohort` for previews.
- Per-item best-effort within **one commit** (`/customers/bulk/tags`, `/customers/bulk/assign-owner`).
- **500 cap** (`RUN_BATCH_MAX_CUSTOMERS`) only on **async-queuing** run-batch (hard 422); `count_only=true`
  dry-run. Static bulk routes must be registered **before** parametric `/{id}` routes (FastAPI ordering trap).

### Custom taxonomy (mirror internal CRUD)
- Dedicated table `custom_categories` (`src/models/custom_category.py`): `{name(≤100), description?,
  category_type ∈ pain_point|feature_request|urgency|general, is_active}`. **No keyword field** (keywords
  derived from `description` in the keyword categorizer). **No unique constraint / no max-count** in DB.
- Internal CRUD `src/api/routes/categories.py` (`/api/v1/categories/custom`): `GET /custom` (org-scoped,
  no admin), `POST` (201, **409 on dup (org,type,name)**), `PATCH` (name/description/is_active; type not
  editable; 409 on rename collision), `DELETE` (204 hard delete). `require_admin_or_owner` on writes.
- **Blast radius of edit/delete** (categories are free-text strings, **no FK** from feedback/corrections):
  - Delete/rename → existing feedback keeps the old string (orphaned, not broken).
  - **Automation rules `feedback_category_match` key on the category string** → a rename silently breaks
    matching rules. This is the one real hazard → surface as a caveat / consider a warning, don't block.
  - M5.2 category classifier vocab is **decoupled** (derives from `AICorrection.corrected_value`, not this
    table) → renaming/deleting a category does NOT corrupt the classifier. Safe.
- Frontend ref: `settings/ai/page.tsx` "Custom Categories" card → `lib/api/categories.ts` (not in scope; API-only).

### Customer CRUD — NOT coherent (open question resolved)
- The only "customer" entity is `CustomerHealth` (`customer_health_scores`, unique `(org, email)`), a
  **derived aggregate**. Only constructor is inside `update_customer_health` (analysis upsert), triggered
  by feedback analysis. **No create endpoint exists anywhere**; customer surface is read + tag/owner/action
  mutations only. Created implicitly on first feedback; archived when last feedback deleted.
- **Decision: drop customer create/delete.** If a customer write slice is wanted at all, it's only **bulk
  tag / owner update** mirroring `/customers/bulk/*` via the `Cohort` contract. Recommend deferring even
  that unless explicitly desired — the two headline deferrals (bulk feedback + taxonomy) are the priority.

## Ambiguities to resolve in the interview
1. **Bulk feedback shape**: uniform patch over an explicit `ids[]` (simplest, mirrors internal
   `POST /workflow/status`) vs heterogeneous per-item patches vs a Cohort-style filter selector. Recommend
   **uniform patch over `ids[]`** with a `BulkActionSummary`-style per-item results envelope.
2. **Which fields bulk-editable**: status only, or status + tags + is_urgent (full parity with single PATCH)?
3. **Bulk cap + sync vs async**: sync single-commit with a hard cap (e.g. 200–500) → 422 over cap, matching
   run-batch's reject-don't-truncate stance. Any `count_only` preview needed?
4. **Response envelope**: `BulkActionSummary{matched,updated,skipped,errors[]}` (aggregate) vs a richer
   `{results:[{id,status,error}]}` per-item array. Public API consumers usually want per-item.
5. **Taxonomy public parity**: `extra="forbid"` on public create/update? enforce a max-count now (internal
   has none)? expose a delete-safety warning for rules keyed on the name?
6. **Customer bulk**: in or out for this feature? (Recommend out / separate.)

## Affected areas (all backend-api)
- `src/api/routes/public_api.py` (+ maybe a new `src/api/public/` module), `src/schemas/` (new bulk +
  taxonomy public schemas), reuse `src/services/workflow_service.py`, `src/services/cohort_service.py`,
  `src/services/ai_correction_service.py`, `src/models/custom_category.py`. Public OpenAPI/Swagger picks up
  new routes automatically. **No new migration** anticipated.
