# Aspect spec — frontend-versioning-ui

**Parent PRD:** `../prd.md` (M9, S1) · **Depends on:** `backend-routes`.
Files: `services/frontend-web/components/settings/ClassifierAccuracyCard.tsx`,
`services/frontend-web/lib/api/classifier-accuracy.ts` (+ tests). pnpm.

## Problem slice
Surface version history, make rollback targetable + confirmed, and expose the
hold/resume state so an operator can see and control durable rollback.

## In scope
- **API client** (`lib/api/classifier-accuracy.ts`, axios `apiClient`, query params):
  - `getClassifierVersions(classifierType)` → `GET /classifier/versions`.
  - Extend `rollbackClassifier(classifierType, toVersionId?)` with optional
    `to_version_id`.
  - `resumeClassifier(classifierType)` → `POST /classifier/resume`.
  - Types: `ClassifierVersionSummary`, `ClassifierVersionsResponse`; add `hold` to
    `ClassifierAccuracyResponse`.
- **`ClassifierAccuracyCard`** (`'use client'`, stays inside the AI page `<Suspense>`):
  - **Version-history table** (shadcn `Table`): fit_at, macro-F1 (`formatMetricPercent`),
    labels, an **Active** badge on the active row, and a **"Roll back to this"** action
    on each non-active row (admin/owner only).
  - **Hold indicator**: when `hold` is true, a persistent "Auto-promotion paused"
    badge + a **Resume auto-promotion** button (admin/owner). Uses theme tokens
    (`var(--chart-1)` / `--destructive`, `color-mix(in oklch, …)`), no hardcoded color.
  - **Confirm dialog** before any rollback/resume (plain `Dialog` — NO
    `alert-dialog`; pattern: `components/customers/ConfirmSuggestionDialog.tsx`),
    `sonner` `toast.success`/`toast.error` (global Toaster) replacing the current
    silent inline error.
  - Refetch versions + accuracy after each action.
  - **S1 nudge** (should-have): if `hold` and the latest `held` eval run in `history`
    has a positive delta, show "a newer candidate would beat your held version by +X —
    Resume?". Degrade gracefully if data absent.
- Keep the existing "Recent shadow-mode evaluations" A/B block.

## Out of scope
- Backend/worker. New routing/pages (extends the existing card in-place).
- Redesign of the accuracy metrics block.

## Acceptance criteria (testable) — vitest, mock `@/lib/api-client`; component tests
reuse `__tests__/settings/ClassifierAccuracyCard.test.tsx` fixtures + `userEvent`
- Client tests: each function calls the exact URL with the right query params
  (`to_version_id` included only when passed).
- Card renders a version table from a populated `versions` response; the active row
  shows the Active badge and no roll-back action.
- Clicking "Roll back to this" opens the confirm dialog; confirming calls
  `rollbackClassifier(type, id)` and toasts success; error path toasts the FastAPI
  `detail`.
- When `hold=true`: "Auto-promotion paused" + Resume button render; Resume calls
  `resumeClassifier` and refetches.
- Mutating controls hidden when `isAdminOrOwner=false`; table + hold badge still
  visible (read-only).
- `pnpm --filter frontend-web test` and `pnpm --filter frontend-web lint` green.

## Dependencies / notes
- axios error shape `err?.response?.data?.detail` (existing convention).
- shadcn primitives present: `table`, `dialog`, `badge`, `button` (no `alert-dialog`).
- Do not add a second `<Toaster>` (already global in `(dashboard)/layout.tsx`).

## Open questions / risks
- Table density in the settings card — cap the visible rows (e.g. last 10) with the
  full list behind scroll, to keep the card compact.
