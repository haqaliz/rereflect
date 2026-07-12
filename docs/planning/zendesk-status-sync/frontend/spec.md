# Aspect: frontend

**Slug:** `zendesk-status-sync` · **Aspect dir:** `frontend`
**Sequencing:** last — after backend-routes (consumes endpoints + response shape).

## Problem slice & outcome

Admin/owner UI to control Zendesk status-sync on the Zendesk settings page: a toggle, a last-synced/
error indicator, and a "Sync Now" button — a direct clone of `JiraStatusSyncCard`.

## In scope
1. New component `services/frontend-web/components/settings/ZendeskStatusSyncCard.tsx` — clone of
   `JiraStatusSyncCard.tsx`:
   - Props `{status: ZendeskConnectionStatus, onStatusChange}`; renders null if `!status.connected`.
   - Toggle: optimistic flip → `patchZendeskStatusSync(checked)`; revert + `toast.error` on failure.
   - "Sync Now": `triggerZendeskStatusSync()` → `toast.success`; 502 → "background worker unavailable" message.
   - Indicator: `Last synced {timeAgo(last_status_synced_at) || 'Never'}`; error line when `last_status_sync_error`.
2. `services/frontend-web/lib/api/zendesk.ts`:
   - Extend `ZendeskConnectionStatus` type: `status_sync_enabled: boolean`, `status_mapping: Record<string,string>|null`, `last_status_synced_at: string|null`, `last_status_sync_error: string|null`.
   - Add `patchZendeskStatusSync(enabled, statusMapping?)` → `PATCH /api/v1/integrations/zendesk/status-sync`.
   - Add `triggerZendeskStatusSync()` → `POST /api/v1/integrations/zendesk/status-sync/sync`.
3. Mount `<ZendeskStatusSyncCard>` on `app/(dashboard)/settings/integrations/zendesk/page.tsx`, gated
   `{status?.connected && isAdminOrOwner && (...)}` (mirror jira/page.tsx:409-412); seed the new fields in `handleConnect`'s `setStatus`.
4. Keep the EXISTING ingestion "Sync Now" (`triggerSync`) intact; label the two distinctly
   ("Sync tickets" for ingestion vs the status-sync card's "Sync Now").

## Out of scope
- A rich per-status mapping editor (defaults + JSON override ship server-side; UI editor is v2). The toggle sends `enabled` only; mapping override is API-only for now.
- Any backend change.

## Acceptance criteria (testable, Vitest + RTL, mirror `JiraStatusSyncCard.test.tsx`)
- Renders null when `connected=false`.
- Switch reflects `status_sync_enabled`; toggling calls `patchZendeskStatusSync(true)`; on rejection reverts + shows toast.
- "Last synced Never" when null; relative `timeAgo` label otherwise.
- `last_status_sync_error` line shown only when present.
- "Sync Now" → success toast on 202; 502 → worker-unavailable toast.
- API-client tests (mirror `jira.test.ts:155-194`): `patchZendeskStatusSync` PATCHes the right URL with `{enabled, status_mapping?}`; `triggerZendeskStatusSync` POSTs the status-sync path.
- `npm run lint` clean; page test fixtures updated with the 4 new fields; existing ingestion Sync-now test still passes.

## Dependencies & sequencing
- Needs: backend-routes (endpoints + `GET /status` fields). Last aspect.

## Open questions / risks
- Distinguish the two "sync" buttons clearly so operators don't confuse ticket-ingestion with status-sync.
