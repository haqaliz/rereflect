# Card — `chore/status-sync-tracking-truth`

**Type:** chore (freeform — no GitHub issue)
**Branch:** `chore/status-sync-tracking-truth`
**Worktree:** `.claude/worktrees/feat-status-sync-realtime-mapping` (renamed branch in place)
**Opened:** 2026-08-09

## The problem

`rereflect-next` (previous session) recommended building `status-sync-realtime-mapping`
as the next feature — real-time Jira/Asana webhooks + a status-mapping editor UI.
Digging at the start of `rbf feat status-sync-realtime-mapping` proved the feature
**already shipped on master 2026-07-18**: `StatusMappingEditor.tsx` mounted in all
three status-sync cards, `jira_webhook.py` + `asana_webhook.py` (handshake + HMAC,
fail-closed) registered in `main.py:395,398`, `status_mapping` on Jira/Asana GET
`/status`, the race-safe conditional-`UPDATE` writer, webhook enable/secret-reveal
UI, SELF_HOSTING docs, and two security re-reviews — all merged as
`feat/status-sync-realtime-mapping`, planned in
`docs/planning/status-sync-realtime-mapping/`.

What had NOT been done: **the tracking docs still claimed it was deferred** —
the exact "close the marker in the same commit" defect DEV-TRACKING's roadmap-hygiene
note (2026-08-01) warns about, and the reason the previous pick was wrong.

## What this chore fixes

Stale "deferred v2" markers, corrected against the shipped code (each claim
verified by reading the card components + webhook routes before editing):

- `AI-TRACKING.md` rows for Jira / Zendesk / Asana — removed the shipped
  webhook + mapping-editor items from the deferred lists, appended a
  "shipped 2026-07-18" sentence per row, updated the surface cells.
- `DEV-TRACKING.md` M3.2 (Jira) / M3.3 (Asana) / M3.4 (Zendesk) — new shipped
  bullet per section; deferred lists now keep only the genuinely-unbuilt items
  (OAuth 3LO, Server/Data Center, section/custom-field mapping, outbound
  webhook-on-change, etc.).
- `docs/planning/status-sync-realtime-mapping/prd.md` — Status header marked
  SHIPPED so it cannot be re-picked.

## What stays deferred (intentionally untouched)

Jira: OAuth 3LO, Server/Data Center, outbound webhook-on-jira-change, multiple sites.
Asana: OAuth 2.0, section/custom-field → `in_review` mapping, assignee/due-date
mapping, team-scoped-project picker, multiple workspaces. Zendesk: OAuth flow,
per-comment ingestion, backfill, filters, multiple subdomains, outbound
webhook-on-zendesk-change.

## Evidence (shipped state)

- `git log`: `1ab04994` (mapping editor mount), `369bd462` (StatusMappingEditor),
  `14fc718d` (jira webhook), `70428d2f` (asana webhook), `ce711b4b` (race guard),
  `f5bfb43f`/`0bf3fb06` (sec reviews) — all ancestors of master.
- Frontend: `components/settings/{Jira,Asana,Zendesk}StatusSyncCard.tsx` + tests.
- Backend: `services/backend-api/src/api/routes/{jira,asana}_webhook.py`.
- Docs: `docs/SELF_HOSTING.md` "Real-time webhook (optional)" sections.
