# Understanding — AI-drafted issue/task content

_Phase 2 dig synthesis (3 mapping agents). All paths in the worktree; line refs `file:line`._

## What the feature really is

Add an **"AI draft" action** to the existing "create work item from feedback" wizard. On click it
calls the LLM (reusing existing infra) to generate a **title + body** from the feedback item, and
**populates the editable wizard fields** — the user reviews/edits, then clicks the existing
"Create Issue"/"Create Task". **Never auto-create.** Degrade gracefully (hide/disable the button)
when no LLM is configured.

## Affected areas (services)

### Backend — `services/backend-api`
- **Jira create flow:** client `src/services/jira_client.py` (`JiraClient`, `text_to_adf`); route
  `POST /api/v1/integrations/jira/issues` → `jira_create_issue` (`jira_integration.py:557`); schema
  `JiraCreateIssueRequest {feedback_id, project_id, issue_type_id, summary, description, force}`
  (`:113`); dup guard on `FeedbackJiraIssue`; timeline `jira_issue_created` (`:676`).
- **Asana create flow:** client `src/services/asana_client.py`; route
  `POST /api/v1/integrations/asana/tasks` → `asana_create_task` (`asana_integration.py:462`); schema
  `AsanaCreateTaskRequest {feedback_id, workspace_gid, project_gid, name, notes, force}` (`:103`);
  dup guard on `FeedbackAsanaTask`; timeline `asana_task_created` (`:578`).
- **No shared create abstraction** — Jira/Asana/Linear are fully separate branches; only auth deps +
  encryption + `FeedbackWorkflowEvent` are common. So the AI-draft is best introduced as the **first
  genuinely shared feedback→draft service**, consumed by both wizards. Per-provider body conversion
  stays put (Jira `text_to_adf`, Asana plain notes).
- **Backend today does NOT synthesize title/body** — the frontend prefills title=`extracted_issue`,
  body=`text` (`create-issue/page.tsx:195-209`).
- **Feedback source fields to draft from** (`src/models/feedback.py`): `text`, `extracted_issue`,
  `sentiment_label`, `tags`, `is_urgent`, `pain_point_*`, `feature_request_*`, `urgent_*`,
  `churn_risk_score`, `suggested_action`, `customer_email`.

### Backend AI/LLM infra to REUSE
- **Gate:** `src/services/copilot/llm_resolver.py:60` `resolve_generation_llm(org_id, db) → LLMConfig`
  with **`is_configured: bool`** (`:53`) — handles cloud-BYOK **and** local Ollama/OpenAI-compatible.
  This is the exact signal to hide/disable the draft button and to 4xx/short-circuit server-side.
  Consumer precedent: `copilot_ws.py:470,518` (`if not llm_cfg.is_configured:` → honest message).
- **Provider-agnostic call:** worker `src/llm/factory.py:16` `LLMProviderFactory.create(...)` +
  `LLMRequest`/`complete` (openai/anthropic/google/ollama/openai_compatible). BYOK resolve:
  `src/utils/byok.py:25 resolve_org_byok_key(...)`.
- **Do NOT copy** M2.3 `response_generator.py` — it's OpenAI-only bespoke `httpx` and its route never
  passes the BYOK key (always 503s). Reuse only its **prompt shape** (tone/brand_voice/product_name
  from `Organization`: `brand_voice`, `default_tone`, `product_name_display`, `support_email_display`,
  `organization.py:31-34`).
- **Usage:** write `LLMUsageLog` (`models/llm_usage_log.py`) with a new `task_type="issue_draft"`
  (mirror `org_resolver.log_usage`).
- **Tests to mirror:** `tests/test_response_generation.py` (LLM mocked via `AsyncMock` patch of the
  imported symbol in the route module); `tests/test_jira_issues.py` / `test_asana_issues.py` (create-route flow).

### Frontend — `services/frontend-web`
- **Wizard:** `app/(dashboard)/feedbacks/[id]/create-issue/page.tsx` — 3-step, branches Linear/Jira/Asana.
  Populate `jiraForm.summary/description` (`:856-871`) and `asanaForm.name/notes` (`:1018-1033`) via their
  setters; never call the submit handlers.
- **Launched from:** feedback detail Actions dropdown → "Create Issue" (`feedbacks/[id]/page.tsx:471`).
- **API clients:** `lib/api/jira.ts`, `lib/api/asana.ts` (add a `draft` call).
- **LLM-configured signal:** `lib/api/ai-settings.ts` `aiSettingsAPI.get()` (`ai_analysis_enabled`,
  `has_custom_key`, `default_provider`) or `listKeys()`. Page doesn't import ai-settings today — but the
  **draft endpoint's own `is_configured` gate is the source of truth**; frontend can just react to it.
- **UI precedent to mirror:** `components/feedback/ResponseModal.tsx` `handleGenerateAI` (`:145`) —
  `generating` state, Sparkles icon + `Loader2` spinner, `toast.error` on failure (`:290-301`).
- `components/integrations/CreateIssueDialog.tsx:42` already exposes `aiTitle`/`aiDescription` props (legacy
  Linear dialog) — a plumbing precedent.
- **Test gap:** no test exists for `create-issue/page.tsx` itself.

## Contradictions / risks surfaced

1. **Where does the backend execute an LLM completion synchronously today?** The full multi-provider
   factory lives in **worker-service**; the request-path copilot uses `resolve_generation_llm` in
   **backend-api** then generates somewhere. Must confirm the exact backend call path copilot uses
   (imports worker `LLMProviderFactory`? a backend client?) — that decides `issue_drafter`'s call
   mechanism. **Key plan-level open question.**
2. **No shared create abstraction** — introducing the draft as a shared service is the right call but is
   net-new surface (first of its kind here).
3. **Body format:** draft returns plain text/markdown (title + body); per-provider conversion (Jira ADF /
   Asana plain) stays downstream. Don't ask the LLM for ADF.

## Open questions for the interview (product decisions)

- **A. Endpoint shape:** one shared `POST /api/v1/feedback/{id}/issue-draft` → `{title, body}` (with a
  `target: jira|asana` hint for length/format) vs per-provider draft routes. _Recommend: single shared._
- **B. Slice-1 scope:** Jira-only first (card default) vs Jira+Asana together (shared service serves both;
  wizard already has both branches — low marginal cost). _Recommend: both._
- **C. Tone:** expose a tone selector in the draft UI (like ResponseModal) vs silently use `org.default_tone`.
- **D. Overwrite behavior:** draft overwrites current field content (with confirm if non-empty?) or only
  fills when empty; and whether a "regenerate" re-click is supported.
