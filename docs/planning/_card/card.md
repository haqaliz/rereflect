# Card — Asana Integration (freeform)

**Type:** feat · **Slug:** `asana-integration` · **Branch:** `feat/asana-integration`
**Source:** Freeform task from the `rereflect-next` recommendation handoff (verified against git — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-06

---

## Brief

Add an **Asana integration, slice 1** to Rereflect. Asana is the only named integration in the backlog that is entirely unbuilt (`DEV-TRACKING.md:185,199-203`, M3.3), while Slack, Intercom, Email, Linear, Jira, Zendesk, HubSpot, and Salesforce have all shipped (`AI-TRACKING.md:57-59`). It deepens the strongest moat lever (the integration layer / product breadth) at the lowest risk, because five prior integrations followed one proven BYOK token-paste pattern.

### Core capability (slice 1)
- **Connect via a BYOK Personal Access Token (PAT)** — encrypted at rest, SSRF-hardened connect/status/disconnect/test — following the exact pattern in `docs/planning/jira-integration/` (NOT the "OAuth flow" the stale backlog line at `DEV-TRACKING.md:200` implies).
- **Create an Asana task from a feedback item** — workspace + project selection, task name/notes derived from the feedback, duplicate guard — activating an Asana branch in the existing create-issue/task wizard (mirror the Jira create-issue card).
- **Register `asana` as a selectable own-auth feedback source type** (`requires_integration=false`), like Jira.
- **Frontend:** Settings > Integrations token-paste page + tile, create-task wizard Asana branch, landing page + `SELF_HOSTING.md` token-setup docs.

### Explicit non-goals / deferred to v2 (name in the plan, same shape Jira used)
- OAuth 2.0 flow (use PAT instead — self-host precedent).
- Inbound status-sync back to Rereflect (needs webhooks/polling).
- AI-drafted task content.
- Project/status/section mapping config, multiple workspaces per org.

---

## Key caveats (from rereflect-next dig)

1. **Token-paste, not OAuth.** Every recent integration (HubSpot private-app token, Jira/Zendesk API token) deliberately dropped the OAuth marketplace flow because it's awkward for self-hosters. Asana Personal Access Tokens fit this precedent. The `DEV-TRACKING.md:200` "Asana OAuth flow" line is stale.
2. **Outbound target, not inbound source.** Asana is a work-management/outbound target (create tasks from feedback, like Jira/Linear) — NOT an inbound feedback source like Zendesk/Intercom. So slice 1 is the create-task wizard branch; the `asana` source type is `requires_integration=false`.
3. **OSS/self-hosted/BYOK** — all features unlocked, no plan gating (the plan-gating / billing / Resend sections in `CLAUDE.md` and the tables in `AI-TRACKING.md` are stale post-pivot).

---

## Asana API notes (for the dig to verify)

- **Auth:** Personal Access Token via `Authorization: Bearer <PAT>` against `https://app.asana.com/api/1.0`.
- **Validate token:** `GET /users/me` (returns the user + their workspaces).
- **List workspaces:** from `/users/me` or `GET /workspaces`.
- **List projects:** `GET /projects?workspace=<gid>`.
- **Create task:** `POST /tasks` with `{data: {name, notes, projects: [<gid>], workspace: <gid>}}`.
- SSRF surface is lower than Jira/Zendesk because the host is the fixed `app.asana.com` (no per-org subdomain) — still assert scheme/host in the client, matching the Jira precedent.

---

## Reference implementations to mirror
- `docs/planning/jira-integration/` — closest precedent (token-paste connect + create-issue-from-feedback + source-type registration). PRD + 5 aspect specs.
- `docs/planning/zendesk-integration/` — most recent integration (6 aspect specs), for the connect/SSRF/encryption/error-taxonomy patterns.
- Jira create-issue wizard branch in `services/frontend-web/` — the UI to mirror for create-task.
- Jira backend routes/model/client in `services/backend-api/src/` — the connect/status/disconnect/test + encrypted-token model to mirror.
