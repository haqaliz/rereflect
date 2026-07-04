# Understanding — feat/jira-integration

Synthesized from 3 read-only mapper agents over the worktree checkout: (1) the shipped **Linear**
integration blueprint, (2) the shipped **HubSpot** token-paste connection shape, (3) the
**feedback-source + create-issue** wiring. All line refs are the worktree checkout on
`feat/jira-integration` (branched from `origin/master`).

## What the task is really asking

Add a **Jira Cloud** integration to Rereflect so an operator can (a) connect their Jira site with a
pasted **Atlassian API token** (email + token, HTTP Basic auth — **not** OAuth 3LO), (b) **create a
Jira issue from a feedback item**, and (c) have `jira` appear as a **feedback-source type**. Mirror
the *structure* of the shipped Linear integration, but take **auth + encryption from the HubSpot
token-paste precedent**, not from Linear's OAuth flow.

## The single most important structural insight

The codebase has **two independent, decoupled wiring points**, and they share no code:

- **(A) Feedback SOURCE type** — just enumerating `jira` so it's selectable. For a create-issue-only
  slice, this is *type registration only* (backend `valid_types` + `/types` entry with
  `requires_integration=False`, frontend icon/color maps + wizard branch). **Inbound Jira
  ingestion (worker `source_events.py` matching) is NOT required** and is out of scope.
- **(B) Create-issue flow** — feedback → Jira issue. Fully separate from (A).

The brief asks for both B and "add `jira` as a feedback-source type", so **A = the cheap type
registration only** (no inbound event pipeline). This is the scope boundary to confirm in the interview.

## Auth & encryption — take from HubSpot, NOT Linear (critical)

- **Linear stores its token in PLAINTEXT** despite a misleading "Fernet-encrypted" column comment
  (route stores raw at `linear_integration.py:412,428`; reads raw at `:494,:627,:744`). **Do not
  copy that.** Use `src/utils/encryption.py` → `encrypt_api_key` / `decrypt_api_key` / `get_key_hint`
  (Fernet, env `LLM_ENCRYPTION_KEY`), exactly as HubSpot/Salesforce do.
- Jira's one pasted credential = **two stored values**: `email` (plaintext, not secret) +
  `api_token` (Fernet-encrypted). Plus `site_url` (e.g. `https://acme.atlassian.net`) and optionally
  `cloud_id`/`account_id`/`display_name`.
- Auth header: **HTTP Basic** `base64(email:api_token)` (httpx `auth=(email, token)`), against
  `https://{site}.atlassian.net/rest/api/3/...` — vs Linear's `Bearer` + GraphQL, vs HubSpot's Bearer.
- Validate on connect via `GET /rest/api/3/myself` (mirror HubSpot's `_validate_hubspot_token`
  error mapping: 401/403 → 422 "invalid or lacks permissions"; other HTTP → 502; network → 502).
  Encryption-key-unset → return **422**, never 500 (HubSpot "R6 safeguard", `hubspot_integration.py:212-222`).

## Jira is NOT a CRM — skip the one-CRM guard

HubSpot/Salesforce share a mutual-exclusion (`crm_integration_common.another_crm_active` +
`purge_crm_enrichment`). **Jira must NOT participate** — a Jira connection coexists with a CRM. Do
not call `another_crm_active` from Jira connect, do not add Jira to that function. One-per-org for
Jira itself is still enforced by a `UniqueConstraint(organization_id)` on the Jira table.

## Slice 1 likely needs NO worker changes

Create-issue is a **synchronous** API call (the Linear `POST /issues` route calls the client inline;
no Celery). Unlike HubSpot (daily sync beat + worker client + backend↔worker model mirror), a
create-issue-only Jira slice does its work in-request. → **No worker task, no worker model mirror, no
beat schedule** for slice 1. (Confirm: only add a worker mirror if we later add background Jira sync.)

## Affected areas (by service) — the mirror targets

**backend-api (CREATE)**
- `src/models/jira_integration.py` — new. Slice-1-minimal: `JiraIntegration` (connection, one-per-org
  `UniqueConstraint`, encrypted `api_token` + plaintext `email` + `site_url`, `token_hint`, `is_active`,
  `connected_by_user_id`, `connected_at`, status cols `last_synced_at`/`last_sync_status`/`last_error`)
  + `FeedbackJiraIssue` (mirror `FeedbackLinearIssue`: `feedback_id`, `organization_id`, `jira_issue_id`,
  `jira_issue_key` e.g. "PROJ-142", `jira_issue_url`, `jira_issue_title`, `created_by_user_id`). Register
  in `src/models/__init__.py`. **Defer** Linear's TeamMapping/StatusMapping tables unless mapping UI is in scope.
