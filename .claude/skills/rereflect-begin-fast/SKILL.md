---
name: rereflect-begin-fast
description: Use when starting work on a Rereflect GitHub issue (bug/feat/task/chore) from its number, or on a freeform task, and you want the fast path straight to an implementation plan. Triggers on "rereflect-begin-fast", "rbf", "rbf bug 42", "rbf feat 123", "begin fast".
arguments: "type id"
---

# Rereflect Begin (Fast Track)

## Overview

Turn a single GitHub issue (or a freeform task) into shipped, test-driven code. The fast track is: **isolate → gather → dig → PRD → plan → implement (TDD).** No proposal/diagram deliverables (use `rereflect-begin` / `rb` when you need those).

**Two non-negotiables for this whole pipeline:**
- **Always work through the agents team.** Every phase with independent units of work is dispatched to agents and synthesized — never done serially in the main thread. See *Agents team (mandatory)*.
- **Implementation is always test-first**, via the `test-driven-development` skill, and is itself executed by the agents team. See Phase 6.

**Invocation:** `rbf <type> <id>` — e.g. `rbf bug 42`, `rbf feat 123`, `rbf chore drop-stripe`.

- `type` ∈ `bug | feat | task | chore` (normalize `feature` → `feat`).
- `id` = the GitHub issue number, **or** a descriptive kebab-case slug for freeform work with no issue.
- Repo: `haqaliz/rereflect` (single repo, single owner).

## Pipeline

Run phases in order. **Do not skip the review gate.** Every phase runs through the agents team (see *Agents team (mandatory)*), and Phase 6 is strict TDD — never do parallelizable work or implementation serially in the main thread.

### Phase 0 — Isolate in a worktree

**REQUIRED SUB-SKILL:** Use `rereflect-worktrees`.

- Branch name: `<type>/<id>` (e.g. `bug/42`, `feat/local-llm`).
- Worktree dir: `.claude/worktrees/<type>-<id>` (e.g. `.claude/worktrees/bug-42`).
- Create from `origin/master`, then ensure `.worktreeinclude` files (env files + `.claude/skills/`) are present as the sub-skill describes.
- All subsequent work (context dump, PRD, plan) happens **inside this worktree.**

### Phase 1 — Gather issue context (`gh`)

Pull everything available from the GitHub issue, then save a raw dump to `docs/planning/_card/card.md` in the worktree so later phases (and the PRD) have a single source. (Filename is issue-free on purpose — the number lives in the branch/PR; the worktree is already dedicated to one task.)

Gather: the issue title/body/labels/state, **all linked/referenced issues** (`#NNN` mentions, "tracked by", task lists), and **comments**. Images embedded in the issue are skipped on purpose — the user attaches those separately.

**Commands and parsing:** see `references/gather-context.md`.

**Freeform fallback:** if `id` is a slug (no GitHub issue), skip the `gh` fetch. Treat the user's task description as the brief and write it into `docs/planning/_card/card.md` as the source instead. The rest of the pipeline is unchanged.

### Phase 2 — Deep dig

Before any PRD work, understand the real problem and the code it touches.

- Read the saved issue dump and every referenced-issue summary.
- Map the relevant code paths across the affected Rereflect services: FastAPI routes/models (`services/backend-api/src/`), Celery tasks (`services/worker-service/src/`), analysis logic (`services/analysis-engine/src/`), and Next.js pages/components (`services/frontend-web/`).
- If a `graphify-out/` directory exists, query the graph first (`graphify query "..."`, `graphify explain "X"`) to target your reads before grepping.
- Produce a short written "understanding" note: what the issue is really asking, affected areas (which services), ambiguities, and open questions.
- Surface contradictions between the issue text and the code — flag them, don't paper over them.

### Phase 3 — Requirements interview

**REQUIRED SUB-SKILL:** Use `prd-interview`.

- Feed it the Phase 1 dump + Phase 2 understanding as the product brief.
- Let it run discovery and pressure-testing. Answer from the gathered context where you can; ask the user only what the context can't resolve.
- Confirm a **descriptive** feature slug (kebab-case, e.g. `local-llm-byok`) for `docs/planning/{slug}/`. Do **not** name the slug `<type>-<id>` — the issue number lives in the branch and PR, not in committed doc paths.
- Output: `docs/planning/{slug}/prd.md` (+ aspect `spec.md` files if decomposed).

### Phase 4 — Generate & self-critique the PRD

**REQUIRED SUB-SKILL:** Use `prd-generator`.

- Refine `prd.md`, run its self-critique, and surface the 🔴/🟡 gaps.

### ⛔ Review gate — STOP

Present the PRD and its flagged gaps. **Wait for the user's explicit approval** before planning. Do not auto-advance to tech-plan.

### Phase 5 — Implementation plan

**REQUIRED SUB-SKILL:** Use `tech-plan`.

- Plan one aspect at a time from `prd.md` (+ `spec.md`).
- Output: `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`.

### Phase 6 — Implement (TDD, agents team)

Start only after the plan is approved. Implementation is **always test-first** and **always run through the agents team** — never hand-written serially in the main thread.

**REQUIRED SUB-SKILL:** Use `test-driven-development` — strict RED → GREEN → REFACTOR; no production code before a failing test.
**REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` to execute the plan — dispatch one agent per independent task from `plan_YYYYMMDD.md`; parallelize independent tasks with `superpowers:dispatching-parallel-agents`.

- Each dispatched agent owns one task and follows the TDD cycle inside it: write the failing test, make it pass, refactor.
- Run the relevant test/lint after each task and keep the branch green:
  - Backend / worker / analysis: `pytest tests/ -v` in the service dir.
  - Frontend: `npm run test` and `npm run lint` in `services/frontend-web`.
- Commit per task on the `<type>/<id>` branch (issue number lives in the commit/PR, never in code).
- You stay the integrator: sequence dependent tasks, synthesize agent results, and surface blockers at each checkpoint.

## Artifact layout (inside the worktree)

```
docs/planning/
├── _card/card.md                 ← raw gh dump (Phase 1), or freeform brief
├── {slug}/prd.md                 ← prd-interview / prd-generator
└── {slug}/{aspect}/plan_*.md     ← tech-plan
```

Phase 6 produces **code commits** on the `<type>/<id>` branch — not documents.

## Agents team (mandatory)

This pipeline is **always** run through a team of agents, never serially in the main thread. For each phase, dispatch agents for the independent units of work and synthesize their results yourself.

**REQUIRED SUB-SKILL:** Use `superpowers:dispatching-parallel-agents` for independent work, and `superpowers:subagent-driven-development` for executing plan tasks in Phase 6.

- **Phase 1–2:** one agent per referenced issue (5-line summary + relevance) + one agent per affected service to map the code area. Keep the `gh` calls themselves batched in a single message.
- **Phase 6:** one agent per independent plan task; each agent works in strict TDD.

Gates, user-facing summaries, and integration stay with you — the agents do the fan-out work.

## Common mistakes

| Mistake | Fix |
|---|---|
| Working in the primary checkout | Always create the Phase 0 worktree first |
| Slug = `bug-42` | Use a descriptive slug; issue number stays in branch/PR |
| Downloading embedded issue images | Skip images; user attaches them separately |
| Skipping the review gate | PRD must be approved before tech-plan |
| Inventing requirements the issue doesn't support | Flag as open question in the PRD instead |
| Implementing serially in the main thread | Execute the plan through the agents team (subagent-driven-development) |
| Writing code before a failing test | Implementation is strict TDD — RED before GREEN, always |
