# Aspect: backend-create-task

**Slice of:** Asana Integration slice 1. **Owner:** one backend engineer/agent. **Depends on:** backend-connection.

## Problem slice & outcome
From a feedback item, a user creates an Asana task. This aspect delivers the `FeedbackAsanaTask` link model, the create-task route with a duplicate guard and timeline event, the `AsanaClient.create_task` method, and the linked-tasks lookup. Mirror Jira's `POST /issues` + `FeedbackJiraIssue`.

## In scope
- **Model** `FeedbackAsanaTask` (`feedback_asana_tasks`): `organization_id`, `feedback_id` FK → `feedback_items.id`, `asana_task_gid`, `asana_task_url`, `asana_task_name`, `created_by_user_id`, `created_at`; indexes on org_id + feedback_id. Co-locate in `src/models/asana_integration.py`; ensure the backend-connection migration creates this table too (coordinate).
- **Client method** `AsanaClient.create_task({name, notes, project_gid, workspace_gid})` → `POST /tasks?opt_fields=permalink_url,name,gid` body `{"data": {"name","notes","projects":[project_gid],"workspace":workspace_gid}}`; returns `{gid, url}` where `url = data.permalink_url`. **`opt_fields` is required** — Asana omits `permalink_url` from the create response by default; if it is still absent, fall back to `GET /tasks/{gid}?opt_fields=permalink_url`. A client test must assert `asana_task_url` is populated. Plain-text `notes` (no ADF).
- **Route** in `src/api/routes/asana_integration.py`:
  - `POST /tasks` `{feedback_id, workspace_gid, project_gid, name, notes?, force?}`: org-ownership check on feedback (404 else); duplicate check on `(organization_id, feedback_id)` in `feedback_asana_tasks` → return 200 `{warning:"duplicate", existing_tasks:[...]}` unless `force`; trim `name` to Asana's max; call `create_task`; on `AsanaAuthError` set integration `last_error`/`last_sync_status` and return 403; on success persist `FeedbackAsanaTask` + append an `asana_task_created` timeline entry (`FeedbackWorkflowEvent`, via a `_add_timeline_entry` helper mirroring Jira).
  - `GET /tasks?feedback_id=` → linked `FeedbackAsanaTask` rows for the feedback.
  - Pydantic: `AsanaCreateTaskRequest`, `AsanaCreateTaskResponse` (with `warning?`/`existing_tasks?`), `AsanaLinkedTaskResponse`.

## Out of scope
- Connect/status/disconnect/test + workspace/project metadata (→ backend-connection).
- Section/assignee/due-date/custom fields (v2).
- Any inbound sync.

## Acceptance criteria (testable)
- `test_asana_issues.py` (tasks): create persists a `FeedbackAsanaTask` + a timeline event; duplicate returns 200 warning without a second Asana call unless `force`; feedback from another org → 404; `AsanaAuthError` → 403 and records `last_error`; `name` trimmed to limit; `GET /tasks?feedback_id=` returns links. `AsanaClient` patched at the route import site.
- `test_asana_client.py` extended: `create_task` posts the right `{data:...}` body and parses `gid`/`permalink_url`.

## Dependencies & sequencing
After backend-connection (needs the model file, client, encryption/decrypt helper, and the router). Blocks the frontend create-task wizard branch (needs `POST /tasks` + `GET /tasks`).

## Open questions / risks
- Asana task-name length limit — confirm and enforce the trim.
- `permalink_url` may require a follow-up field request on `POST /tasks`; verify the create response includes it, else `GET /tasks/{gid}?opt_fields=permalink_url`.
