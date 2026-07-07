# Card — AI-drafted issue/task content (freeform)

**Type:** feat · **Slug:** `ai-drafted-issue-content` · **Branch:** `feat/ai-drafted-issue-content`
**Source:** freeform (no GitHub issue) — handed off from `rereflect-next` on 2026-07-07.

---

## Brief (from rereflect-next handoff)

Add AI-drafted content to the "create work item from feedback" wizard for the outbound
integrations (**Jira first, Asana as immediate follow-on** — they share the wizard). When the
user opens the create-issue / create-task step, offer an **"AI draft"** action that calls the
existing LLM abstraction (reuse the M2.3 response-generation / tone infra) to generate the
issue **title + description (Jira ADF)** / task **name + notes (Asana)** from the feedback item,
populated into the existing editable fields **for review before create — never auto-create**.

## Why (moat / grounding)

- Genuine **deferred-v2** item in the docs, not invented:
  - Jira: "AI-drafted issue content" deferred — `DEV-TRACKING.md:197`
  - Asana: "AI-drafted content" deferred v2 — `AI-TRACKING.md:60`
- **Unblocked** — the LLM abstraction (M2.1, `AI-TRACKING.md:130`) and response-generation
  infra with tone control (M2.3, `AI-TRACKING.md:156`) already exist to reuse.
- Deepens the real moat: **integrated AI workflow + integration + developer surface**. Rides the
  create-issue/create-task wizard that already has shared Jira + Asana branches
  (`AI-TRACKING.md:58,60`).
- **Gets better as base models improve** — fits BYOK / local-LLM positioning (rank rule 2).

## Caveats to respect from the start

- **Human-in-the-loop only:** draft into the existing editable wizard fields; user edits, then
  creates. **Never auto-create** (matches M2.3's no-auto-send precedent + honest brand).
- **Degrade gracefully:** for keyless local-LLM / VADER-only orgs where no LLM resolves, the
  wizard shows today's manual/blank fields — no error, no broken flow. The "AI draft" action
  should be hidden/disabled when no LLM provider resolves.
- Keep the existing **org-scoped duplicate guard** intact.
- **Slice 1 = shared drafting service + Jira** (both branches share the wizard); Asana is the
  immediate follow-on.

## Out of scope (initial)

- Auto-creation / auto-send of issues or tasks.
- Inbound status-sync / write-back from Jira/Asana (separate deferred-v2 thread).
- New LLM providers (reuse existing abstraction only).
- AI-drafted content for inbound sources (Zendesk/Intercom) — those are ingestion, not creation.

## Reference implementations to mirror (confirm in Phase 2 dig)

- Create-issue / create-task wizard (frontend) — the shared Jira + Asana branch UI.
- Jira + Asana API clients + create-issue/create-task routes (backend).
- M2.3 response generation service (tone selector, LLM call) — the closest "generate text from a
  feedback item" precedent to reuse.
- LLM abstraction / provider-resolution layer (M2.1) — for graceful no-LLM degradation.
