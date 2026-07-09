# Aspect Spec — customers-bulk-ui

**Parent PRD:** `../prd.md` · **Owner agent:** `fe-react-specialist`
**Sequence:** LAST — after `bulk-actions-api` + `playbook-cohort-run` (consumes their API contracts).

## Problem slice & outcome

Give `/customers` a working selection + bulk-actions surface: check rows (or "select all N matching the
filter"), then Export / Tag / Assign owner / Run playbook against the cohort. Surface `tags` and `cs_owner`
so results are visible.

## In scope

- **Row selection.** Add a `select` checkbox column to the customers `columns` (mirror
  `feedbacks/columns.tsx:91-112`, use `@/components/ui/checkbox`, `enableSorting/enableHiding:false`). Wire
  `rowSelection` + `onRowSelectionChange` into the shared `DataTable` (`customers/page.tsx:556`). Add
  `getRowId: row => row.customer_email` support to the shared `DataTable` (small, backward-compatible change)
  so selection keys are emails, not indices; derive `selectedEmails` from selection.
- **Whole-filter selection.** A "Select all N matching this filter" affordance (banner when a page is fully
  selected, or a menu item) that switches the cohort to **filter mode** — the UI then sends the active
  `filter` object (segment/risk/search/include_archived), **not** a list of emails, to the bulk endpoints.
  Track cohort mode in state: `{mode: 'emails', emails} | {mode: 'filter', filter}`.
- **Bulk-actions toolbar.** When a cohort is active, show a toolbar/`DropdownMenu` in the header (next to the
  existing "Mark N as churned" button, `page.tsx:409-420`) with: Export CSV, Tag, Assign owner, Run playbook.
  Do **not** extend the shared DataTable's hardwired toolbar — keep it in the page header.
- **Dialogs** (mirror `BulkMarkChurnedDialog` props `{open, onOpenChange, cohort, onSuccess}`; toast via
  `sonner`; `queryClient.invalidateQueries(['customers'])` on success):
  - **Tag dialog:** tag input (add/remove mode toggle), affected-count preview.
  - **Assign-owner dialog:** org-member picker (fetch team members via existing team API), or "Unassign".
  - **Run-playbook dialog:** playbook picker (reuse `listPlaybooks`, show matching/active non-template),
    affected-count preview + queue-cap warning if count > 500.
  - **Export:** triggers the `GET /customers/export` download (respect current filters) — a
    `window.location`/anchor download or fetch→Blob; no dialog needed unless confirming large exports.
- **API client** (`lib/api/customers.ts`): add `exportCustomers(params)`, `bulkTag(cohort, tags, mode)`,
  `bulkAssignOwner(cohort, userId|null)`; extend `lib/api/playbooks.ts` `runPlaybookBatch` filter type with
  `emails?`/`segment?`. Add `tags` and `cs_owner` to `CustomerListItem`/`CustomerProfileData` types.
- **Surfacing:** a `tags` display (chips) and a `cs_owner` column/badge on the list; both on the profile page.
  Follow Sunset-Horizon theming — CSS variables + `color-mix(in oklch, ...)`, no hardcoded colors; shadcn/ui.
- **Docs:** brief `SELF_HOSTING.md` note on the bulk actions (operator-facing).

## Out of scope

- Backend endpoints (other aspects).
- Tag-filtering the list; saved cohorts; outreach.

## Acceptance criteria (testable, `npm run test` + `npm run lint` green)

- Selecting rows populates `selectedEmails` (via `getRowId` = email); toolbar appears; clearing works.
- "Select all N in filter" switches to filter mode and the subsequent bulk call sends `filter`, not `emails`
  (assert request payload in a mocked test).
- Each dialog calls the correct client fn with the correct cohort shape and shows a toast + refetches on
  success; error path shows `toast.error`.
- Export triggers a download hitting `/customers/export` with the active filters.
- Run-playbook dialog warns when affected count > 500 and blocks/deters the run.
- `tags` chips and `cs_owner` render on list + profile; unassigned owner renders cleanly.
- Row-click navigation still works and is not triggered by checkbox/toolbar clicks (DataTable already guards
  `input[type=checkbox]`/`button`).

## Dependencies & sequencing

Needs both backend aspects' contracts. Build after they're green. TDD: component/interaction tests RED-first
where the project's frontend test setup supports them (Vitest); otherwise assert on API-client payload
builders + rely on `npm run lint`/`build`.

## Risks

- Shared `DataTable` `getRowId` change must not break other consumers (feedbacks uses its *own* data-table,
  so risk is limited to customers + any other shared-DataTable users — grep before changing).
- Filter-mode cohort must serialize the same filter keys the backend `CohortFilter` expects (keep names in
  sync with `bulk-actions-api`).
