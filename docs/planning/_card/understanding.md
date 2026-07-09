# Understanding — segment-actions (Phase 2 dig)

_Synthesis of two read-only mapping agents (backend + frontend). All paths in the worktree; line refs `file:line`._

## What the feature really is

Make the just-shipped **Customer Segments** actionable. Today `segment` is a read-only column + filter
on the Customers page (backend + frontend both already support `?segment=`). This feature adds an
**action surface** on `/customers`: select a cohort (by segment filter or row checkboxes) and act on it
in bulk — **export**, **run a playbook**, and (scope TBD) **tag / assign a CS owner**. It deepens the
churn → health → **playbook** loop by letting it operate on cohorts, which is the reason segments exist.

## Two card assumptions that the code CONTRADICTS (must resolve)

1. **Alembic is SINGLE-headed, not multi-heads.** Current head is `6d7e00e682c7`
   (`add_segment_to_customer_health`); the chain is linear. The card's "6-heads / merge heads first"
   note is stale (it predates the segment merge, which landed linearly). **A new migration branches from
   `down_revision = "6d7e00e682c7"`** — no merge needed.

2. **Binding a playbook to a segment does NOT require relaxing `probability_min/max` NOT NULL.** The card
   inherited the segments-PRD assumption that segment-targeting means editing the *playbook definition*.
   But `ChurnPlaybook.probability_min/max` are `NOT NULL` in model + migration + Pydantic + a
   `CheckConstraint(min < max)` — and playbook→customer targeting is a **run-time** concern, already
   modelled by `POST /playbooks/{id}/run-batch` via `_apply_run_batch_filters` (`playbooks.py:128-157`,
   `RunBatchFilters` `:179-184`). **Cleanest path: extend `run-batch` filters to accept `emails[]` and/or
   `segment`** and select `CustomerHealth` rows directly — no playbook-model migration, no NOT-NULL
   change. This makes slice 1 materially cleaner than the card's caveat implied.

## Code map (grounded)

### Backend (`services/backend-api`)
- **List API:** `GET /api/v1/customers/` → `list_customers` (`customers.py:252-364`). Validates `segment`
  against `SEGMENT_SLUGS` (`:282-286`), filters `CustomerHealth.segment == segment` (`:296-297`), org-scoped
  (`:288`). Serializer `CustomerListItem` (`:40-52`): email, name, health, risk, confidence, feedback_count,
  last_feedback_at, last_active_at, sentiment_trend, is_archived, has_llm_analysis, `segment`. **No `tags`
  field. No CSV export endpoint** (greenfield). Per-row `_compute_sentiment_trend_for_customer` (`:340`) is
  an N+1 — relevant if a *server-side* export streams all rows.
- **Bulk precedent:** `POST /api/v1/customers/churn-events/bulk` → `bulk_mark_churned`
  (`churn_events.py:162-205`). Schema `ChurnEventBulkCreate` (`schemas/churn_event.py:67-89`): `emails:
  List[str]` (normalized `.strip().lower()`), returns `BulkSummary {created, skipped, errors}`. Stamps
  `organization_id` on write; does NOT verify emails are existing org customers. **Static paths must be
  registered before parametric `/{email}` routes** (`churn_events.py:157-159`).
- **Playbooks:** `playbooks.py` (router gated `require_feature("churn_playbooks")`). Single run `POST
  /{id}/run` (`:404-447`), **batch run `POST /{id}/run-batch`** (`:450-515`) with daily-limit + celery
  dispatch (`tasks.churn_playbooks.run_playbook`). Targeting is **probability-range only** today
  (`_apply_run_batch_filters:128-157`); **no segment/emails predicate exists yet** — that's the extension
  point.
- **Segment data:** `CustomerHealth.segment` `String(30)` nullable (`customer_health.py:34`), index
  `ix_customer_health_segment (organization_id, segment)` (`:87`). Classifier
  `segment_service.classify_segment` — **DUPLICATED in worker-service; keep both in sync** (header comment,
  TRACKING.md, commit `19d0c14`). 7 slugs: at_risk, silent_churner, dormant, power_user, happy_advocate,
  new, unsegmented.
