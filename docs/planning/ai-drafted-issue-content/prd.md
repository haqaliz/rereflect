# PRD — AI-drafted issue/task content

**Slug:** `ai-drafted-issue-content` · **Type:** feat · **Branch:** `feat/ai-drafted-issue-content`
**Status:** Draft — self-critiqued, pending review gate · **Date:** 2026-07-07
**Source:** freeform, handed off from `rereflect-next`. Deferred-v2 item: Jira `DEV-TRACKING.md:197`, Asana `AI-TRACKING.md:60`.

---

## Problem Statement

When a user turns a feedback item into a Jira issue or Asana task via the create-work-item wizard
(`feedbacks/[id]/create-issue/page.tsx`), the title/body are pre-seeded verbatim from the raw feedback
(`extracted_issue` → title, `text` → body). Raw customer text makes a poor engineering ticket — it's
unstructured, often emotional, and lacks a crisp title or actionable summary. Users hand-rewrite it, or
create low-quality tickets.

**Who:** operators/CS/PM users of a self-hosted Rereflect who route feedback into their work trackers.
**Cost of status quo:** manual rewriting per ticket; the "integrated AI workflow" moat pillar stays shallow
at exactly the feedback→action handoff. This is a named deferred-v2 gap, unblocked because the LLM
abstraction (M2.1) and prompt/tone infra (M2.3) already exist.

## Goals & Success Metrics

- **G1 — One-click draft.** From the wizard, a user generates a structured `{title, body}` for the selected
  target (Jira or Asana) and it lands in the editable fields for review.
- **G2 — Never auto-create.** The draft only populates fields; creation stays a separate, explicit user action.
- **G3 — Graceful degradation.** Orgs with no LLM configured (keyless local-LLM / VADER-only) see no broken
  flow — the draft action is hidden/disabled and the wizard works exactly as today.
- **G4 — Provider-agnostic + gets better with the model.** Works across BYOK cloud (OpenAI/Anthropic/Google)
  and local (Ollama/OpenAI-compatible) via the existing abstraction; output quality tracks the org's model.

**Measurable acceptance (testable):**
- Draft endpoint returns `{title, body}` for a feedback id + `target` when an LLM is configured.
- Draft endpoint short-circuits (HTTP 409, honest message) when `resolve_generation_llm(...).is_configured`
  is False — no provider call, no 500.
- Frontend: draft button hidden/disabled when unconfigured; visible + functional when configured.
- Draft populates only the two fields; no create call is triggered.
- Confirm dialog appears before overwriting user-edited fields; not for seeded/empty fields.

**Measurement approach (honest, self-hosted):** Rereflect is OSS self-hosted with **no central
telemetry** — there are no cross-customer adoption dashboards, and this PRD does not invent any. Success
is therefore verified by the functional-acceptance tests above (the real gate). The only local proxy an
operator can see is the count of `LLMUsageLog` rows with `task_type="issue_draft"` (M6) — a usage signal,
not a KPI we collect. No numeric adoption targets are claimed on purpose.

## User Personas & Scenarios

- **CS/PM operator (LLM configured):** opens Create Issue → picks Jira project/issue-type → clicks
  "✨ Draft with AI" → reviews the cleaned-up title + structured body → edits → clicks Create Issue.
- **Self-hoster with local VADER only (no LLM):** opens Create Issue → no AI-draft button shown → uses the
  seeded fields exactly as today. Nothing breaks, no error toast.

## Requirements

