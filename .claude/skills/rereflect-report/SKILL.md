---
name: rereflect-report
description: Use when a Rereflect GitHub issue (bug, task, chore, or feature) is done and you want a brief, friendly, non-technical completion note saved on Desktop to share with the team.
allowed-tools: Read, Grep, Glob, Bash, Write
arguments: "type id"
---

# Rereflect Work Item Completion Note

A short, friendly, non-technical heads-up that an issue is done. Written like a teammate would write it — no jargon, no commit hashes, no checklists. Just one plain-English sentence about what changed, plus a link and a screenshot.

## Arguments

- `type` ∈ `bug | task | chore | feature`
- `id` = the GitHub issue number

Usage: `/rereflect-report bug 42` or `/rereflect-report feature 123`.

## When to use

- An issue is finished and you want to let the team know in a human way.
- You've closed (or are about to close) an issue on GitHub.

## Output

Markdown file saved to `/Users/aliz/Desktop/{type}-{ISSUE_ID}-completion.md`.

Examples:
- `/Users/aliz/Desktop/bug-42-completion.md`
- `/Users/aliz/Desktop/task-50-completion.md`
- `/Users/aliz/Desktop/chore-61-completion.md`
- `/Users/aliz/Desktop/feature-123-completion.md`

## The template

One template, four small verb tweaks. Keep it warm, short, and free of technical detail.

```markdown
## #{Issue ID} - {Page or Feature} - {Short Title}

Hey! Quick note that this one's {verb}.

**What changed (in plain words):**
{One or two friendly sentences. What's different for the user now. No jargon. No em dashes.}

**See it live:** {link to the page or area}
**Screenshot/video:** {attached, or link}

If anything looks off or you'd like a tweak, just say the word.
```

Verb per type:

| Type | Verb |
|---|---|
| `bug` | fixed |
| `task` | done |
| `chore` | done |
| `feature` | shipped |

## Tone rules

- Write like you're messaging a teammate, not filing a ticket.
- Plain English only. Swap out words like *deduplicated, refactored, endpoint, payload, DTO, regex, polyfill, schema migration, idempotent* for everyday phrasing.
- No checklists, no testing matrices, no commit hashes, no branch names, no file paths — those live in the PR, not in this note.
- Two or three short paragraphs max. If it reads like docs, trim again.
- **Never use the em dash character `—` in the note.** It's a tell that an AI wrote it. Use a comma, a period, or a regular hyphen with spaces (`-`) instead.
- A friendly closer is welcome ("Let me know what you think.", "Happy to revisit if needed.").

## Workflow

1. **Fetch the issue** to get the title and context:
   ```bash
   gh issue view [ISSUE_ID] --json number,title,body,url,labels
   ```
2. **Distill** the change into one or two plain sentences. Resist the urge to add detail.
3. **Ask the user for a screenshot or short video** if one isn't already on hand.
4. **Write** the note to `/Users/aliz/Desktop/{type}-{ID}-completion.md` and tell the user it's ready.

## Optional: cross-page check

Only include if the user explicitly asks for it. Append one short, friendly line:

```markdown
**Also checked:** {a couple of related pages you peeked at, in plain words}
```

Don't add this by default — it makes the note look like an audit.

## Example (bug)

```markdown
## #42 - Feedback list - Sentiment badge color

Hey! Quick note that this one's fixed.

**What changed (in plain words):**
The sentiment badges on the feedback list now use the right colors, so negative feedback shows up in red instead of grey and is easy to spot.

**See it live:** http://localhost:3000/feedbacks
**Screenshot/video:** attached

If anything looks off or you'd like a tweak, just say the word.
```
