# Understanding — Asana Integration (slice 1)

**Slug:** `asana-integration` · **Branch:** `feat/asana-integration` · **Date:** 2026-07-06

## What this is really asking

Add Asana as the next integration, mirroring the **Jira** precedent, which is the closest match: an **own-auth, outbound** integration whose core action is **create an Asana task from a feedback item**. Connect via a BYOK **Personal Access Token (PAT)**, not OAuth. All features unlocked (OSS self-hosted).

## Affected services

| Service | Change? | Why |
|---|---|---|
| **backend-api** | **YES — all the real work** | New model, client, routes, source-type registration, migration |
| **worker-service** | **NO** | Jira (the outbound precedent) has **zero** worker footprint — create-task runs synchronously in a backend route. No adapter, no mirror model, no Celery task, no beat entry. |
| **analysis-engine** | NO | Not involved |
| **frontend-web** | YES | API client, connect page, integrations index, create-task wizard branch |
| **landing-web** | YES | Integration registry entry + page + icon + docs |

## The create-task flow (mirrors Jira exactly)

`POST /api/v1/integrations/asana/tasks` in a backend route: verify feedback ownership (404) → duplicate check against `FeedbackAsanaTask` (return 200 `{warning:"duplicate"}` unless `force`) → decrypt PAT → `AsanaClient.create_task(...)` → persist `FeedbackAsanaTask` link + an `asana_task_created` timeline event (`FeedbackWorkflowEvent`). On auth failure set `last_error`/`last_sync_status`, return 403.

## Backend files (mirror `jira_integration`)

**New:**
- `src/models/asana_integration.py` — `AsanaIntegration` (org-unique; drop `site_url`/`email`; keep encrypted `api_token`, `token_hint`, `account_gid`, `display_name`, status/error columns) + `FeedbackAsanaTask` (mirror `FeedbackJiraIssue`, `*_task_*` fields).
- `alembic/versions/{rev}_add_asana_integration_tables.py`.
- `src/services/asana_client.py` — `AsanaClient` (Bearer PAT, **fixed host `https://app.asana.com/api/1.0`**), error taxonomy `AsanaError/AsanaAuthError(401/403)/AsanaTransientError(429,5xx)/AsanaNotFoundError(404)`; methods `validate()` (`GET /users/me`), `get_workspaces()`, `get_projects(workspace_gid)` (`GET /projects?workspace=`), `create_task({name,notes,projects:[gid],workspace})` (`POST /tasks`).
- Tests: `test_asana_models.py`, `test_asana_client.py`, `test_asana_connection.py`, `test_asana_issues.py` (tasks), `test_feedback_sources_asana.py`.

**Touch:**
- `src/models/__init__.py` — import + `__all__`.
- `src/api/main.py` — import + `app.include_router(...)` (near line 286).
- `src/api/routes/feedback_sources.py` — add `asana` `SourceTypeInfo` (`requires_integration=False`) in `list_source_types()` + add `"asana"` to `valid_types` in `create_feedback_source`.

## Frontend files (mirror Jira, PAT-only + Workspace/Project)

**frontend-web NEW:** `lib/api/asana.ts` (connect = `{api_token}` only; `getWorkspaces()` + `getProjects(workspaceId)`, no issue-type), `lib/asanaIssueWizard.ts`, `components/icons/AsanaIcon.tsx` (brand `#F06A6A`), `app/(dashboard)/settings/integrations/asana/page.tsx` (**single PAT field**), tests `lib/api/__tests__/asana.test.ts` + `lib/__tests__/asanaIssueWizard.test.ts`.
**frontend-web EDIT:** `app/(dashboard)/settings/integrations/page.tsx` (status state+fetch, connected card, available tile, empty-state guard), `app/(dashboard)/feedbacks/[id]/create-issue/page.tsx` (**activate the already-present "Coming soon" Asana tile** → Workspace picker → Project picker → submit; no issue-type).
**landing-web:** `lib/integrations.ts` (`asana` entry `status:'available'`), `components/icons/AsanaIcon.tsx`, `app/integrations/asana/page.tsx`, `app/integrations/page.tsx` + `components/landing/IntegrationBar.tsx` icon maps.
**docs:** `docs/SELF_HOSTING.md` "Connecting Asana" section.

## Key differences from Jira (SSRF surface is smaller)

- **Fixed host** `app.asana.com` → no `site_url` column, no `_normalize_site_url`, **no `_assert_host_not_ssrf` DNS gate**. Client still asserts constant scheme/host (cheap).
- **Bearer PAT** (`Authorization: Bearer <pat>`), not Basic → connect request is **PAT only** (no email).
- Asana uses **workspace + project + `gid`** identifiers; `notes` is plain text → **no ADF/`text_to_adf`** needed.

## Contradictions / open questions to resolve in the PRD interview

1. **"Register `asana` as a source type" vs inbound ingestion.** Jira IS registered in the backend `/types` list, but the **worker has no Jira adapter** (registry = email/intercom/slack/webhook/zendesk only). So source-type registration is a lightweight backend `SourceTypeInfo` entry that does **not** imply inbound processing. Decision: **slice 1 is outbound-only** (create-task); register `asana` in `feedback_sources.py` for parity, but build **no worker adapter and no inbound feedback-source wizard pages**. Confirm this scope.
2. **Alembic has 6 heads on `master`** (each recent integration added a head without linearizing — Zendesk's `z1a2b3c4d5e6` did the same). Follow precedent: chain the Asana migration from the **Zendesk head `z1a2b3c4d5e6`**. Flag that a real `alembic upgrade head` would need `alembic merge heads` — but that's a pre-existing repo condition, out of scope for this slice.
3. **Duplicate-guard key.** Mirror Jira: one `FeedbackAsanaTask` per (org, feedback) unless `force`. Confirm we key duplicates on `feedback_id` (not task content).
4. **Landing/docs scope.** Confirm slice 1 includes the marketing landing page + SELF_HOSTING doc (Jira/Zendesk both shipped these together).

## Deferred to v2 (name in PRD, same shape Jira used)
OAuth 2.0; inbound status-sync back to Rereflect (webhooks/polling); AI-drafted task content; project/section mapping config; multiple workspaces per org; inbound Asana-as-feedback-source ingestion.
