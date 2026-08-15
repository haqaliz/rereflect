# Aspect spec — Frontend write-back card

**Feature:** `intercom-writeback` (prd.md R9) · **Aspect:** `frontend-writeback-card`

## Problem slice

Operators need to see and control the write-back where they already manage the
Intercom connection: Settings → Integrations → Intercom. Today that page
(`services/frontend-web/app/(dashboard)/settings/integrations/intercom/page.tsx`, 433
lines) has a Connection card (:167-235), an optional webhook card (:237-286), and a
Disconnect card — no write-back surface. `lib/api/intercom.ts` exposes only
connect/getStatus/disconnect and its status type carries no writeback fields
(`intercom.ts:13-14` even notes "Intercom is inbound-only").

## In-scope

- Extend the `IntercomConnectionStatus` type (`lib/api/intercom.ts`) with
  `writeback_enabled`, `writeback_action`, `last_writeback_at`, `last_writeback_status`,
  `last_writeback_error` (mirroring `hubspot.ts:17-23`).
- Add `updateWriteback(enabled, action)` → PATCH `/writeback` and
  `testWriteback()` → POST `/writeback/test` to `lib/api/intercom.ts`
  (hubspot.ts:166-183 precedent).
- New `components/settings/IntercomWritebackCard.tsx` in the HubSpotWritebackCard style
  (238 lines precedent: never-optimistic — PATCH → refetch → `onStatusChange`; Switch +
  action selector (`note_and_close` | `note_only` radio/select) + status grid +
  destructive error line for `last_writeback_error`; renders `null` when
  `!status.connected`).
- Honest copy (the "Two-Way Sync" discipline, prd.md R9): the card states what it does —
  "on resolve, adds a note and closes the conversation"; that it is **off by default**;
  that it requires `conversation:write` scope on the Intercom app (and that a missing
  scope shows as `missing_write_scope` here, it does not disable the integration); that
  it applies to resolutions **after** enabling only.
- Mount in `intercom/page.tsx` between the Connection card and the webhook card, gated
  `status?.connected && isAdminOrOwner` (page already computes `isAdminOrOwner` per the
  HubSpot mount precedent at `hubspot/page.tsx:401-404`).
- Add the `Test write-back` button wired to `testWriteback()` with a result toast
  (S1) — disabled while a test is in flight.
- Vitest tests for the card (toggle round-trip, never-optimistic revert on failure,
  action change, test-button states) following the existing settings-card test
  patterns in `app/(dashboard)/settings/integrations/*/__tests__/`.

## Out of scope

- Integrations-index tile surfacing (writeback-ui/spec.md:40 precedent: HubSpot doesn't
  do it either).
- Landing page / README copy (docs-tracking-changelog aspect + prd.md OQ3).
- Any change to the Connection/webhook/Disconnect cards.

## Acceptance criteria (testable)

1. Card renders only when `status.connected` (and admin/owner); shows the five writeback
   fields.
2. Toggling PATCHes, refetches, and reverts optimistically-changed UI on failure
   (tests).
3. Action change round-trips (PATCH `{action}`) and the selector reflects the server
   value.
4. Test button shows `{ok}` / reason copy from `/writeback/test` without erroring when
   the endpoint returns `{ok: false}`.
5. `lib/api/intercom.ts` types compile under strict mode; `pnpm lint` + `pnpm test`
   green in frontend-web.

## Dependencies & sequencing

- Needs `config-api-routes` (PATCH/test routes + extended status) and its model columns.
- After `db-config-model` + `config-api-routes`.

## Open questions / risks

- Action selector UI: radio pair vs select — follow the smallest shadcn pattern already
  used in the repo (check the CRM writeback cards / status-sync cards for a precedent).
- Whether `last_writeback_error` rendering uses the CRM `REASON_COPY` map pattern
  (HubSpotWritebackCard.tsx:17-30) — yes, mirror it with write-back-specific reasons
  (`missing_write_scope`, `no_admin`, `missing_encryption_key`).
