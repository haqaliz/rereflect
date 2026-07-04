# PRD — Jira Cloud Integration (slice 1)

**Slug:** `jira-integration` · **Branch:** `feat/jira-integration` · **Type:** feat
**Date:** 2026-07-04 · **Status:** Draft (pre-review-gate)
**Source:** Freeform task from `rereflect-next` (no GitHub issue). See `../_card/card.md` + `../_card/understanding.md`.

---

## Problem Statement

Rereflect can turn a piece of feedback into an issue in **Linear**, but not in **Jira** — the most
widely deployed enterprise issue tracker and the next pending integration in the backlog
(`DEV-TRACKING.md:189`, "M3.2 — JIRA Integration", unchecked). Teams that run Jira (the majority of
enterprise SaaS orgs) cannot route a bug/feature-request from Rereflect into their engineering
workflow without manual copy-paste, and cannot list Jira as one of their feedback sources.

**Evidence it's real:** Jira is explicitly named in the integration backlog (`DEV-TRACKING.md:183,189`)
and pre-rendered as a "Coming soon" tile already sitting in the create-issue wizard
(`feedbacks/[id]/create-issue/page.tsx:298-312`). The Linear integration shipped end-to-end and is a
proven, tested in-repo blueprint to mirror.

**Who has the problem:** self-hosting operators and their CS/PM/support users whose engineering team
lives in Jira Cloud.

## Goals & Success Metrics

**Goal:** An operator can connect their Jira Cloud site with a pasted API token and create a Jira
issue from any feedback item; `jira` appears as a selectable feedback source.

Success = all of:
- Connect a Jira Cloud site via **email + Atlassian API token** (Basic auth); the token is validated
  before storing and encrypted at rest. Measurable: `POST /connect` with a valid token returns
  `connected: true` and a `token_hint`; an invalid token returns **422** (never 500).
- Create a Jira issue from a feedback item (pick project + issue type, edit summary + description);
  the created issue's **key + browse URL** are stored and shown, and a `jira_issue_created` timeline
  event is recorded. Measurable: `POST /issues` returns the issue key/url; a `FeedbackJiraIssue` row exists.
- `jira` is a selectable source type in the feedback-source wizard (own-auth, `requires_integration=false`).
- **All features unlocked** (OSS self-hosted) — no Pro+ gate. Measurable: create-issue works on a Free-plan org in tests.

**Adoption metric (lagging, post-launch):** ≥1 Jira issue created per connected org within 30 days
of connecting. Acknowledged as a lagging indicator — the slice can be "done and green" without it, so
it's tracked but not a ship gate.

**Non-metric goal:** the slice ships thin enough to review in one PR and leaves clean seams for the
deferred v2 items (AI drafting, status sync, Server/DC).

## User Personas & Scenarios

- **Operator (admin/owner)** connects Jira in Settings → Integrations by pasting their Jira site URL,
  account email, and an Atlassian API token. They see a status card (site, token hint, connected-at)
  and a Test button.
- **CS/PM user** opens a feedback item → "Create issue" → picks Jira → selects a project + issue type,
  edits the pre-filled summary/description → creates. They get a link to the new Jira issue and see it
  linked on the feedback timeline.
- **Anyone browsing integrations** sees an accurate Jira tile (connected/not) and a marketing page.

## Requirements

### Must-have (slice 1)
1. **Connect (token-paste, encrypted)** — `POST /api/v1/integrations/jira/connect` accepting
   `{ site_url, email, api_token }`. Validate via `GET /rest/api/3/myself` before storing; encrypt
   `api_token` with `encrypt_api_key` (Fernet, `LLM_ENCRYPTION_KEY`); store `email` + `site_url`
   plaintext + `token_hint`. Token is **never** returned in any response. Encryption-key-unset → 422.
   One Jira connection per org (`UniqueConstraint(organization_id)`); re-connect rotates the token.
2. **Status / disconnect / test** — `GET /status`, `DELETE /disconnect` (soft `is_active=false`),
   `POST /test` (re-validate stored creds; never 500).
3. **List projects + issue types** — `GET /projects`, `GET /issuetypes?project_id=` proxying the Jira REST API.
4. **Create issue from feedback** — `POST /issues` with `{ feedback_id, project_id, issue_type_id,
   summary, description, force? }`. Verify feedback belongs to the caller's org; duplicate check →
   `200` with `warning: "duplicate"` unless `force`; call `JiraClient.create_issue`; persist a
   `FeedbackJiraIssue` mapping row; add a `jira_issue_created` timeline event. `GET /issues?feedback_id=`
   lists linked issues.
5. **Feedback-source type registration** — add `"jira"` to `valid_types` and a `SourceTypeInfo`
   (`requires_integration=false`, own-auth like Linear) in `feedback_sources.py`; wire the frontend
   source wizard (icon/color + own-auth connection check via `jiraAPI.getStatus()`).
