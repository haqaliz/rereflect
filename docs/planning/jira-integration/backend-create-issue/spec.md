# Aspect Spec — backend-create-issue

**Parent PRD:** `../prd.md` · **Aspect dir:** `backend-create-issue/` · **Depends on:** `backend-connection`

## Problem slice & outcome

Turn a feedback item into a Jira issue. The backend exposes the project/issue-type pickers the wizard
needs and the create endpoint that actually files the issue, stores the link, and records a timeline
event. Outcome: `POST /issues` → Jira issue key + browse URL; a `FeedbackJiraIssue` row + a
`jira_issue_created` timeline entry exist.

## In scope

- **Extend `JiraClient`** (`src/services/jira_client.py`):
  - `get_projects()` → `GET /rest/api/3/project/search` (or `/project`), returns `[{id, key, name}]`.
  - `get_issue_types(project_id)` → project create-metadata issue types, returns `[{id, name}]`.
  - `create_issue({project_id, issue_type_id, summary, description_adf})` →
    `POST /rest/api/3/issue`, returns `{id, key, self/browse url}`. Build the browse URL as
    `{site_url}/browse/{key}`.
  - **ADF**: `description` must be an **Atlassian Document Format** doc, not a string. Add a helper
    `text_to_adf(text)` producing a minimal valid ADF (`{type:"doc", version:1, content:[{type:
    "paragraph", content:[{type:"text", text}]}]}`); empty text → empty doc. Unit-test this helper.
  - Reuse the `JiraAuthError`/`JiraTransientError`/`JiraNotFoundError` taxonomy from the connection aspect.
- **Routes** (append to `src/api/routes/jira_integration.py`), all under `require_admin_or_owner`,
  using `_require_active_integration` (400 if none) + `get_decrypted_token`:
  - `GET /projects` → proxy `get_projects()`.
  - `GET /issuetypes?project_id=` → proxy `get_issue_types()`.
  - `POST /issues` `{feedback_id, project_id, issue_type_id, summary, description, force?}`:
    1. verify the feedback belongs to the caller's org (404 if not);
    2. duplicate check — if a `FeedbackJiraIssue` already links this feedback and not `force`, return
       **200** with `{warning: "duplicate", ...existing}` (mirror Linear);
    3. `text_to_adf(description)`; call `create_issue(...)`;
    4. **stale-token handling**: `JiraAuthError` → **403/422** with a "reconnect Jira / check project
       permissions" message + set `last_error`/`last_sync_status` on the integration — **never 500**;
       `JiraTransientError` → 502;
    5. persist a `FeedbackJiraIssue` row (`jira_issue_id/key/url/title`, `created_by_user_id`);
    6. add a `jira_issue_created` timeline event (mirror Linear's `_add_timeline_entry`);
    7. return `{jira_issue_id, jira_issue_key, jira_issue_url, jira_issue_title}`.
  - `GET /issues?feedback_id=` → list linked `FeedbackJiraIssue` rows (for the wizard duplicate warning).

## Out of scope (this aspect)

- AI-drafted summary/description (v2).
- Project/status **mapping** config tables/endpoints (v2).
- Inbound webhook / status sync.
- Frontend wizard wiring (→ `frontend`).

## Acceptance criteria (testable — TDD)

- `test_jira_issues.py`:
  - `text_to_adf` unit: wraps plain text into valid ADF; empty string → valid empty doc.
  - `GET /projects` / `GET /issuetypes` proxy the (mocked) client; 400 when not connected.
  - `POST /issues` happy path (mocked `create_issue`) → returns key/url; `FeedbackJiraIssue` row +
    `jira_issue_created` timeline event created.
  - duplicate (already linked, no `force`) → **200** `warning:"duplicate"`, no second row; with
    `force` → creates again.
  - feedback of another org → **404**.
  - **stale token**: client raises `JiraAuthError` → **403/422** (not 500), `last_error` set.
  - transient error → **502**.
  - unlocked on Free plan.
- Mock the client at the route module (`patch("src.api.routes.jira_integration.JiraClient")`).

## Dependencies & sequencing

After `backend-connection` (needs the models, client class + errors, `get_decrypted_token`,
`_require_active_integration`). Blocks the `frontend` create-issue wizard branch.

## Open questions / risks

- Jira `create-meta` for issue types changed across API versions; use the project-scoped
  create-metadata endpoint and tolerate an empty list (surface "no issue types" rather than crash).
- Summary length: Jira caps summary at 255 chars — validate/trim and 422 on empty summary.
