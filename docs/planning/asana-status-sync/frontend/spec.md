# Aspect: frontend

## Problem slice & outcome
Give operators the status-sync toggle, last-synced/error indicator, and "Sync now" button on the Asana
settings detail page — a line-for-line parity of the Jira card.

## In scope (`services/frontend-web`)
- **`components/settings/AsanaStatusSyncCard.tsx`** — copy of `components/settings/JiraStatusSyncCard.tsx`
  with `jira → asana` renames. Props `{ status: AsanaConnectionStatus; onStatusChange }`. Reads
  `status_sync_enabled`, `last_status_synced_at`, `last_sync_status`, `last_error`. Optimistic toggle
  with revert-on-error; "Sync now" special-cases HTTP 502 → "background worker unavailable". Reuses
  shared primitives (`Switch`, `Button`, `Card*`, `toast` from sonner, `Loader2`/`RefreshCw`, `timeAgo`).
- **`lib/api/asana.ts`**:
  - Add `patchAsanaStatusSync(enabled, statusMapping?)` → `PATCH /api/v1/integrations/asana/status-sync`.
  - Add `triggerAsanaSync()` → `POST /api/v1/integrations/asana/sync`.
  - Add `AsanaSyncTriggerResponse { status: string }`.
  - Extend `AsanaConnectionStatus` with `status_sync_enabled: boolean` and
    `last_status_synced_at: string | null`.
- **`app/(dashboard)/settings/integrations/asana/page.tsx`**:
  - Render `{status?.connected && isAdminOrOwner && <AsanaStatusSyncCard status={status}
    onStatusChange={setStatus} />}` in the slot after the connection Card (~line 351), matching the Jira
    page.
  - Add `status_sync_enabled: false, last_status_synced_at: null` to the `handleConnect` status literal.
- The Integrations **list** page needs no change (matches Jira — sync UI lives only on the detail page).

## Out of scope
- Any mapping-editor UI (operators set mapping via API in slice 1; Jira has no mapping editor either —
  per-status-name editor is deferred there too).
- Backend routes (backend-routes aspect) — consumed here.

## Acceptance criteria (testable) — mirror `JiraStatusSyncCard.test.tsx` + `jira.test.ts`
- Card renders toggle reflecting `status_sync_enabled`; toggling calls `patchAsanaStatusSync` and lifts
  the new status up; error reverts + toasts.
- "Sync now" calls `triggerAsanaSync`, toasts success; 502 → worker-unavailable message.
- Shows "Never" when `last_status_synced_at` null, else `timeAgo`; shows `last_error` in red only when
  `last_sync_status === 'error'`.
- `npm run test` and `npm run lint` green.

## Dependencies & sequencing
- Depends on **backend-routes** (final response/request shapes).
- Last UI aspect; no other aspect depends on it.

## Open questions / risks
- Keep the card visually identical to Jira's for consistency; no new design.