- `src/services/jira_client.py` — new. REST (not GraphQL), Basic auth, per-site base URL. Methods:
  `validate`(myself), `get_projects`, `get_issue_types`(per project), `create_issue`. Custom error
  taxonomy (mirror HubSpot's transient/scope/notfound). **No** create_webhook/delete_webhook.
- `src/api/routes/jira_integration.py` — new. Prefix `/api/v1/integrations/jira`. **POST `/connect`**
  (accept pasted email+token+site, validate, encrypt, store; token NEVER in response),
  `GET /status`, `DELETE /disconnect` (soft `is_active=False`), `POST /test`, proxy `GET /projects`,
  `GET /issuetypes`, and **`POST /issues`** (verify feedback ownership, duplicate check → 200
  `warning:"duplicate"` unless `force`, call client, store `FeedbackJiraIssue`, add timeline event
  `jira_issue_created`) + `GET /issues`.
- `alembic/versions/*_add_jira_integration_tables.py` — new, down_revision = current head; keep it
  **clean** (Linear's migration has unrelated auto-gen alter_column noise — don't replicate).
- Tests: `tests/test_jira_client.py`, `test_jira_connection.py` (token-paste, replaces oauth),
  `test_jira_issues.py`, `test_jira_models.py` (incl. one-per-org constraint). Mock the client at the
  route module (`patch("src.api.routes.jira_integration.JiraClient")`), `unittest.mock` — the repo pattern.

**backend-api (MODIFY)**
- `src/api/main.py` — `include_router(jira_integration.router)`.
- `src/api/routes/feedback_sources.py` — add `"jira"` to `valid_types` (L269) + a `SourceTypeInfo`
  in `list_source_types` (L157-203) with `requires_integration=False` (own-auth, like Linear). No
  worker `source_events.py` change (out of scope).
- `src/config/plans.py` — **OSS unlocked**: either omit `require_feature` on Jira routes, or add
  `"jira_integration": "free"` (HubSpot does the latter — the feature gate becomes a no-op while
  keeping the RBAC `require_admin_or_owner` gate). **Do NOT** map it to Pro like Linear does.

**frontend-web (CREATE/MODIFY)**
- `lib/api/jira.ts` — new (mirror `linear.ts` but connect via token POST, not `getConnectUrl`).
- `app/(dashboard)/settings/integrations/jira/page.tsx` — new detail page; **not-connected view is a
  token-paste form** (mirror HubSpot's `settings/integrations/hubspot/page.tsx`: password Input +
  show/hide, site + email inputs, connect error alert; connected view = status grid + Test/Disconnect).
- `app/(dashboard)/settings/integrations/page.tsx` — add a Jira tile + status fetch in the
  `Promise.allSettled` block.
- `app/(dashboard)/feedbacks/[id]/create-issue/page.tsx` — **activate the existing static "JIRA –
  Coming soon" tile (L298-312)**; add `jiraAPI.getStatus()` discovery, a Jira configure sub-form
  (project + issue type + summary + description), submit + done branches (issue key / browse URL).
- `components/icons/JiraIcon.tsx` — new. Optionally mirror source-wizard icon/color maps if Jira-as-source UI is in scope.
- If Jira-as-source: mirror `linear` special-casing across the 4 `feedback-sources/*` pages.

**landing-web (CREATE, optional)**
- `lib/integrations.ts` — add a `jira` entry (copy HubSpot's token-paste setupSteps wording).
- `app/integrations/jira/page.tsx` + `components/icons/JiraIcon.tsx`.

## Ambiguities / open questions (for the interview)

1. **Scope of "feedback-source type"**: confirm A = type registration only (selectable in wizard),
   NOT inbound Jira→feedback ingestion. (Recommended: registration only for slice 1.)
2. **Mapping tables**: skip Linear-style project/status **mapping** config for slice 1 and just pick
   project + issue type live in the create-issue wizard? (Recommended: skip, fetch live.)
3. **AI title/description generation**: Linear offers BYOK-LLM issue content gen. Include for Jira
   slice 1 or defer? (Leaning defer — keep slice thin; user provides summary/description.)
4. **Site identification**: store full `site_url` the operator pastes, or resolve `cloud_id` via
   `/oauth/token/accessible-resources` (that endpoint needs OAuth — with API-token Basic auth we just
   use `https://{site}.atlassian.net` directly). (Recommended: store `site_url`, call it directly.)
5. **Duplicate handling**: reuse Linear's "already linked → 200 warning unless force" pattern? (Yes.)
6. **Plan-gate style**: omit `require_feature` entirely vs add `jira_integration` to the free plan.
   (Either is "unlocked"; HubSpot's add-to-free keeps the pattern uniform.)
7. **Landing page**: in scope for this feature or a follow-up? (Low-risk, optional.)

## Contradiction / risk flags

- **Brief vs code — encryption**: the brief says "follow Linear as the blueprint", but Linear stores
  the token in plaintext. Following Linear *literally* would ship an insecure secret at rest. Resolved
  by the brief's own steer ("copy structure, not auth mechanism") → use HubSpot encryption. Flagged so
  the PRD makes it explicit.
- **Atlassian Cloud vs Server/DC**: only Cloud (`*.atlassian.net`, REST v3, API-token Basic auth) is
  in scope. Server/DC (different base URL, PAT/Bearer) and 3LO OAuth are **deferred v2** per the brief.
- **No status sync without webhooks**: token-paste v1 ships no inbound webhook (HubSpot/Salesforce
  ship none either). The created issue's live status won't auto-update in Rereflect — acceptable for
  slice 1; note it as a known limitation.
