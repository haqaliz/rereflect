# Aspect: writeback-ui (frontend)

**Slice of:** crm-writeback PRD · **Service:** `services/frontend-web`
**Depends on:** writeback-config-api (PATCH `/writeback` + extended `/status`).

## Problem slice / outcome

Let an admin/owner turn writeback on/off, set the custom-field name, run a validation check, and
see writeback status — all on the existing HubSpot detail page, mirroring the ARR-property +
sync-status patterns already there.

## In scope

- **`lib/api/hubspot.ts`:** add `updateWriteback({ enabled, field_name })` → `PATCH /api/v1/integrations/hubspot/writeback`; (S1) `testWriteback()` → `POST /writeback/test`. Extend `HubSpotConnectionStatus` with the new writeback config + status fields.
- **`app/(dashboard)/settings/integrations/hubspot/page.tsx`** (connected state): a "Health-score writeback" card with
  - a `Switch` (opt-in) mirroring `components/settings/AISettingsGeneral.tsx`;
  - a field-name input (default suggestion `rereflect_health_score`), disabled unless enabling — mirrors the existing ARR-property input;
  - a **Validate/Test** button + result panel mirroring the existing Test-connection panel;
  - a status row (`last_writeback_at`, `last_writeback_status`, `contacts_written`) + a `last_writeback_error` Alert when present (mirror the existing `last_error` alert).
- Enabling with an empty/invalid field surfaces the backend 4xx message inline; the toggle does not visually latch on until the PATCH succeeds.
- Admin/owner gating already enforced by the page.

## Out of scope

- Salesforce UI; any customer-profile UI; a global integrations-index writeback widget (detail page only for slice 1).

## Acceptance criteria (testable)

- Toggling on with a valid field calls `updateWriteback` and reflects enabled state from the refetched status.
- Toggling on with no/invalid field shows the backend error and leaves the switch off.
- Status/error fields render from `/status`; no writeback UI shows when HubSpot is disconnected.
- Lint + type-check clean; matches existing card/Switch/Alert styling (no hardcoded colors).

## Notes

Persistence pattern mirrors `aiSettingsAPI.update()` PATCH; shared axios (`lib/api-client.ts`) injects auth.
