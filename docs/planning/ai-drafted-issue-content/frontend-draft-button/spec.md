# Aspect Spec — frontend-draft-button

**Feature:** ai-drafted-issue-content · **Aspect:** frontend-draft-button · **Service:** `services/frontend-web`

## Problem slice & outcome
A "✨ Draft with AI" button in the Jira and Asana branches of the create-issue/task wizard that calls the draft
endpoint and fills the title/body fields for review — never auto-creates; degrades gracefully with no LLM.

## In scope
- Draft button + loading state in both the Jira and Asana configure branches of
  `app/(dashboard)/feedbacks/[id]/create-issue/page.tsx`.
- `lib/api/issueDraft.ts` (or add to jira/asana clients) — `draftIssueContent(feedbackId, target)`.
- Overwrite-with-confirm-if-edited behavior (M8); re-click regenerates.
- Graceful degradation (M9 / T2 resolution): button hidden when no LLM configured.

## Out of scope
- Backend (separate aspect). Linear branch. Tone selector. Auto-create.

## Acceptance criteria (testable)
1. Button visible in Jira + Asana branches when an LLM is configured; **hidden** when not (T2).
2. Click → loading (spinner, disabled) → fields populated from `{title, body}`; no create call fired.
3. If the field content differs from the auto-seeded default (user edited), a confirm appears before overwrite;
   accepting overwrites, cancelling leaves fields untouched.
4. On endpoint error (incl. 409) → `toast.error`, fields untouched, button re-enabled.
5. Button disabled while a draft is in flight (no parallel calls).

## Dependencies & sequencing
- Depends on: backend-draft-service (endpoint contract). Sequence **after** the backend aspect.
- Precedent to mirror: `components/feedback/ResponseModal.tsx` (Sparkles + `Loader2`, `generating` state).

## T2 resolution (frontend gate)
Read the org's LLM-configured signal via `aiSettingsAPI.get()` (`ai_analysis_enabled` + `default_provider`/
`has_custom_key`) **or** `listKeys()` on wizard mount; store `aiConfigured: boolean`; render the button only when
true. The endpoint's 409 remains the backend safety net (criterion 4), but the button is **hidden**, not merely
failing, so keyless orgs never see a dead control. Local (Ollama/OpenAI-compatible) counts as configured — make
sure the chosen signal reflects `default_provider` + base_url, not just cloud keys. _If `aiSettingsAPI.get()`
does not expose a local-configured flag cleanly, fall back to attempting the draft and treating 409 as "hide
next time" — decide during implementation, prefer the explicit signal._

## Open questions / risks
- `create-issue/page.tsx` has **no existing test** — this aspect adds the first (R2).