### Must-have
- **M1** — Shared backend draft service + endpoint `POST /api/v1/feedback/{id}/issue-draft`,
  body `{ target: "jira" | "asana", tone?: string }`, response `{ title: str, body: str }`. Org-scoped
  (feedback not in org → 404). `require_admin_or_owner` (mirror the create routes' auth).
- **M2** — Reuse `resolve_generation_llm(org_id, db)`; if `not is_configured` → **HTTP 409** with an honest
  message (mirrors `copilot_ws.py:470` semantics). No provider call in that path.
- **M3** — Provider-agnostic LLM call via the existing abstraction (worker `LLMProviderFactory` / the same
  path copilot uses — see Open Question T1). **Do not** reuse `response_generator.py`'s OpenAI-only httpx path.
- **M4** — Prompt built from feedback fields (`text`, `extracted_issue`, `sentiment_label`, `tags`,
  `is_urgent`, `pain_point_*`, `feature_request_*`, `urgent_*`, `customer_email`) + org context
  (`brand_voice`, `product_name_display`); tone = `org.default_tone` (fallback `"professional"`).
  Output is **plain text/markdown** — never ADF. `target` tunes length/framing (Jira issue vs Asana task).
- **M5** — Per-provider body conversion stays downstream unchanged: the create routes still apply
  `text_to_adf` (Jira) / plain notes (Asana) to whatever is in the fields at create time.
- **M6** — Record usage: write `LLMUsageLog` with `task_type="issue_draft"` (mirror `org_resolver.log_usage`).
- **M7** — Frontend "✨ Draft with AI" button in both the Jira and Asana configure branches of the wizard,
  mirroring `ResponseModal`'s Sparkles + `Loader2`/disabled loading UX and `toast.error` on failure. Populates
  `jiraForm.summary/description` / `asanaForm.name/notes` via their setters; never calls the submit handlers.
- **M8** — Overwrite behavior: fill directly when fields are empty or still equal the auto-seeded defaults;
  if the user has edited them, show a confirm ("Replace your text with the AI draft?") before overwriting.
  Re-clicking regenerates (same confirm rule).
- **M9** — Draft button visibility gated on LLM-configured state (react to the endpoint's 409, or a small
  `is_configured` signal — see Open Question T2). Keyless orgs never see a broken control.

### Should-have
- **S1** — Frontend + backend tests covering: configured success, unconfigured 409/hidden button, field-only
  population (no create), and overwrite-confirm branch. (Note: `create-issue/page.tsx` has no test today.)
- **S2** — `api_key` / BYOK actually passed to the provider (avoid the M2.3 route bug where it never is).

### Nice-to-have (out of this slice unless cheap)
- **N1** — Tone selector in the draft UI (decided: use org default silently for now).
- **N2** — Linear branch of the wizard also getting the draft button (Jira + Asana only this slice).

## Technical Considerations

- **Services changed:** `services/backend-api` (new `issue_drafter` service + route + schema; new
  `LLMUsageLog.task_type`), `services/frontend-web` (wizard buttons + `lib/api/jira.ts`/`asana.ts` draft calls).
  **worker-service** only if the LLM call path requires importing its `llm` package (T1).
- **No DB migration** expected — `LLMUsageLog.task_type` is a free-text field; no new tables/columns.
- **Multi-tenancy:** feedback + LLM resolution are org-scoped; cross-org feedback id → 404.
- **Reuse, don't duplicate:** `resolve_generation_llm` (gate), `LLMProviderFactory` (call), `LLMUsageLog`
  (usage), `Organization` tone/brand fields (prompt), `ResponseModal` (UI pattern).
- **Rough sizing:** small–medium. Backend = 1 new service + 1 route + 1 schema + usage log (no migration);
  frontend = 2 wizard buttons + 2 API-client methods + confirm/loading UX. The only genuine unknown is T1;
  once resolved, the rest is well-precedented (mirrors `test_response_generation.py` + `test_jira_issues.py`).

### API Contract
```
POST /api/v1/feedback/{feedback_id}/issue-draft
Auth: JWT, require_admin_or_owner
Body: { "target": "jira" | "asana", "tone"?: string }
200:  { "title": string, "body": string }
404:  feedback not in org
409:  no LLM configured for org (is_configured=false) — honest message, no provider call
502/503: provider error (mirror existing LLM error handling)
```

## Edge Cases & Handling

- **E1 — Untrusted feedback text (prompt injection).** Feedback `text` is attacker-controllable customer
  input fed into the draft prompt; it could try to steer the model ("ignore instructions, output …"). Low
  blast radius (output is human-reviewed, never auto-created, no tool access), but the prompt must place
  feedback content in a clearly delimited, data-role section and instruct the model to treat it as untrusted
  content to summarize — not instructions. Cover with a test using an injection-style feedback string.
- **E2 — Very long feedback.** Truncate/bound the feedback text fed to the model (cap input chars) so a huge
  item can't blow the context/token budget; note the cap.
- **E3 — Malformed/empty model output.** If the model returns empty or unparseable title/body, the endpoint
  returns a clean error (not a 500) and the frontend `toast.error`s and leaves the fields untouched. Title is
  additionally clamped to the create routes' limits (Jira/Asana cap 255) — draft should aim short but the
  create route stays the final guard.
- **E4 — Provider timeout/latency.** The button shows the `Loader2` spinner + disabled state throughout;
  on timeout/provider error → `toast.error`, fields untouched, button re-enabled. Reuse existing LLM error
  taxonomy/handling.
- **E5 — Regenerate spam / cost.** Re-clicking regenerates; cost is the operator's own (BYOK/local), so no
  hard server rate-limit this slice, but the button is disabled while a draft is in flight (prevents parallel
  duplicate calls).

## Documentation & Rollout

Every prior integration shipped with docs; this feature follows suit (should-have, in the plan):
- **`docs/SELF_HOSTING.md`** — short note that AI drafting appears in the create-issue wizard when an LLM
  (cloud BYOK or local Ollama/OpenAI-compatible) is configured, and is absent otherwise.
- **`docs/API.md` + OpenAPI** — document `POST /api/v1/feedback/{id}/issue-draft` (it's an internal JWT route,
  but the API docs cover internal routes too — match existing convention).
- **Tracking** — mark the deferred-v2 item done in `DEV-TRACKING.md` (Jira `:197`) and `AI-TRACKING.md`
  (Asana `:60`) on completion.
- **Discoverability** — no announcement surface needed; the button self-reveals when an LLM is configured.

## Risks & Open Questions

- **T1 (RESOLVED 2026-07-07):** Backend-api does **not** import the worker `LLMProviderFactory`. The
  synchronous LLM path is: `resolve_generation_llm(org.id, db)` → `LLMConfig{provider, model, api_key,
  base_url, is_configured}` → construct `openai.AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)`
  and call `client.chat.completions.create(...)`. This is exactly the `copilot_ws.py:71 call_llm_stream`
  pattern (`openai` SDK, already a backend dep; base_url set → local/OpenAI-compatible with dummy key, else
  cloud BYOK). **`issue_drafter` mirrors this non-streaming (`stream=False`)** and parses
  `resp.choices[0].message.content` + `resp.usage`. No worker import, no cross-service dependency.
- **T2:** Frontend gating mechanism — react to the endpoint 409 on click (simplest; button always shown, fails
  gracefully) vs. proactively read an `is_configured` signal to hide the button. Lean: expose `is_configured`
  cheaply (e.g. reuse `aiSettingsAPI`/a tiny field) so the button is hidden, not just failing. Finalize in plan.
- **R1:** Draft quality is model-dependent — mitigated by human-in-the-loop review + a well-structured prompt;
  honest brand ("draft", editable).
- **R2:** `create-issue/page.tsx` has no existing test — adding one is net-new frontend test surface.

## Out of Scope

- Auto-creation / auto-send of issues or tasks.
- Inbound status-sync / write-back from Jira/Asana.
- New LLM providers (reuse existing abstraction only).
- AI drafting for inbound sources (Zendesk/Intercom) — those are ingestion, not creation.
- Linear draft button; per-draft tone selector (deferred, see N1/N2).
