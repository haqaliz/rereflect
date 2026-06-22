---
name: rereflect-worktrees
description: Isolate parallel work in the Rereflect monorepo using the Claude Code worktree layout. Use when starting work on a new bug/feature that should not collide with another running Claude session, or when needing to run two stacks (frontend + backend + worker) locally at once. Covers branch naming, worktree placement under .claude/worktrees, auto-copied gitignored files via .worktreeinclude, and cleanup.
allowed-tools: Bash, Read, Write, Edit, Glob
---

# Rereflect Worktree Workflow

## When to Use

- Another Claude session is already running on a different branch in this repo and you want to start a new bug/feature without colliding.
- You want to run two full stacks (frontend + backend + worker) side by side on different branches.
- The user says "create a worktree for #NN" or "let's isolate this in a worktree".
- The primary checkout is dirty and switching branches would mix work.

Don't use this for one-off file edits that finish in a single session — a worktree is overhead for nothing if you commit + push before the next branch switch.

## Layout — the official Claude Code pattern

Worktrees live **inside the repo** at `.claude/worktrees/<name>/`. The whole `.claude/` directory is already in `.gitignore` here, so worktree contents never appear as untracked files in the primary.

```
/Users/aliz/dev/at/rereflect/                            ← primary (master)
/Users/aliz/dev/at/rereflect/.claude/worktrees/bug-42/   ← bug 42 worktree
/Users/aliz/dev/at/rereflect/.claude/worktrees/feat-local-llm/
```

This is the layout documented at https://code.claude.com/docs/en/worktrees. Sibling layouts like `rereflect.42` work but make `cd` paths awkward and don't auto-trigger `.worktreeinclude` for `claude --worktree`.

## Branch naming convention

`<type>/<id>` — where `id` is the GitHub issue number, or a descriptive kebab-case slug for freeform work with no issue. Examples:
- `bug/42`
- `feat/123`
- `feat/local-llm` (freeform, no issue number)
- `chore/drop-stripe`

`type` ∈ `bug | feat | task | chore` (normalize `feature` → `feat`). Rereflect is a single-owner repo, so no owner suffix.

## Creating a worktree

### From master (new branch)
```bash
git fetch origin master
git worktree add -b bug/42 .claude/worktrees/bug-42 origin/master
```

### From an existing branch you already pushed
```bash
git worktree add .claude/worktrees/bug-42 bug/42
```

### Via Claude Code's --worktree flag
```bash
claude --worktree bug-42
```
This creates `.claude/worktrees/bug-42/` on a new branch `worktree-bug-42` based on `origin/HEAD`, and processes `.worktreeinclude` automatically. The auto-generated `worktree-<name>` branch usually won't match the `<type>/<id>` convention — when naming work after an issue, create the branch first, then `git worktree add` with the existing branch.

## Auto-copying gitignored config (`.worktreeinclude`)

`.claude/` and per-service `.env` files are gitignored, so a fresh worktree starts **without** them. The repo root has a `.worktreeinclude` listing what must follow into new worktrees:

```
.claude/skills/
services/backend-api/.env
services/worker-service/.env
services/analysis-engine/.env
services/frontend-web/.env.local
services/frontend-web/.env.sentry-build-plugin
```

`.worktreeinclude` is consumed automatically by `claude --worktree`. The `.claude/skills/` entry is what carries the `rereflect-*` workflow skills into the worktree so you can keep using them there.

