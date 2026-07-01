# Aspect Spec — salesforce-frontend

**PRD:** `../prd.md` · **Build order: aspect 4 of 4 (last).** No DB. Consumes aspect-2 endpoints. Buildable vs mocks.

## Problem slice & outcome
An admin/owner discovers, connects (via OAuth redirect), and manages Salesforce from Settings → Integrations, and sees which CRM populated the Customer 360 card.

## In scope
- **API client** `services/frontend-web/lib/api/salesforce.ts`: types (`SalesforceConnectionStatus` with `connected, instance_url, sf_org_id, last_synced_at, last_sync_status, last_error, contacts_synced, contacts_matched, connected_at`) + `salesforceAPI`: `getConnectUrl()` (→ `{auth_url}`, mirror `linear.ts:97-99,122-125`), `getStatus()`, `disconnect()`, `test()`. **No `connect(token)`** — OAuth redirect.
- **Integrations index** `app/(dashboard)/settings/integrations/page.tsx`: add `salesforceStatus` state + fetch in the `Promise.allSettled` block; Active tile (mirror HubSpot 376-431) + Available tile (mirror 644-669), Salesforce-blue brand (`#00A1E0`), routing to `/settings/integrations/salesforce`. Reuse the existing generic `oauth_error` banner.
- **Connect/detail page** `app/(dashboard)/settings/integrations/salesforce/page.tsx`: RBAC member-redirect guard (mirror `hubspot/page.tsx:57,60-64`); **disconnected state = OAuth CTA** ("Connect with Salesforce" → `salesforceAPI.getConnectUrl()` → `window.location.href = auth_url`, mirror `linear/page.tsx:339-350`); connected-state grid (instance_url, sf_org_id, connected_at, last_synced_at, contacts_synced/matched) + Test / Disconnect (mirror HubSpot page + confirm dialog). Handle `?connected=1` / `?oauth_error=` return params.
- **Copy fix** `components/customers/CrmCompanyCard.tsx:50`: provider-neutral empty state ("Connect a CRM (HubSpot or Salesforce) in Settings…").

## Should-have
- `components/icons/SalesforceIcon.tsx` (mirror `LinearIcon.tsx`) instead of a monogram.
- `crm_provider` badge on `CrmCompanyCard` when present.
- `docs/SELF_HOSTING.md` Salesforce section (Connected App setup, scopes, redirect URI, verify note).

## Out of scope
- Backend endpoints (aspect 2).
- Renaming HubSpot UI.

## Acceptance criteria (testable, Vitest)
1. `salesforceAPI` methods hit the right paths (mocked axios); `getConnectUrl` returns `auth_url`.
2. Integrations index renders a Salesforce tile (available when disconnected, active when connected) via mocked status.
3. Connect page: members are redirected; disconnected state shows the OAuth CTA (not a token form); clicking it navigates to `auth_url`; connected state shows the stats grid + Test/Disconnect.
4. `CrmCompanyCard` empty state no longer says "Connect HubSpot"; renders provider badge when `crm_provider` present.
5. `npm run test` + `npm run lint` + `npm run build` clean.

## Dependencies & sequencing
- After `salesforce-connection` (endpoints), but buildable against mocked responses in parallel; integrate last.
- Update existing integration-page tests/snapshots intentionally (new tile).

## Risks
- OAuth redirect return-param handling (`connected` / `oauth_error`) — reuse existing generic handling.
- Never hardcode colors (CSS vars); strict TS; wrap `useSearchParams` in Suspense if used.
