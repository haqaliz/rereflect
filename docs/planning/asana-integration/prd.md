# PRD — Asana Integration (slice 1)

**Slug:** `asana-integration` · **Branch:** `feat/asana-integration` · **Date:** 2026-07-06
**Status:** Approved scope, pending PRD review gate
**Author:** rereflect-begin-fast pipeline (freeform task from `rereflect-next`)

## Problem Statement

Rereflect turns customer feedback into insight, but acting on that insight means creating work items in whatever tool a team already runs on. Rereflect can already push feedback into **Jira** and **Linear**; **Asana** — one of the most widely used work-management tools among the PM/CS personas Rereflect targets — is the only named integration in the backlog that is entirely unbuilt (`DEV-TRACKING.md:185,199-203`, M3.3).

For an Asana-first team today, the loop breaks at the last step: they read a pain point or feature request in Rereflect, then re-type it by hand into Asana. This PRD closes that gap with the same one-click "create work item from feedback" action Jira/Linear already provide.

**Evidence it's real:** the moat is product breadth + the integration layer (`AI-TRACKING.md` strategic decisions; `rereflect-next` ranking). Five integrations already shipped on one proven pattern, and the create-issue wizard already renders an Asana tile as a disabled "Coming soon" placeholder (`services/frontend-web/app/(dashboard)/feedbacks/[id]/create-issue/page.tsx`) — the product already promises this.

## Goals & Success Metrics

**Goal:** An operator can connect their Asana workspace with a Personal Access Token and create an Asana task from any feedback item in one action, without leaving Rereflect.

**Success criteria (testable):**
- A self-hoster pastes an Asana PAT in Settings → Integrations → Asana and sees a connected state (workspace/user resolved) with no plaintext token stored.
- From a feedback item, a user selects Asana → workspace → project and creates a task; the created task appears in Asana with the feedback content, and a link + timeline event are persisted in Rereflect.
- Creating a task twice for the same feedback is prevented unless the user forces it.
- `asana` appears as a selectable source type (parity), and the landing page lists Asana as available.
- Full test coverage mirroring the Jira suite (models, client, connection, tasks, source-type), green.

**Non-metrics (honesty):** no accuracy/volume claims — this is a plumbing feature, measured by "the action works end to end," not by an analytics number.

## User Personas & Scenarios

- **CS manager / PM (Asana team):** reads a churn-risk or feature-request feedback item, clicks Actions → Create Issue → Asana, picks their team's project, and the task lands in their sprint board with the feedback text and a back-link.
- **Operator / admin (self-hoster):** mints an Asana PAT, pastes it into Settings → Integrations, tests the connection, and manages (test/disconnect) it later. Admin/owner-gated.

## Requirements

