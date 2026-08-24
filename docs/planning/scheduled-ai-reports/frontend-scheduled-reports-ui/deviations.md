# Deviations — frontend-scheduled-reports-ui

Recorded at completion (2026-08-25) per the aspect plan §7 ("Do not restructure the
existing Reports list view beyond wrapping it in Tabs").

1. **Scheduled tab kept inline in `page.tsx`.** The plan preferred a separate
   `components/reports/ScheduledReportsTab.tsx` once the page passes ~450 lines, but the
   aspect's file scope is fixed to four files (orchestration constraint), so the scheduled
   section lives in `app/(dashboard)/reports/page.tsx` as `ScheduledReportsSection`.
2. **Weekly default day is Monday (1), not Sunday (0).** The create dialog defaults to
   `day_of_week = 1` so the seed cadence reads "Weekly · Mon 09:00 UTC" — matching the
   plan's example label and the PRD's Monday-09:00 founder persona. Index 0 = Sunday
   remains selectable in the dropdown.
3. **The existing `ReportsPage.test.tsx` was not modified.** `useAuth` is only called
   inside the tab-mounted `ScheduledReportsSection`, so the pre-existing test renders
   without an auth mock; the Reports tab stays the default and every legacy `data-testid`
   (`report-row-*`, `empty-state`, `confirm-delete-button`, …) is unchanged.
4. **Create dialog defaults:** report type `executive_summary`, date range 30 days,
   cadence weekly (Mon), hour 09:00 UTC, recipients seeded with the current user's email.