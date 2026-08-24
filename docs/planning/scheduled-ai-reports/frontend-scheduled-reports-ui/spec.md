# Aspect spec — frontend-scheduled-reports-ui

**Feature:** scheduled-ai-reports · **Aspect:** `frontend-scheduled-reports-ui`
**Source:** `docs/planning/scheduled-ai-reports/prd.md` §4.4

## Problem slice & user outcome

On the existing `/reports` page, an operator (admin/owner) can manage report schedules from
a **Scheduled** tab: see them in a table (type, cadence, day/hour, recipients, last run),
create one via a dialog, toggle enabled, and delete. Members see the list read-only.

## In-scope requirements

1. **API client** `services/frontend-web/lib/api/scheduled-reports.ts` (follows
   `lib/api/reports.ts` shape, shared `apiClient`):
   - `list()`, `create(payload)`, `update(id, payload)`, `delete(id)`, `toggle(id)`;
   - `ScheduledReport` type (id, report_type, date_range_days, cadence, hour_utc,
     day_of_week, day_of_month, recipients, enabled, last_run_at, created_at, updated_at);
   - reuse `REPORT_TYPE_LABELS` / `REPORT_TYPE_COLORS` from `lib/api/reports.ts`.
2. **UI on `/reports`** (`app/(dashboard)/reports/page.tsx`):
   - shadcn `Tabs` (Reports | Scheduled) around the existing list + the new tab;
   - Scheduled tab: table (type Badge, cadence + day/hour label e.g. "Weekly · Mon 09:00
     UTC", recipients count, last run, enabled `Switch` → `toggle(id)` with optimistic
     replace + `toast`, delete with confirm `Dialog`, `data-testid`s on rows/empty state);
   - "New schedule" `Dialog` form: report type `Select` (4), date range `Select` (7/30/90),
     cadence `Select` (daily/weekly/monthly) with conditional `day_of_week` (0-6) and
     `day_of_month` (1-31) fields, hour `Select` (0-23 UTC), recipients input (comma/newline
     separated, seeded with the current user's email) — create → `toast` + row refresh;
   - member users: hide create/toggle/delete controls (read-only list);
   - loading spinner + empty state (`data-testid="empty-state"`), mirroring the existing page.
3. **No sidebar change** — the tab lives on the existing Reports nav item.

## Out-of-scope boundaries

- No edit-in-place of an existing schedule beyond toggle/delete (PATCH exists in the API;
  a full edit form is a follow-up) — create covers new schedules; the dialog validates like
  the backend.
- No "run now" button (API exists in the worker aspect; surface it only if trivial).

## Acceptance criteria (testable)

- Vitest page test `services/frontend-web/__tests__/reports/ReportsPageScheduled.test.tsx`
  (model on `ReportsPage.test.tsx`; mock `next/navigation`, `sonner`, both API modules via
  `vi.hoisted` + `importOriginal`): empty state; list renders rows with type/cadence/last run;
  toggle calls `toggle(id)` and updates state; delete flows through confirm dialog; create
  dialog submits correct payload incl. cadence-conditional fields; member sees no create/
  toggle/delete controls.
- API-client test `lib/api/__tests__/scheduled-reports.test.ts` (mock `apiClient` methods).
- `cd services/frontend-web && pnpm test && pnpm lint` green.

## Dependencies & sequencing

- Depends on aspect `backend-schedule-crud` (API contract).
- Build after backend aspect; can run in parallel with the worker aspects.

## Open questions / risks

- Keep the reports page test suite green: the existing `ReportsPage.test.tsx` renders the
  page — adding Tabs must not break its selectors (keep existing `data-testid`s intact).
- `useSearchParams`-free (no Suspense needed); plain client-component state like the
  existing page.