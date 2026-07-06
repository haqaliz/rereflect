# Aspect: frontend

**Slice of:** Asana Integration slice 1. **Owner:** one frontend engineer/agent. **Depends on:** backend-connection + backend-create-task (API contracts).

## Problem slice & outcome
In-app: an admin connects Asana with a PAT, sees it on the Integrations page, and any user creates an Asana task from a feedback item via the create-issue wizard. Mirror the Jira frontend; Asana specifics = **PAT-only connect** (fixed host, no site URL/email) and **Workspace → Project pickers** (no issue-type).

## In scope
**New files (`services/frontend-web/`):**
- `lib/api/asana.ts` — types (`AsanaConnectionStatus`, `AsanaConnectRequest{api_token}`, `AsanaWorkspace`, `AsanaProject`, `CreateAsanaTaskRequest{feedback_id,workspace_gid,project_gid,name,notes?,force?}`, `CreateAsanaTaskResponse` w/ `warning?`/`existing_tasks?`, `AsanaLinkedTask`) + `asanaAPI` object: `connect`, `getStatus`, `disconnect`, `testConnection`, `getWorkspaces`, `getProjects(workspaceGid)`, `createTask`, `getLinkedTasks(feedbackId)` against `/api/v1/integrations/asana/*`. Uses the shared `apiClient` (global auth).
- `lib/asanaIssueWizard.ts` — `isDuplicateAsanaResponse`, `getAsanaCreateTaskErrorMessage(status, detail)` (403=reconnect, 422=rejected), `isStaleAsanaTokenStatus`.
- `components/icons/AsanaIcon.tsx` — brand `#F06A6A`.
- `app/(dashboard)/settings/integrations/asana/page.tsx` — admin/owner-gated; **single PAT field** (show/hide); connect/test/disconnect (confirm dialog); connected-details grid (token_hint/display_name/connected_at); "how to get your PAT" help card. Mirror the Jira/Zendesk connect page.
- Tests: `lib/api/__tests__/asana.test.ts` (`vi.mock('@/lib/api-client')`, assert URL+payload per method), `lib/__tests__/asanaIssueWizard.test.ts`.

**Edit files:**
- `app/(dashboard)/settings/integrations/page.tsx` — import `asanaAPI` + `AsanaIcon`; `asanaStatus` state + fetch in the `Promise.allSettled`; connected card (Test/Configure/Disconnect); available tile (when `!asanaStatus?.connected`, links to `/settings/integrations/asana`); add `!(asanaStatus?.connected)` to the empty-state guard.
- `app/(dashboard)/feedbacks/[id]/create-issue/page.tsx` — load `asanaAPI.getStatus`; add `asana` to `SelectedIntegration`; convert the existing disabled "Coming soon" Asana tile → live `handleSelectAsana`; `asanaForm{workspaceGid,projectGid,name,notes}`; effects: load `getWorkspaces()`, then `getProjects(workspaceGid)` on workspace change; **Workspace picker → Project picker (no issue-type)**; `handleAsanaSubmit(force)` with duplicate/"Create anyway" + "Reconnect Asana" on 403; done branch. **Auth errors on the metadata calls too:** a revoked/stale PAT during `getWorkspaces()`/`getProjects()` (401/403) shows the same "Reconnect Asana" affordance, not a raw error.

## Out of scope
- The Linear-only `components/integrations/CreateIssueDialog.tsx` modal (leave its Asana "Coming soon" tile; the Actions dropdown uses the page wizard).
- Inbound feedback-source wizard pages + `TRIGGER_OPTIONS.asana` (outbound-only slice).
- Landing/docs (→ landing aspect).

## Acceptance criteria (testable)
- `asana.test.ts`: each `asanaAPI.*` method calls the correct URL with the correct payload; connect sends only `{api_token}`.
- `asanaIssueWizard.test.ts`: duplicate detection + error-message mapping (403/422) + stale-token detection.
- Manual/QA: connect a PAT → connected card shows; create-issue wizard → Asana tile active → Workspace/Project pickers populate → submit creates a task; duplicate shows "Create anyway"; 403 shows Reconnect.

## Dependencies & sequencing
Last (needs the backend endpoints). API client + connect page can start against the contract once backend-connection lands; the wizard branch needs backend-create-task.

## Open questions / risks
- Workspace/project lists can be large — the Jira `Select` pattern is fine for slice 1 (no search/pagination); note as a possible follow-up.