6. **Frontend** — `lib/api/jira.ts`; `settings/integrations/jira` detail page (token-paste connect
   form mirroring HubSpot's; connected-state status grid + Test/Disconnect); Jira tile on the
   integrations index; activate the Jira card in the create-issue wizard with a project/issue-type/
   summary/description sub-form + done step (issue key + browse URL); `JiraIcon`.
7. **Landing page** — `jira` entry in `landing-web/lib/integrations.ts` (token-paste setup wording,
   copy HubSpot's) + `app/integrations/jira/page.tsx` + `JiraIcon`.
8. **Unlocked** — keep `require_admin_or_owner` RBAC; make the feature gate a no-op by mapping
   `jira_integration` to the **free** plan in `plans.py` (uniform with HubSpot), NOT Pro like Linear.
9. **Tests (TDD)** — `test_jira_client.py`, `test_jira_connection.py`, `test_jira_issues.py`,
   `test_jira_models.py` (incl. one-per-org constraint + unlocked-on-free). Frontend `npm run test` + `lint` green.

### Should-have
- Clear inline error surfacing on connect/test (invalid token, wrong site, missing scope) and a
  `last_error` display on the status card (mirror HubSpot).
- **Stale-token handling on the create path** (not just connect/test): if the token is revoked or
  lacks project-create scope at create time, `POST /issues` returns a clear 4xx (422/403) with a
  "reconnect Jira / check permissions" message and records `last_error` — it must NOT 500. This
  failure path is in the test matrix.
- `description` sent to Jira in the correct format (Jira Cloud REST v3 uses **ADF** — Atlassian
  Document Format — for `description`; plain-text must be wrapped). This is a real API contract detail,
  not optional if the description is to render.
- **Operator setup docs** — a short section (in the landing page's `setupSteps` and/or
  `docs/SELF_HOSTING.md`) on minting an Atlassian API token (id.atlassian.com → Security → API tokens)
  and the accepted `site_url` format. Mirrors the usage-enrichment self-hosting-docs precedent.

### Nice-to-have (explicitly deferred — see Out of Scope)
- AI-drafted summary/description, project/status mapping config, inbound status sync.

## Technical Considerations

**Services changed:** `backend-api` (new model + client + route, 3 modified files), `frontend-web`
(new api client + settings page + wizard edits + icon), `landing-web` (new page + data entry + icon).
**No `worker-service` change** — create-issue is synchronous, in-request. **No Alembic noise** — one
clean migration for the two new tables.

**Auth (critical):** mirror **HubSpot's token-paste + encryption**, NOT Linear's OAuth. Basic auth
`base64(email:api_token)` against `https://{site}.atlassian.net/rest/api/3/...`. Linear stores its
token in **plaintext** (a latent bug in the shipped code) — do **not** copy that; use
`encrypt_api_key`/`decrypt_api_key`/`get_key_hint`.

**Not a CRM:** Jira must NOT join the one-CRM-per-org mutual exclusion
(`crm_integration_common.another_crm_active`) — it coexists with HubSpot/Salesforce. One-per-org for
Jira is enforced solely by its own table constraint.

**Multi-tenancy:** every endpoint scopes by `organization_id` from JWT; `JiraIntegration` and
`FeedbackJiraIssue` carry `organization_id`; feedback ownership re-checked on create.

### Data Model (new)
- `jira_integrations` — one row/org. `id`, `organization_id` (unique, no-FK-or-FK per repo norm),
  `site_url`, `email`, `api_token` (Fernet-encrypted), `token_hint`, `account_id`/`display_name`
  (optional, from `/myself`), `is_active`, `connected_by_user_id`, `connected_at`,
  `last_synced_at`/`last_sync_status`/`last_error`, `created_at`/`updated_at`.
- `feedback_jira_issues` — `id`, `organization_id`, `feedback_id` (FK CASCADE), `jira_issue_id`,
  `jira_issue_key` (e.g. "PROJ-142"), `jira_issue_url`, `jira_issue_title`, `created_by_user_id`,
  `created_at`. Indexed on `feedback_id`, `organization_id`.

### API Contracts (new, prefix `/api/v1/integrations/jira`)
`POST /connect` · `GET /status` · `DELETE /disconnect` · `POST /test` · `GET /projects` ·
`GET /issuetypes` · `POST /issues` · `GET /issues`. All under `require_admin_or_owner`;
feature gate is a free-mapped no-op.

## Risks & Open Questions

- **ADF description format** — Jira Cloud REST v3 requires the issue `description` as an ADF document,
  not a plain string. Plan must wrap plain text into a minimal ADF doc, or the create call 400s. (Resolved in the plan; flagged here.)
- **Site URL normalization** — operators may paste `acme.atlassian.net`, `https://acme.atlassian.net`,
  or a trailing slash. Normalize on connect; validate reachability via `/myself`.
- **No live status sync** — without webhooks/polling (deferred), a linked issue's status won't update
  in Rereflect. Accepted limitation for slice 1; store key+url only, don't display a live status field.
- **Disconnect / reconnect semantics (specced):** disconnect is **soft** (`is_active=false`) and
  **preserves** `feedback_jira_issues` links (mirrors Linear). Reconnect **reuses the same org row**
  (rotates `api_token` + `token_hint`, sets `is_active=true`). Existing issue links survive a
  disconnect→reconnect cycle. Covered by a model/route test.
- **Token scope** — an Atlassian API token inherits the user's permissions; creating issues in a
  project the user can't access will 403. Surface as a clear error, don't crash.
- **Backend↔worker model parity test** — not needed since no worker model is added; if a Jira sync
  worker is added in v2, a mirror + parity check becomes required.

## Out of Scope (deferred to v2)

- **Atlassian OAuth 2.0 (3LO)** marketplace flow — awkward for self-host; token-paste only.
- **Jira Server / Data Center** — Cloud (`*.atlassian.net`, REST v3, API-token Basic auth) only.
- **AI-drafted** issue summary/description (BYOK-LLM) — user writes them in slice 1.
- **Inbound Jira → feedback ingestion** — `jira` is registered as a selectable source type but no
  worker matching / event pipeline is built.
- **Project/status mapping config** (Linear's TeamMapping/StatusMapping tables) — pick project +
  issue type live in the wizard instead.
- **Inbound webhook receiver / live status sync / two-way sync.**
- **Multiple Jira sites per org.**
