# Card: AI Copilot suggested actions

**Type:** feat (freeform, no GitHub issue)
**Slug:** `copilot-suggested-actions`
**Branch:** `feat/copilot-suggested-actions`
**Source:** `rereflect-next` recommendation (2026-09-06), verified against code + tracking

## Brief

Build AI Copilot **suggested actions**: the copilot proposes concrete, executable actions
alongside its answer, and the user clicks to execute. This is the shape already locked as a
strategic decision, and explicitly deferred as a V1 non-goal — never built.

## Verified facts (from the docs)

- `AI-TRACKING.md:25` — Strategic Decisions table: **"Copilot actions | Read + suggest
  actions (user clicks to execute)"**. The intended shape is locked; only the read half shipped.
- `docs/archive/prd/PRD-AI-COPILOT.md:33` — V1 Non-Goals: **"No action execution (read-only —
  no mutations, no status changes, no assignments)"**. Deferred by scope, not by a blocker.
- `AI-TRACKING.md:144-158` — M2.2 AI Copilot COMPLETE. The checklist has no action item;
  everything shipped is read/answer/report.
- `services/backend-api/src/services/copilot/intent_classifier.py:115` — intents are
  `"data" | "analysis" | "general" | "report"`. No `action` intent.
- `services/backend-api/src/services/copilot/` — no executor/registry module
  (context_resolver, intent_classifier, llm_resolver, report_generator, response_formatter,
  schema_whitelist, sql_executor, sql_generator, sql_validator, template_matcher,
  template_saver).

## Why now (moat)

The execution side is already shipped and tested — this slice only adds proposal + confirm +
dispatch:

- Playbooks with the full action set — `feat/playbook-action-types` (merged `9d4d5792`);
  churn-triggered auto-execution `AI-TRACKING.md:381` (M4.1.5 COMPLETE).
- Bulk cohort actions on the shared `Cohort` contract — `AI-TRACKING.md:346`
  (`segment-actions`): CSV export, bulk tag, bulk assign-owner, run-playbook-on-cohort.
- Status changes via the shared `apply_status_change` helper; tags / `is_urgent` edits —
  `AI-TRACKING.md:456` (public API write scope).

The copilot currently sits outside the churn → health → playbook → automations loop as a
read-only surface. This is the seam that joins them, and it improves as base models improve
(BYOK / local LLM — the M5 framing at `AI-TRACKING.md:463`).

## Hard constraints (settled before the interview)

1. **Whitelisted server-side action registry — never free-form LLM tool calls.** Mirror the
   read path's precedent: `sql_validator.py` + `schema_whitelist.py`.
2. **RBAC re-checked server-side at execute time**, via the existing
   `require_admin_or_owner` / `require_owner` dependencies (`src/api/dependencies.py`).
   A member can view analytics but cannot run playbooks or manage integrations
   (CLAUDE.md permission matrix). The copilot must never become an RBAC bypass — hiding a
   chip in the UI is not enforcement.
3. **Honest degrade with no LLM.** Gate the proposal step on
   `resolve_generation_llm().is_configured` and hide the surface entirely when unconfigured —
   the same precedent as the "✨ Draft with AI" button (AI-Drafted Issue/Task Content row,
   `AI-TRACKING.md`).
4. **Confirm before execute.** No auto-execution; the user clicks. Matches the shipped
   response-suggestion posture ("copy-to-clipboard + edit before sending, no auto-send",
   `AI-TRACKING.md:165`).

## Known limits to carry into the PRD

- `AI-TRACKING.md:346` — run-playbook on a **whole-filter cohort** currently requires a
  `segment` (or explicit emails); a risk/search-only cohort can be exported/tagged/assigned
  but not playbook-run. Any cohort-scoped action suggestion inherits this.
- Small/local models are weakest at structured action selection — the registry must constrain
  the model, not trust it.
- Start with one narrow, testable first slice (suggest + execute a single action type
  end-to-end) rather than the full registry.

## Open questions for the interview

- Which action type is the first slice?
- Where does the proposal surface — Cmd+K modal, /conversations, or both?
- Are proposals model-generated then validated against the registry, or deterministically
  derived from the query result + intent?
- Does an executed action get an audit record / timeline event?
