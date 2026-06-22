---
name: rereflect-end
description: Use when finishing local work on a Rereflect GitHub issue after the PR is merged and you also need a completion report on Desktop. Triggers on "rereflect-end", "re", "re bug 42", "re feat 123", "end full".
arguments: "type id"
---

# Rereflect End (Full Track)

## Overview

Same cleanup as `rereflect-end-fast`, **plus** a completion report at the end via `rereflect-report`.

**Invocation:** `re <type> <id>` — e.g. `re bug 42`, `re feat 123`.
Arguments and conventions are identical to `rereflect-end-fast`.

## Pipeline

**REQUIRED SUB-SKILL:** Use `rereflect-end-fast` for the cleanup pipeline.

Run its **Phase 0 → Phase 2 exactly as written** (safety check → master + pull → remove worktree → delete branch). Only proceed to Phase 3 once cleanup verification passes.

### Phase 3 — Completion report

**REQUIRED SUB-SKILL:** Use `rereflect-report` with the issue id and the corresponding type.

The type vocabulary maps straight through — no translation needed:

| `re` arg | `rereflect-report` arg |
|---|---|
| `bug` | `bug` |
| `task` | `task` |
| `chore` | `chore` |
| `feat` | `feature` |
| `feature` | `feature` |

Example: `re bug 42` → invoke `rereflect-report` with `bug` + `42` → writes `/Users/aliz/Desktop/bug-42-completion.md`.

`rereflect-report` fetches the issue via `gh` and produces the standard template. If it asks for a screenshot/video, provide one (or hand it to the user to attach), then confirm the file landed on Desktop.

### Phase 4 — Post a solution comment on the issue (optional)

Same approach as `rereflect-end-fast` Phase 3 — ask the user, draft (using the issue + the just-generated report as source material), confirm, then `gh issue comment <id> --body "..."`. See `rereflect-end-fast` SKILL.md for the snippet and verb mapping.

The comment can mirror the report's plain-English summary in a sentence or two. Same tone rules: no em dashes, no jargon, no commit hashes. Skip entirely if the user declines or the work was freeform (no issue).

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the report before cleanup | Phases 0–2 first; the report is last |
| Skipping the report on purpose | Use `rereflect-end-fast` / `ref` instead |
| Passing the wrong type to `rereflect-report` | Apply the mapping table (`feat`/`feature` → `feature`) |
| Posting the issue comment before the report | Phase 4 comes after Phase 3; the report's plain-English summary is good source material |
| Posting the comment without confirmation | Draft first, confirm with the user, then post |
