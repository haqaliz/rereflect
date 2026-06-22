---
name: tech-plan
description: Create a phased technical implementation plan from planning artifacts in docs/planning (PRD + aspect spec) for the Rereflect monorepo. Use after prd-interview when the user is ready to execute a specific aspect. Triggers on "tech plan", "implementation plan", "plan from PRD".
tags:
  - planning
  - documentation
metadata:
  status: trial
---

Create a phased technical implementation plan from planning artifacts under `docs/planning/{slug}/`.
Inputs can come directly from `prd-interview`; do not require `prd-generator`.
If the user provided artifacts in context (attached file, pasted content, or referenced path), use them directly.
Otherwise, search the workspace for:

- PRDs matching `docs/planning/*/prd.md`
- Aspect specs matching `docs/planning/*/*/spec.md`

Analyze the current codebase (the Rereflect monorepo: `services/backend-api`, `services/frontend-web`, `services/worker-service`, `services/analysis-engine`), then create a detailed **Implementation Plan** optimized for autonomous agent execution.
The plan should be structured so the agent can work through it systematically with minimal human intervention.

## Handoff Contract

- **Feature requirements source:** `docs/planning/{slug}/prd.md`
- **Aspect requirements source (preferred):** `docs/planning/{slug}/{aspect}/spec.md`
- **Plan output (required):** `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`

Plan one aspect at a time.
If a feature has multiple aspects, create one plan file per aspect.

**Filename:** `plan_YYYYMMDD.md` (where YYYYMMDD is today's date, e.g., `plan_20260622.md`)
**Location:** Aspect directory (e.g., `docs/planning/local-llm-byok/provider-config/plan_20260622.md`).
Create the directory if needed.
If the user provided an aspect spec from a different location, write the plan alongside that spec.
If only a PRD is provided (no aspect spec), ask the user which aspect to plan, create or update `spec.md` for that aspect, then write the plan in that aspect directory.
If the PRD was pasted or attached (no file path), ask the user to confirm both feature slug and aspect name, then write to `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`.

## Deliverables

### 1. Project Setup Checklist

- Which service(s) the work touches and any new module/directory structure to create
- Configuration files needed (per-service `.env` keys, etc.)
- Package dependencies to install (`requirements.txt` for Python services, `package.json` for frontend; pin versions where critical)
- Database changes (new Alembic migration?) — note up front

### 2. Implementation Phases

Break the build into sequential phases that can be executed autonomously. For each phase:

**Phase N: [Name]**

- **Goal:** What this phase accomplishes
- **Prerequisites:** What must exist before starting
- **Files to create/modify:** Explicit list, with service prefix (e.g. `services/backend-api/src/api/routes/...`)
- **Implementation steps:** Numbered, specific instructions
- **Validation:** How to verify the phase is complete (`pytest tests/ -v` for Python services; `npm run test` / `npm run lint` for frontend; expected outputs)
- **Commit message:** Suggested commit message for this phase

### 3. File-by-File Build Order

Ordered list of every file to create/modify, with:

- Filepath (service-qualified)
- Purpose (one line)
- Key functions/components/endpoints it exports
- Dependencies on other files in the project

### 4. Testing Strategy

- Unit tests to write (mapped to implementation phases) — `pytest` for backend/worker/analysis, Vitest for frontend
- Integration tests (API routes, Celery task flow)
- Manual verification steps (`./start-all.sh`, then exercise the flow at http://localhost:3000)
- Test commands to run per service

### 5. Environment & Secrets

- Environment variables needed (which service's `.env`)
- External services/APIs to configure (LLM providers, Redis, Resend, etc.)
- Local development setup instructions (Redis running, Celery worker active, migrations applied)

### 6. Edge Cases & Error Handling

- Known edge cases to handle
- Error states to account for (HTTP status codes, validation, multi-tenancy `organization_id` scoping)
- Fallback behaviors

### 7. Agent Execution Notes

- Suggested checkpoints for human review
- Areas likely to need iteration or debugging
- Sections where the agent should ask for clarification before proceeding

## Guidelines

- Be extremely explicit — assume no implicit knowledge
- Prefer small, testable increments over large monolithic steps
- Each phase should result in runnable (even if incomplete) code, branch kept green
- Respect Rereflect conventions: validate `organization_id` on every route, Pydantic models for request/response, CSS variables (never hardcoded colors) on the frontend
- Flag any spec ambiguities that could block implementation
- Note assumptions clearly
- Optimize for autonomous execution with minimal back-and-forth

## Edge Cases

- **Greenfield vs. existing codebase**: Rereflect is an existing codebase — skip scaffolding and focus on integration points and impact analysis. (Full project setup only applies to a brand-new service.)
- **No aspect spec exists yet**: Derive a candidate aspect list from the PRD, ask the user to choose one, draft `spec.md` for that aspect, confirm, then plan.
- **Incomplete PRD**: If the PRD lacks testable acceptance criteria or measurable metrics, flag this and recommend running prd-interview before planning.
- **Multiple PRDs**: Create separate implementation plans per PRD unless they share infrastructure, in which case note shared phases.
- **Multiple planning sessions**: If an aspect has multiple `plan_YYYYMMDD.md` files, base the new plan on the current `prd.md` + `spec.md`. Create a new plan file with today's date.
- **PRD with flagged gaps**: If prd-interview produced the PRD via the "just write it" path, gaps may be marked. Note these in the plan and recommend resolution before the affected phase.
