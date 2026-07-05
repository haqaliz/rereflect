# Aspect: frontend

**Slice:** The operator connects Zendesk and creates a `zendesk` feedback source entirely in the
Next.js app, matching the Jira token-paste UX.

## In scope (all under `services/frontend-web/`)
- ADD `components/icons/ZendeskIcon.tsx` (mirror `JiraIcon.tsx`; `className` prop; brand `#03363D`).
- ADD `lib/api/zendesk.ts` (mirror `lib/api/jira.ts`): `ZendeskConnectionStatus`,
  `ZendeskConnect{Request,Response}`, `ZendeskDisconnectResponse`, `ZendeskTestResponse`, and
  `zendeskAPI.{connect,getStatus,disconnect,testConnection}` → `/api/v1/integrations/zendesk/*`.
  (No outbound createIssue/getProjects — inbound only.)
- ADD connect page `app/(dashboard)/settings/integrations/zendesk/page.tsx` (mirror Jira page):
  fields **subdomain / email / API token** (Eye toggle), connect/test/disconnect, connected view,
  admin gating + member redirect, webhook URL+secret display (from connect response).
- CHANGE `app/(dashboard)/settings/integrations/page.tsx`: import icon, `zendeskStatus` state,
  add to `Promise.allSettled` fetch, Active-integration block (mirror Jira l.699-822), Available
  tile (mirror l.981-1004), empty-state check.
- CHANGE the 4 feedback-source pages' `SOURCE_ICONS`/`SOURCE_COLORS` (+ imports):
  `new/`, list `page.tsx`, `[id]/`, `pending/`.
- CHANGE `app/(dashboard)/feedback-sources/new/page.tsx`: `zendesk` branch in
  `getInitialStep`/`handleTypeSelect`, status fetch+state, integration-step Zendesk connection
  card (→ `/settings/integrations/zendesk`), step-indicator/back special-cases, name placeholder.
- CHANGE `lib/api/feedback-sources.ts`: `TRIGGER_OPTIONS.zendesk` + add `'zendesk'` to the
  `source_type` union.

## Out of scope
- Backend endpoints (separate aspects); landing site (separate aspect); outbound issue creation.

## Acceptance criteria (mirror `lib/api/__tests__/jira.test.ts` + integrations contract test)
- `zendesk.test.ts`: each `zendeskAPI` method hits the correct `/api/v1/integrations/zendesk/*` URL.
- Integrations page contract test includes `zendeskAPI` (getStatus/connect/disconnect/testConnection).
- `npm run test` + `npm run lint` green.
- Manual: connect page renders subdomain/email/token, shows connected state + webhook secret.

## Dependencies / sequencing
- Depends on **backend-connection** endpoints existing (contract), but UI can be built in parallel
  against the known contract and integrated last.
