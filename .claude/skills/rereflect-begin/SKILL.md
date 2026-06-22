---
name: rereflect-begin
description: Use when starting work on a Rereflect GitHub issue (bug/feat/task/chore) from its number, or on a freeform task, and you need stakeholder proposals (technical + non-technical PDFs with diagrams) before planning. Triggers on "rereflect-begin", "rb", "rb bug 42", "rb feat 123", "begin full".
arguments: "type id"
---

# Rereflect Begin (Full Track)

## Overview

Same pipeline as `rereflect-begin-fast`, plus a **proposal phase**: after the PRD is approved, produce diagrams and two review PDFs (technical + non-technical) for stakeholders, get approval, then plan.

**Invocation:** `rb <type> <id>` — e.g. `rb bug 42`, `rb feat 123`, `rb chore drop-stripe`.
Arguments and conventions (type set, `<type>/<id>` branch, descriptive slug, worktree, GitHub issue or freeform fallback) are identical to `rereflect-begin-fast`.

The two non-negotiables carry over from `rereflect-begin-fast`: **always work through the agents team** (every phase, including diagrams and the two proposals), and **implementation is test-first** via the `test-driven-development` skill, executed by the agents team.

## Pipeline

**REQUIRED SUB-SKILL:** Use `rereflect-begin-fast` for the base pipeline.

Run its **Phase 0 → Phase 4 and the ⛔ PRD review gate exactly as written** (worktree → gather context → deep dig → `prd-interview` → `prd-generator` → stop for PRD approval).

**Then, instead of going straight to tech-plan, insert Phase A below. Only after Phase A's approval gate do you run `rereflect-begin-fast`'s Phase 5 (tech-plan) and Phase 6 (implement — TDD via the agents team).**

### Phase A — Proposals (diagrams → PDFs)

Detailed steps, proposal structure, and `md-to-pdf` invocation: see `references/proposals.md`.

1. **Diagram** — Use `excalidraw`. From the approved PRD, draw as many diagrams as the feature needs (system/architecture, data flow, sequence, before/after, ER/schema, etc.). Save to `docs/planning/{slug}/diagrams/*.excalidraw`.
2. **Export** — Use `excalidraw-to-svg` to render every diagram to `.svg` alongside the source.
3. **Write two proposals** (markdown, in `docs/planning/{slug}/proposals/`), embedding the SVGs. Both filenames are prefixed with the issue type and id so stakeholders can identify the source at a glance:
   - `<type>-<id>-technical-proposal.md` (e.g. `bug-42-technical-proposal.md`) — for engineers: architecture, components, data flow, risks, effort.
   - `<type>-<id>-non-technical-proposal.md` (e.g. `bug-42-non-technical-proposal.md`) — for stakeholders: problem, value, what changes for users, timeline, plain language.
   Generate the two in parallel (see Parallelization).
4. **PDF** — Use `md-to-pdf` to produce `<type>-<id>-technical-proposal.pdf` and `<type>-<id>-non-technical-proposal.pdf`.

### ⛔ Approval gate — STOP

Present both PDFs. **Wait for the user's explicit approval** of the proposals before planning. Do not auto-advance.

### Final phases — Plan & implement

Run `rereflect-begin-fast`'s **Phase 5 (tech-plan)** → `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`, then its **Phase 6 (implement)** — strict TDD (`test-driven-development`) executed through the agents team (`superpowers:subagent-driven-development`), one agent per plan task, branch kept green.

## Artifact layout (inside the worktree)

```
docs/planning/
├── _card/card.md                     ← raw gh dump (or freeform brief)
├── {slug}/prd.md                     ← PRD (approved at the first gate)
├── {slug}/diagrams/*.excalidraw|.svg ← Phase A
├── {slug}/proposals/<type>-<id>-technical-proposal.{md,pdf}
├── {slug}/proposals/<type>-<id>-non-technical-proposal.{md,pdf}
└── {slug}/{aspect}/plan_*.md         ← tech-plan
```

## Agents team (mandatory)

Run **every** phase through the agents team — never serially in the main thread.

**REQUIRED SUB-SKILL:** Use `superpowers:dispatching-parallel-agents`; use `superpowers:subagent-driven-development` for Phase 6.

- Base pipeline: fan out context-gathering across referenced issues and affected services (as in `rereflect-begin-fast`).
- Phase A: generate independent diagrams with parallel agents; write the technical and non-technical proposals concurrently (two agents, same PRD + SVGs).
- Phase 6: one agent per independent plan task, each in strict TDD.

## Common mistakes

| Mistake | Fix |
|---|---|
| Writing proposals before the PRD is approved | Phase A starts only after the first ⛔ gate |
| One proposal for both audiences | Always two: technical and non-technical |
| Embedding `.excalidraw` instead of `.svg` | PDFs embed the exported SVGs |
| Skipping the proposal approval gate | Proposals must be approved before tech-plan |
| Diagrams/PDFs outside the worktree | Everything lives under the worktree's `docs/planning/{slug}/` |
| Implementing serially or test-after | Phase 6 is agents-team + strict TDD (RED before GREEN) |
