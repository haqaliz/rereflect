# Card: Microsoft Teams notification integration

**Type:** feat (freeform, no GitHub issue)
**Slug:** `teams-notifications`
**Branch:** `feat/teams-notifications`
**Source:** `rereflect-next` recommendation (2026-09-02), verified against code

## Brief

Build the Microsoft Teams notification integration — the only provider still
named-but-missing in the codebase. `Integration.type` reserves `'teams'` alongside
`'slack'`/`'discord'` (`services/backend-api/src/models/integration.py:13`), and
`feedback_source.py:16` also names Teams as a source type — neither exists anywhere in
the shipped surface. Outbound alerts today are Slack + Discord + email + dashboard;
Teams is the gap for Microsoft-365-heavy orgs and fits the OSS/BYOK model (paste an
Incoming Webhook URL — no vendor lock-in, no OAuth).

## Verified facts (from code)

- `services/backend-api/src/models/integration.py:13` — `type = Column(String(50))` with
  comment `# 'slack', 'discord', 'teams'` — Teams named, never implemented.
- `services/backend-api/src/models/feedback_source.py:16` — `# Source type: slack, discord, teams, email, webhook, api` — Teams also named as a source type, never implemented.
- DEV-TRACKING.md:237-244 (P7) — integration-selection loop duplicated 4×, low-level
  sender 3× across the two processes; "Adding a fifth provider (Teams is already named in
  the `Integration.type` comment) means another full round." Refactor explicitly declined
  once (Discord work, 2026-07-29) — scope discipline, not avoidance.
- DEV-TRACKING.md P2 (2026-07-29) — the Discord slice is the pattern to mirror: provider
  CRUD + test route, a sender per process (backend returns a status dict, worker raises),
  dispatch on the main alert pipe and the health-drop path.
- DEV-TRACKING.md P2/P5 — the automations engine `_execute_notify` channel list remains
  dashboard/email/slack (Discord excluded twice, "no channels editor"); Teams should be
  wired into the automations notify branch **and** its worker mirrors.

## Proposed scope (slice 1)

1. Teams connector: Incoming-Webhook URL connect (Settings → Integrations tile + token-paste
   page + CRUD + test route, Fernet-encrypted, mirroring the Discord/Zendesk/Jira/Asana
   BYO-token precedent).
2. `send_teams_message` sender per process — backend returns a status dict, worker raises —
   matching the existing Slack/Discord contract.
3. Dispatch wiring: main alert pipe + health-drop path, plus the automations
   `_execute_notify` branch and its worker mirrors.
4. README + landing integration row update in the same PR so the claim is honest on day one.

## Known caveat (P7)

The integration-selection/sender logic is duplicated 4×/3× (DEV-TRACKING.md P7). Prefer a
**bounded shared sender** for the new Teams path + automations branch over a full provider
abstraction (that refactor touches every Slack path and was explicitly declined once).
Record the P7 decision in the planning docs.

## Open questions (for the dig / interview)

- Teams webhook flavor: classic Incoming Webhook vs Power Automate Workflows URL — accept
  both? Validate by URL shape?
- Payload format: simple `messageCard`/adaptive card vs plain text — what does the existing
  Slack Block Kit formatter pattern imply?
- `feedback_source` Teams source type: in scope or explicitly out (outbound only)?
- Automations channels editor: still out of scope, or does Teams land on a hardcoded
  `channels` list like Slack did?