- **CS-owner / assignee: does NOT exist on customers.** Only `feedback.assigned_to` + `AssignmentRule`
  (feedback-level). A customer CS-owner needs a **new column on `customer_health_scores` + migration**.
- **Migrations:** single head `6d7e00e682c7`; new revision branches from it.

### Frontend (`services/frontend-web`)
- **Customers page:** `app/(dashboard)/customers/page.tsx` (`CustomersPage`). Filters are React state (not
  URL-synced); `queryParams` spreads `search`/`risk_level`/`segment` into `customersAPI.list`. Segment
  filter `Select` (`:507-535`). Table = shared `DataTable` (`components/shared/data-table.tsx`) in
  `serverSide` mode.
- **Row-selection GAP:** `selectedEmails`/`bulkChurnOpen` state + a "Mark N as churned" button
  (`:409-420`) + `BulkMarkChurnedDialog` mount (`:585-590`) already exist, but the table has **no checkbox
  column and no `rowSelection`/`onRowSelectionChange` wired** → `selectedEmails` never populates (dead
  today). The shared `DataTable` supports `rowSelection` props but **doesn't set `getRowId`** (keys are row
  indices, not emails) and its built-in toolbar is hardwired to analyze/delete only. Checkbox-column
  precedent: `feedbacks/columns.tsx:91-112` (uses `@/components/ui/checkbox`).
- **Bulk dialog pattern:** `BulkMarkChurnedDialog.tsx` — props `{open, onOpenChange, selectedEmails,
  onSuccess}`; toast on success/error; parent clears selection in `onSuccess`. New bulk dialogs should
  mirror this shape and add `queryClient.invalidateQueries(['customers'])` for mutations.
- **Run playbook UI:** `RunPlaybookDropdown.tsx` — single-customer only (`customerEmail`, `churnProbability`),
  filters playbooks whose band contains the probability. API client `lib/api/playbooks.ts` already has
  `runPlaybookBatch(id, filters)` → `POST /playbooks/{id}/run-batch`, but `filters` = `{probability_min?,
  probability_max?, time_to_churn_bucket?}` — **no `emails`/`segment` yet** (matches backend gap).
- **CSV export precedent (client-side):** `lib/api/churn-events.ts` `exportChurnEventsCsv` paginates all
  pages + Blob download. Direct pattern to reuse for a client-side customer export (no backend needed).
- **Customers API client:** `lib/api/customers.ts` — `CustomerListParams` has `segment?`; `CustomerListItem`
  has `segment?` but **no `tags`**. Segment badge: `SegmentBadge.tsx` + `lib/constants/segments.ts`
  (`SegmentSlug` union, labels, `color-mix` theming).
- **Customer tags: greenfield** (tags exist only on feedback).

## Open questions for the interview (Phase 3)

1. **Slice-1 scope.** Recommend: (a) row selection + bulk toolbar, (b) **CSV export** (client-side, reuse
   `exportChurnEventsCsv` pattern), (c) **run playbook on selection/segment** (extend `run-batch` filters —
   no playbook migration). Treat **bulk tag** and **bulk CS-owner assign** as slice 2 (both greenfield
   schema: new column/table + migration + UI). Confirm this cut.
2. **Run-playbook targeting semantics.** Run against the explicit **selected emails**, or against the whole
   **active segment filter** (all matching rows, not just the current page)? The latter needs the backend to
   resolve the segment server-side (safer for large cohorts than sending thousands of emails).
3. **Export: client-side vs server-side.** Client-side (reuse precedent, respects current filters, no N+1
   worries at page scale) vs a streaming backend endpoint (needed only if exporting very large orgs). Which
   columns to include.
4. **Playbook gating under OSS.** The playbooks router is gated `require_feature("churn_playbooks")` — under
   the OSS/all-unlocked pivot, confirm whether the run-batch extension inherits that gate as-is (leave gate
   untouched, features unlocked at the plan config level) — do not re-introduce plan gating.
5. **Org-scope validation on bulk.** Mirror the loose bulk-churn pattern (org-stamp, per-row skip), or
   validate that each email is an existing org customer? Recommend validating for the action endpoints.
