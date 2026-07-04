# Aspect Spec — writeback-ui

**Feature:** `salesforce-crm-writeback` · **Aspect:** `writeback-ui` · **Deps:** `writeback-config-api`

## Problem slice / outcome

An admin/owner can enable, configure, and validate Salesforce writeback and see its status from the
Salesforce integration settings page — mirroring the shipped HubSpot writeback card.

## In-scope

1. **`services/frontend-web/lib/api/salesforce.ts`** —
   - Extend `SalesforceConnectionStatus` with the 6 writeback fields (mirror `hubspot.ts:17-24`):
     `writeback_enabled`, `writeback_field_name`, `last_writeback_at`, `last_writeback_status`,
     `last_writeback_error`, `contacts_written`.
   - Add `updateWriteback({enabled, field_name})` → `PATCH /api/v1/integrations/salesforce/writeback`.
   - Add `testWriteback(field_name)` → `POST /api/v1/integrations/salesforce/writeback/test`
     → `{ok, reason}`.
   - Add the 3 supporting interfaces (config/response/test-response), mirroring `hubspot.ts:43-60`.
2. **`services/frontend-web/components/settings/SalesforceWritebackCard.tsx` (new)** — mirror
   `HubSpotWritebackCard.tsx` (238 lines):
   - Props `{status: SalesforceConnectionStatus, onStatusChange}`; render `null` when
     `!status.connected`.
   - Switch(enable) → validate non-empty field on enable → `salesforceAPI.updateWriteback(...)` →
     refetch `getStatus()` → `onStatusChange` (never optimistic).
   - Field Input default `Rereflect_Health_Score__c`; locked once `writeback_enabled`.
   - Validate button → `testWriteback` → `{ok, reason}` panel.
   - Status grid: `last_writeback_at`, `last_writeback_status` (via a `STATUS_COPY` map),
     `contacts_written`; destructive alert for `last_writeback_error`.
   - `REASON_COPY` / `STATUS_COPY` friendly maps adapted to Salesforce wording (`field_not_found`,
     `missing_write_scope`, `wrong_type`, `ambiguous_contact`, `deferred: daily_limit`, ...).
   - Use CSS variables / shadcn primitives only — no hardcoded colors.
3. **`services/frontend-web/app/(dashboard)/settings/integrations/salesforce/page.tsx`** — import and
   render `<SalesforceWritebackCard status={status} onStatusChange={setStatus} />` between the
   connection Card (~`:368`) and the Help Card (~`:371`), gated `status?.connected && isAdminOrOwner`
   (mirror HubSpot page `:400-403`).

## Out-of-scope

- Integrations-index tile writeback surfacing (HubSpot doesn't do it either — no change).
- Any backend change.

## Acceptance criteria (testable)

- `components/settings/__tests__/SalesforceWritebackCard.test.tsx` (new, mirror the HubSpot card test):
  renders null when disconnected; enable path calls `updateWriteback` then refetches; validate path
  shows ok/reason; status grid + error alert render from status fields; field locked when enabled.
- `lib/api/__tests__/salesforce.test.ts` (extend): `updateWriteback` / `testWriteback` hit the correct
  URLs with the right bodies.
- `npm run test` and `npm run lint` green.

## Dependencies / sequencing

Last aspect; consumes the config-api contracts. Can be built against the documented endpoint shapes in
parallel with backend once contracts are frozen, but validated end-to-end only after config-api lands.

## Open questions / risks

- `SalesforceConnectionStatus` currently has no writeback fields (dig confirmed) — extend the type in
  one place so it flows through the settings page + tile automatically.
