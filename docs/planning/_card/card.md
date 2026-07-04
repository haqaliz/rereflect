# Card: feat/jira-integration (freeform)

**Type:** feat · **Slug:** `jira-integration` · **Branch:** `feat/jira-integration`
**Source:** Freeform task from the `rereflect-next` recommendation handoff (verified against git — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-04

---

## Brief (verbatim from handoff)

Build a Jira integration for Rereflect, following the already-shipped **Linear** integration
as the structural blueprint (`linear_client.py`, `linear_integration` model + migration,
`linear_webhook.py`, `lib/api/linear.ts`, the `create-issue` wizard, and the Linear test
suite).

**Slice 1:** connect Jira **Cloud via an Atlassian API token (email + token, Basic auth)** —
NOT the 3LO marketplace OAuth, which is awkward to self-host (HubSpot's private-app token is
the precedent to follow); then create a Jira issue from a feedback item and add `jira` as a
feedback-source type.

All features unlocked (OSS self-hosted — do **not** re-add the Pro+ plan gating Linear carries).
Defer Jira Server/Data Center and OAuth 3LO to v2, and flag that caveat in the plan so the dig
isn't surprised by it.

## Provenance / roadmap references

- `DEV-TRACKING.md:189` — "M3.2 — JIRA Integration (2-3 weeks)", fully unchecked (`- [ ]`).
- `DEV-TRACKING.md:183` — JIRA listed as pending in the integration backlog; Linear shipped.
- `AI-TRACKING.md` strategic decisions — integrations are part of the moat (product breadth +
  integrated workflow + developer surface).
- Guardrail: OSS self-hosted, MIT, BYOK — all features unlocked, **no plan gating** (the
  `Pro+`/`Business+` framing in CLAUDE.md / AI-TRACKING is pre-pivot and stale).

## Scope (slice 1)

- **Connect** one Jira Cloud site per org via Atlassian **API token (email + token, Basic auth)**
  — BYOK, pasted by the self-hoster; mirror HubSpot's private-app-token connection shape.
- **Create a Jira issue** from a feedback item (project + issue type selection), mirroring the
  Linear `create-issue` wizard.
- **`jira` feedback-source type** so Jira can be picked as a source (mirror Linear's
  `requires_integration=false` own-auth pattern — Jira uses its own token, not the generic
  Integration OAuth model).

## Explicitly deferred (later slices / v2)

- Jira **Server / Data Center** (only Cloud in slice 1 — different base URL + auth).
- Atlassian **OAuth 2.0 (3LO)** marketplace flow.
- Inbound **webhook** receiver (pull Jira comments/status back as feedback context).
- Team/project/status field **mappings** UI beyond the minimum needed to create an issue.
- Two-way status sync / issue back-linking beyond storing the created issue key+URL.

## Why (moat / fit)

- The named next integration in the backlog (`DEV-TRACKING.md:189`, unchecked) and genuinely
  unbuilt (grep of `services/` → only build artifacts + a generic `create-issue` page).
- A proven, tested in-repo blueprint exists (Linear shipped end-to-end) → depth-first, low-risk.
- Deepens the integrations + developer-surface moat pillar; fits OSS/self-hosted/BYOK — the
  operator connects their own Jira with their own token, all features unlocked.

## Known caveat (carry into PRD)

Atlassian's OAuth 2.0 (3LO) marketplace flow is awkward for self-hosting (callback registration,
per-tenant app). Slice 1 uses **Jira Cloud + an Atlassian API token (email + token, Basic auth
against `https://{site}.atlassian.net`)**, mirroring HubSpot's private-app-token BYOK precedent.
Defer Jira Server/Data Center and 3LO OAuth to v2. **Copy Linear's *structure*, not its OAuth
auth mechanism** — the connection model differs (token paste, not an OAuth redirect).

## In-repo blueprint (Linear — shipped, tested; verified present on master)

- `services/backend-api/src/services/linear_client.py`
- `services/backend-api/src/models/linear_integration.py`
- `services/backend-api/src/api/routes/linear_webhook.py`
- `services/backend-api/alembic/versions/5ee1b2567a02_add_linear_integration_tables.py`
- `services/backend-api/tests/test_linear_{client,oauth,webhook,issues,models,config,plan_gating}.py`
- `services/frontend-web/lib/api/linear.ts`
- `services/frontend-web/app/(dashboard)/feedbacks/[id]/create-issue/page.tsx`
- `services/landing-web/app/integrations/linear/page.tsx`
- HubSpot connection (token-paste BYOK precedent for the *auth* shape):
  `services/backend-api/src/api/routes/hubspot_integration.py`, `src/models/hubspot_integration.py`

## Open questions for the interview (seed)

- Connection storage: new `jira_integrations` table (mirror `linear_integrations`) vs. the generic
  `integrations` model — Linear chose its own tables; likely mirror that.
- One Jira site per org, or many? (Slice-1 default: one, like HubSpot's one-CRM guard.)
- Create-issue field set: project + issue type + summary + description only, or also priority/labels/assignee?
- Where does the connect UI live: `settings/integrations/jira` detail page (mirror HubSpot) + a tile on the integrations index.
- Do we validate the token on connect (a `myself`/`serverInfo` GET), like HubSpot's Test?
- Field for the created issue back-reference: store `{issue_key, issue_url}` on the feedback or in a mapping table?
