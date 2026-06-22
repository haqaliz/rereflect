# Gathering issue context with `gh`

Goal: dump the GitHub issue, its referenced issues, and comments into
`docs/planning/_card/card.md` inside the worktree.

## Prerequisites

- GitHub CLI authenticated: `gh auth status`. If it errors, run `gh auth login`.
- Repo is `haqaliz/rereflect`; `gh` infers it from the worktree's `origin` remote.

## Constants

```bash
ID="42"          # the GitHub issue number
```

## 1. The issue itself

```bash
gh issue view "$ID" --json number,title,state,author,assignees,labels,body,url,createdAt,comments \
  > /tmp/issue-$ID.json
```

Pull the fields you care about:

```bash
jq '{
  number, title, state, url,
  author: .author.login,
  labels: [.labels[].name],
  assignees: [.assignees[].login],
  body
}' /tmp/issue-$ID.json
```

A human-readable view with comments inline (handy for the dump):

```bash
gh issue view "$ID" --comments
```

## 2. Referenced / linked issues

GitHub has no strict parent/child like Azure DevOps. Discover related issues two ways:

```bash
# (a) #NNN references in the body + comments
jq -r '.body, (.comments[]?.body)' /tmp/issue-$ID.json \
  | grep -oE '#[0-9]+' | tr -d '#' | sort -u

# (b) cross-reference events (issues that mention or track this one) via the timeline API
gh api "repos/haqaliz/rereflect/issues/$ID/timeline" \
  --jq '.[] | select(.event=="cross-referenced") | .source.issue.number' 2>/dev/null | sort -u
```

Fetch each referenced issue (parallelize across agents when there are several):

```bash
gh issue view "$REF_ID" --json number,title,state,body,url
```

## 3. Comments

Already included via `--json comments` above, or rendered inline by `gh issue view --comments`. Attribute each comment to `comments[].author.login` and `comments[].createdAt`.

## 4. Attachments (non-image only)

GitHub issue attachments are markdown links/embeds in the body and comments
(`https://github.com/user-attachments/...` or `https://user-images.githubusercontent.com/...`).
Image embeds use `![...](...)`; file links use `[name](...)`. **Skip images** — the user
attaches those separately. Optionally download non-image attachments:

```bash
mkdir -p docs/planning/_card/attachments
# extract non-image attachment URLs from body + comments, then:
curl -sSL "$URL" -o "docs/planning/_card/attachments/$NAME"
```

## 5. Write the dump

Assemble into `docs/planning/_card/card.md`:

- Header: number, type (label), title, state, author, link to the issue.
- Body (issue description), labels.
- Referenced issues: number, title, state, one-line summary.
- Comments: chronological, attributed.
- Attachments: list of downloaded files (note any images deferred to the user).

This file is the single source the rest of the pipeline reads from.

## Freeform fallback (no issue number)

If `id` is a slug rather than an issue number, there is nothing to fetch. Take the
user's task description as the brief and write it directly into
`docs/planning/_card/card.md` (title, what's being asked, any context the user gave).
The rest of the pipeline reads from this file exactly the same way.