When using bare `git worktree add`, copy the relevant files manually (it doesn't re-process the include after creation):

```bash
WT=.claude/worktrees/bug-42
mkdir -p "$WT/services/backend-api" "$WT/services/worker-service" \
         "$WT/services/analysis-engine" "$WT/services/frontend-web"
cp services/backend-api/.env        "$WT/services/backend-api/.env"
cp services/worker-service/.env      "$WT/services/worker-service/.env"
cp services/analysis-engine/.env     "$WT/services/analysis-engine/.env"
cp services/frontend-web/.env.local  "$WT/services/frontend-web/.env.local"
cp -R .claude/skills                 "$WT/.claude/skills"
```

Do **not** copy `venv/` or `node_modules/` — those are per-worktree and reinstalled below.

## Per-worktree setup (Python services)

Each service owns its own `venv/` (not shared between worktrees). Backend, worker, and analysis-engine each need one. `start.sh` creates/activates `venv` and installs `requirements.txt` if missing, so the simplest path is just to run it:

```bash
cd .claude/worktrees/bug-42/services/backend-api
./start.sh            # creates venv, installs deps, serves on :8000
```

```bash
cd .claude/worktrees/bug-42/services/worker-service
./start.sh            # creates venv, installs deps, starts Celery (needs Redis)
```

Manual venv setup if you prefer:
```bash
cd .claude/worktrees/bug-42/services/backend-api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Per-worktree setup (frontend)

`node_modules` is per-worktree and not auto-installed:

```bash
cd .claude/worktrees/bug-42/services/frontend-web
npm install
npm run dev          # Next.js on :3000
```

## Ports & running two stacks at once

Default ports (from CLAUDE.md): frontend `3000`, backend API `8000`, Redis `6379`. **Redis is shared** — run one `redis-server` for the machine; both worktrees can talk to it (be aware Celery tasks share the same broker/queues unless you change `REDIS_URL`/DB index in the worktree's `.env`).

If the primary stack is already serving, override ports in the worktree:
```bash
# Frontend
npm run dev -- --port 3001
# Backend (uvicorn under start.sh honors PORT, or run directly)
uvicorn src.api.main:app --reload --port 8001
```
Point the worktree frontend's `.env.local` `NEXT_PUBLIC_API_URL` at the matching backend port.

## Alembic migrations from a worktree

Paths are relative to the worktree, not the primary:
```bash
cd .claude/worktrees/bug-42/services/backend-api
source venv/bin/activate
alembic upgrade head
alembic revision -m "description"
```

## Switching between worktrees

```bash
git worktree list
```
To jump into a worktree's Claude session, `cd` into the worktree dir and run `claude`. Resuming a session that was started in the primary on the same branch isn't supported — start a new session in the worktree.

## Cleaning up

After the PR merges and you no longer need the branch locally:

```bash
git worktree remove .claude/worktrees/bug-42
git branch -d bug/42
```

`worktree remove` refuses if there are uncommitted or untracked changes. Either commit them first, or pass `--force` only if you're sure they should be discarded. (`rereflect-end-fast` automates this safely.)

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` / `celery: command not found` in worktree | `venv/` not created in this worktree | Run the service's `./start.sh`, or `python3 -m venv venv && pip install -r requirements.txt` |
| Backend exits: "Redis is not running" | No `redis-server` for the machine | Start one shared Redis: `redis-server` |
| Frontend can't reach API | `.env.local` not copied, or wrong `NEXT_PUBLIC_API_URL` port | Copy `.env.local`, point it at the worktree's backend port |
| Next.js dev fails on :3000 | Port held by primary's `npm run dev` | `npm run dev -- --port 3001` |
| Worktree missing `rereflect-*` skills | `.claude/skills/` not carried over | `cp -R .claude/skills <worktree>/.claude/skills`, or add it to `.worktreeinclude` and use `claude --worktree` |
| `git worktree add` fails: "already checked out" | Branch is checked out in another worktree (often the primary) | `git checkout master` in the conflicting worktree first, then retry |

## Migrating an old sibling-style worktree

If you have `rereflect.42` sitting next to the primary, migrate it:

```bash
git worktree move /Users/aliz/dev/at/rereflect.42 \
  /Users/aliz/dev/at/rereflect/.claude/worktrees/bug-42
```

`git worktree move` preserves untracked files (`.env`, `venv`, `node_modules`), so nothing is lost.