### Must-have
1. **PAT connect flow** (`asana` own-auth integration): connect / status / disconnect / test endpoints. PAT encrypted at rest (Fernet, reuse `encrypt_api_key`); response never returns the token; store a `token_hint`. One integration per org (unique constraint). Admin/owner-gated.
2. **Asana API client** (`AsanaClient`): fixed host `https://app.asana.com/api/1.0`, **Bearer PAT** auth, timeout, no redirects, token never logged (repr/str omit it). Error taxonomy: `AsanaError` / `AsanaAuthError` (401/403) / `AsanaTransientError` (429, 5xx) / `AsanaNotFoundError` (404). Methods: `validate()` (`GET /users/me`), `get_workspaces()`, `get_projects(workspace_gid)`, `create_task(...)` (`POST /tasks`).
3. **Create task from feedback** (`POST /api/v1/integrations/asana/tasks`): verify feedback belongs to org (404 else); duplicate guard on `(organization_id, feedback_id)` → return 200 `{warning:"duplicate", existing_tasks:[...]}` unless `force=true`; build `{name, notes, projects:[gid], workspace}` (name trimmed to Asana's limit, plain-text notes — no ADF); persist a `FeedbackAsanaTask` link + an `asana_task_created` timeline event (`FeedbackWorkflowEvent`); on `AsanaAuthError` set `last_error`/`last_sync_status` and return 403.
4. **Metadata endpoints for the wizard:** `GET /workspaces`, `GET /projects?workspace_gid=`, `GET /tasks?feedback_id=` (linked tasks).
5. **Source-type registration:** add `asana` `SourceTypeInfo` (`requires_integration=False`, `available=True`) to `list_source_types()` and `"asana"` to `valid_types` in `create_feedback_source` (`services/backend-api/src/api/routes/feedback_sources.py`). Backend-only parity, **no** worker adapter (matches Jira).
6. **Frontend — connect page:** `settings/integrations/asana/page.tsx` with a **single PAT field** (show/hide), connect/test/disconnect (confirm dialog), connected-details grid, "how to get your PAT" help card. Admin/owner-gated redirect.
7. **Frontend — integrations index:** Asana status state + fetch, connected card (Test/Disconnect), available tile (when not connected), empty-state guard update; `AsanaIcon` (brand `#F06A6A`).
8. **Frontend — create-task wizard:** activate the existing "Coming soon" Asana tile in `create-issue/page.tsx`; **Workspace picker → Project picker** (no issue-type); submit with duplicate / "Create anyway" handling and a "Reconnect Asana" affordance on 403; done branch. New `lib/api/asana.ts` + `lib/asanaIssueWizard.ts`.
9. **Landing + docs:** `landing-web/lib/integrations.ts` `asana` entry (`status:'available'`) + `app/integrations/asana/page.tsx` + landing `AsanaIcon` + the two landing icon maps; "Connecting Asana" section in `docs/SELF_HOSTING.md`.
10. **Tests** across all of the above, mirroring the Jira suite (`unittest.mock` patching `httpx.Client` / route-level `AsanaClient`; Vitest `vi.mock('@/lib/api-client')`).

### Should-have
- Consistent error copy via an `asanaIssueWizard` helper (403 = reconnect, 422 = rejected), mirroring `jiraIssueWizard`.
- Alembic migration authored to chain from the current Zendesk head (see Risks).

### Nice-to-have (not required for slice 1)
- Surfacing the created task's `permalink_url` inline on the feedback detail (a "Linked tasks" card already exists for Jira — reuse if cheap).

## Technical Considerations

- **Services changed:** `backend-api` (all core logic), `frontend-web` (UI + client), `landing-web` (marketing) + `docs`. **`worker-service` and `analysis-engine`: no change** — the Jira create-task precedent has zero worker footprint (synchronous backend route; no adapter, mirror model, Celery task, or beat entry).
- **Multi-tenancy:** every row and query scoped by `organization_id`; connect is upsert-by-org; `FeedbackAsanaTask` carries `organization_id`.
- **Security:** PAT Fernet-encrypted; `LLM_ENCRYPTION_KEY` unset → 422 not 500 (the Jira "R6 safeguard"). Fixed Asana host removes the per-org-subdomain SSRF surface Jira/Zendesk needed — the client still asserts constant scheme/host, but there is **no DNS/private-IP gate** to build.
- **Reuse as-is:** `src/utils/encryption.py`, `require_admin_or_owner` / org dependencies, `FeedbackWorkflowEvent` timeline, the create-issue wizard shell, the integrations-index and connect-page shells.

### Data Model
- `AsanaIntegration` (`asana_integrations`): `organization_id` (FK, unique `uq_asana_integrations_org_id`), `api_token` (encrypted Text), `token_hint`, `account_gid`, `display_name`, `is_active`, `connected_by_user_id`, `connected_at`, `last_synced_at`, `last_sync_status`, `last_error`, timestamps. **No `site_url`, no `email`** (Bearer, fixed host).
- `FeedbackAsanaTask` (`feedback_asana_tasks`): `organization_id`, `feedback_id` (FK), `asana_task_gid`, `asana_task_url`, `asana_task_name`, `created_by_user_id`, `created_at`; indexes on org_id + feedback_id.
- Register both in `src/models/__init__.py`.

### API Contracts (prefix `/api/v1/integrations/asana`)
`POST /connect` `{api_token}` → metadata only · `GET /status` · `DELETE /disconnect` (soft) · `POST /test` (never 500) · `GET /workspaces` · `GET /projects?workspace_gid=` · `POST /tasks` `{feedback_id, workspace_gid, project_gid, name, notes?, force?}` · `GET /tasks?feedback_id=`.

## Risks & Open Questions

- **Alembic multiple heads (pre-existing).** `master` has **6 alembic heads**; each recent integration migration just added another head without linearizing (Zendesk's `z1a2b3c4d5e6` did the same). **Decision:** follow precedent — chain the Asana migration from the Zendesk head `z1a2b3c4d5e6`. Note honestly in the migration that a real `alembic upgrade head` across the repo needs `alembic merge heads`; that cleanup is **out of scope** for this slice (it's a repo-wide condition, not caused here).
- **Asana field/endpoint drift.** `GET /users/me`, `GET /workspaces`, `GET /projects?workspace=`, `POST /tasks` shapes are assumed from Asana API v1; the client is unit-tested against mocked responses, so a shape mismatch surfaces as a test/contract fix, not a silent failure.
- **Duplicate key.** Confirmed: key on `(organization_id, feedback_id)`, not task content — mirrors Jira.
- **Rate limits.** Asana enforces per-token rate limits; `AsanaTransientError` (429) is surfaced as retryable/502 at the route, not retried in-process (matches Jira).
- **Team-scoped projects (usability limit — NEEDS A DECISION).** Asana's hierarchy is workspace → team → project; `GET /projects?workspace=` returns workspace-visible projects and may **omit team-scoped projects**, and the list can be large with no search. If a user's target project isn't in the picker, the feature silently fails for them. **Decision (confirmed 2026-07-06):** accept the limitation, ship the flat workspace→project picker, and document it in SELF_HOSTING; a team selector / project search is a v2 follow-up.
- **`permalink_url`.** Asana omits it from the `POST /tasks` response unless requested — the client must pass `opt_fields=permalink_url` (with a `GET /tasks/{gid}` fallback), asserted by a test, so the "view in Asana" link never breaks.

## Out of Scope (deferred to v2 — same shape Jira used)
- OAuth 2.0 (PAT only).
- **Inbound** Asana-tasks-as-feedback ingestion (worker adapter, mirror model, Celery poll, feedback-source wizard pages).
- Status-sync back to Rereflect (webhooks/polling).
- AI-drafted task content.
- Section / assignee / due-date / custom-field mapping; multiple workspaces or projects config per org.
- Repo-wide Alembic head linearization.
