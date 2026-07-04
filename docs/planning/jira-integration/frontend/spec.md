# Aspect Spec — frontend

**Parent PRD:** `../prd.md` · **Aspect dir:** `frontend/`
**Depends on:** `backend-connection`, `backend-create-issue`, `source-type-registration`

## Problem slice & outcome

The operator- and user-facing surface in the dashboard app: connect Jira from Settings, create a Jira
issue from a feedback item, and see Jira as a source option. Outcome: token-paste connect works,
create-issue wizard files a Jira issue and links back, integrations index shows accurate Jira status.

## In scope (`services/frontend-web`)

- **API client** `lib/api/jira.ts` (mirror `lib/api/linear.ts` but token-paste, not `getConnectUrl`):
  types (`JiraConnectionStatus`, `JiraProject`, `JiraIssueType`, `CreateJiraIssueRequest/Response`,
  `JiraLinkedIssue`) + `jiraAPI`: `connect({site_url, email, api_token})`, `getStatus`, `disconnect`,
  `testConnection`, `getProjects`, `getIssueTypes(project_id)`, `createIssue`, `getLinkedIssues(feedback_id)`.
- **Icon** `components/icons/JiraIcon.tsx`.
- **Settings detail page** `app/(dashboard)/settings/integrations/jira/page.tsx` (mirror the HubSpot
  page, NOT Linear's OAuth page): member→preferences redirect; RBAC `isAdminOrOwner`;
  **not-connected** = token-paste form (site URL input, email input, password-type API-token input with
  show/hide, connect-error alert, Connect button); **connected** = status grid (site, email, token
  hint, connected-at, last-synced/last-error) + Test + Disconnect (confirm dialog).
- **Integrations index** `app/(dashboard)/settings/integrations/page.tsx`: add a Jira tile + fetch
  `jiraAPI.getStatus()` in the existing `Promise.allSettled` block; link to `/settings/integrations/jira`.
- **Create-issue wizard** `app/(dashboard)/feedbacks/[id]/create-issue/page.tsx`:
  - Activate the existing static **"JIRA – Coming soon"** tile (~L298-312) into a selectable card
    gated on `jiraAPI.getStatus()` (`connected && is_active`).
  - Add a Jira configure sub-form: project select (`getProjects`) → issue-type select
    (`getIssueTypes` on project change) → summary + description; submit → `jiraAPI.createIssue`;
    handle the `warning:"duplicate"` 200 (offer "create anyway" = `force`); handle stale-token 4xx
    with a "reconnect Jira" message.
  - `done` step shows the issue key + "Open in Jira" (browse URL).
- **Source wizard entries** (mirror `linear` special-casing) across
  `app/(dashboard)/feedback-sources/{new,page,[id],pending}.tsx`: add `jira` to the `SOURCE_ICONS` /
  `SOURCE_COLORS` maps and the own-auth connection-check branch (uses `jiraAPI.getStatus()` instead of
  picking an `integration_id`, exactly like Linear).

## Out of scope (this aspect)

- Landing/marketing page (→ `landing`).
- Mapping-config UI (v2).

## Acceptance criteria (testable)

- `npm run test` green: unit tests for `lib/api/jira.ts` shape and any wizard branch logic that has a
  testable pure function (mirror existing Linear/HubSpot frontend tests where present).
- `npm run lint` clean (ESLint v9 flat config already in repo).
- Manual/there-exists: connect form posts to `/api/v1/integrations/jira/connect`; create-issue wizard
  Jira branch calls `createIssue` and renders the browse URL; integrations index reflects connected state.

## Dependencies & sequencing

Last of the product-app aspects — needs all three backend aspects' endpoints. Can develop against the
finalized route contracts in the specs even before backend merges, but tests/verify need the backend.

## Open questions / risks

- Keep the description field plain-text in the UI; ADF wrapping happens server-side (do not build ADF
  in the frontend).
- Match the repo's existing frontend test coverage depth for integrations (Linear/HubSpot pages have
  limited unit tests — don't over-invest; lint + a client-shape test + the pure wizard helpers).
