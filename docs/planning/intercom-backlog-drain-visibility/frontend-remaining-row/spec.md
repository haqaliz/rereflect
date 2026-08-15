# Aspect spec — Frontend "≈ N remaining" row

**Feature:** `intercom-backlog-drain-visibility` (prd.md R5) · **Aspect:** `frontend-remaining-row`

## Problem slice

The Connection card on the Intercom settings page must render the drain estimate
honestly — only when it exists and is positive — without contradicting the existing
"never backfills history" alert copy.

## In-scope

- `IntercomConnectionStatus` (services/frontend-web/lib/api/intercom.ts:18-43) gains
  `backlog_remaining: number | null` (after `feedback_items_ingested` :34, mirroring
  the writeback fields' six-layer pattern).
- Connection card (app/(dashboard)/settings/integrations/intercom/page.tsx:168-236):
  a row after "Feedback ingested" (:199-202) rendering **"≈ N conversations left to
  sync"** when `backlog_remaining` is non-null AND > 0, with the estimate qualifier
  ("estimate — drains over runs"). No row when null, 0, disconnected, or OAuth
  (backlog_remaining stays null for those by construction).
- Reconcile the connected-but-zero "never backfills history" alert copy (:212-224) so
  it doesn't contradict the drain estimate (the first sync DOES drain the
  since-connect window; "never backfills" refers to pre-connect history — tighten the
  wording).
- Tests: IntercomPage.test.tsx — render when > 0 (mirror the ingested-count test
  :224-230), no row when null / 0 / disconnected; fixtures CONNECTED + DISCONNECTED
  gain the field; writeback-card tests' fixtures if they construct status objects.

## Out of scope

- Backend/worker (other aspects); "N of M" display (PRD N1); anything beyond the
  settings page.

## Acceptance criteria (testable)

1. Type compiles strict-mode; fixtures updated; row renders only for non-null > 0.
2. Card copy includes the estimate qualifier; the zero-ingested alert copy no longer
   contradicts the estimate.
3. `pnpm test` + `pnpm lint` green (frontend-web).

## Dependencies & sequencing

- After `db-status-api` (the API field must exist).

## Open questions / risks

- Wording: "≈ N conversations left to sync (estimate, drains over runs)" — match the
  card's existing tone; the PRD's honest-limits language is the source.
