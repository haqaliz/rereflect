---
name: rereflect-end-fast
description: Use when finishing local work on a Rereflect GitHub issue after the PR is merged and you want to clean up without generating a completion report. Triggers on "rereflect-end-fast", "ref", "ref bug 42", "ref feat 123", "end fast".
arguments: "type id"
---

# Rereflect End (Fast Track)

## Overview

Closes out an issue's local state after the PR has merged: **master → pull → remove worktree → delete branch.** No report (use `rereflect-end` / `re` for that).

**Invocation:** `ref <type> <id>` — e.g. `ref bug 42`, `ref feat 123`.

- `type` ∈ `bug | feat | task | chore` (normalize `feature` → `feat`)
- `id` = the GitHub issue number, or the slug used for freeform work
- Branch: `<type>/<id>`; worktree dir: `.claude/worktrees/<type>-<id>`

## Pipeline

### Phase 0 — Safety check

Before removing anything:

- **Worktree clean?** `git -C <worktree> status --porcelain` must be empty. If not, stop — commit or stash first.
- **Branch merged?** Confirm the PR is merged (`gh pr view <PR> --json state,mergedAt` or `gh pr list --state merged --head <branch>`). `git branch -d` will refuse an unmerged branch on purpose; do not bypass with `-D` without explicit user OK.
- **You may be inside the worktree being removed.** Resolve the primary checkout first (Phase 1) and run all commands from there.

### Phase 1 — Master, pulled

Resolve the **primary** checkout (not the worktree). The first line of `git worktree list` is the primary:

```bash
PRIMARY=$(git worktree list | head -1 | awk '{print $1}')
```

Switch and pull, fast-forward only:

```bash
git -C "$PRIMARY" checkout master
git -C "$PRIMARY" pull --ff-only origin master
```

### Phase 2 — Remove worktree, delete branch

```bash
WORKTREE_NAME="<type>-<id>"   # e.g. bug-42
BRANCH="<type>/<id>"          # e.g. bug/42

git -C "$PRIMARY" worktree remove ".claude/worktrees/$WORKTREE_NAME"
git -C "$PRIMARY" branch -d "$BRANCH"
```

If `worktree remove` refuses due to uncommitted/untracked files, go back to Phase 0 — don't pass `--force` silently.

If `branch -d` refuses because the branch isn't merged into master, surface the message — the PR may not be merged, or there are unpushed commits. Don't use `-D` silently.

After both succeed, verify:

```bash
git -C "$PRIMARY" worktree list           # the worktree should be gone
git -C "$PRIMARY" branch --list "$BRANCH" # should print nothing
```

### Phase 3 — Post a solution comment on the issue (optional)

Optional. Ask first: *"Want me to post a short comment on the issue explaining what we did?"* If the user declines, there's nothing meaningful to say, or the work was freeform (no issue), skip.

Otherwise:

1. **Draft a short note** (2–4 sentences). Sources, in order of preference:
   - What the user tells you to say.
   - The merged PR's title + description (via `gh pr view <PR>`).
   - A best-effort summary from the issue title and the change verb.

   Keep it friendly, light on jargon, no em dashes, no commit hashes, no file paths. The change verb matches the type: `bug → fixed`, `task → done`, `chore → done`, `feat`/`feature → shipped`. Example: *"Shipped the local LLM provider settings. You can now point Rereflect at a self-hosted OpenAI-compatible model from the AI settings page. Let me know if anything looks off."*

2. **Confirm the draft** with the user before posting.

3. **Post it** with `gh`:

   ```bash
   gh issue comment <id> --body "<confirmed comment text>"
   ```

   If `gh` returns an auth error, it isn't logged in — surface the error and stop. On success, `gh` prints the comment URL; tell the user it landed.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running from inside the worktree being removed | Resolve `PRIMARY` first, run commands from there |
| Using `git pull` (allowing merge) | Use `--ff-only` |
| Forcing branch delete with `-D` | Only after explicit user OK — `-d` refuses unmerged for a reason |
| Forcing worktree remove with `--force` | Same — never silently discard uncommitted work |
| Worktree dir vs branch confusion | Worktree dir is `<type>-<id>` (e.g. `bug-42`); branch is `<type>/<id>` (e.g. `bug/42`) |
| Posting the issue comment without confirmation | Draft first, show the user, only post after explicit OK |
| Posting a comment on freeform work | There's no issue to comment on — skip Phase 3 |
