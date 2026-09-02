# PRD: Microsoft Teams Notification Integration

**Slug:** `teams-notifications` · **Branch:** `feat/teams-notifications` · **Date:** 2026-09-02
**Type:** feat (freeform) · **Source:** `rereflect-next` recommendation + user-confirmed scope

## Problem Statement

Outbound alerts reach Slack, Discord, email and the in-app dashboard — but not Microsoft
Teams, even though the codebase has reserved `'teams'` as a provider type since before the
OSS pivot (`services/backend-api/src/models/integration.py:13`,
`services/backend-api/src/models/feedback_source.py:16`). The landing page currently shows a
"Microsoft Teams — Coming Soon" placeholder tile
(`services/frontend-web/app/(dashboard)/settings/integrations/page.tsx:1447-1465`).

**For whom:** self-hosters on Microsoft 365 whose team lives in Teams — the churn/health
alerts, automations notifications and playbook notify actions all skip them today.
**Evidence it's real:** the reserved-but-unimplemented type comment; the shipped Discord
precedent (P2/P5, DEV-TRACKING.md:181-209) that established the exact provider shape; the
landing placeholder tile that over-promises.

## Goals & Success Metrics

- **Goal:** Teams becomes a first-class outbound notification provider, parity with the
  shipped Discord slice (connect via pasted webhook URL, test route, dispatch on every
  notification pipe, per-user channel preference).
- **Measured by:** (1) an operator can connect a Teams webhook URL end-to-end and see a
  test card; (2) health-drop alerts, generic alerts, automation `send_notification`
  actions and playbook `notify` actions all reach Teams; (3) per-user `channel_teams`
  toggle behaves exactly like `channel_discord` (default on, opt-out, decoupled from the
  Slack toggle); (4) no regression in the Slack/Discord paths (characterization tests
  stay green); (5) the landing "Coming Soon" tile is replaced by a live tile, and README /
  SELF_HOSTING / landing claims match reality.
- **Non-goal metrics:** no adoption/usage numbers — this is a parity slice; success is
  honest, working parity.

## User Personas & Scenarios

- **Operator (self-hoster, M365 shop):** connects a Teams Incoming Webhook URL in
  Settings → Integrations, hits "Test", sees a brand-colored card in their channel.
- **Team member:** opts out of Teams alerts per notification type via Settings →
  Notifications (mirrors the Discord toggle).
- **CS lead:** a churn-triggered playbook runs `notify` with `channel: "teams"` and the
  action log shows it posted; a `send_notification` automation rule with `channels:
  ["teams"]` posts org-wide once per firing.

## Requirements

### Must-have

1. **Backend connector** — `POST /api/v1/integrations/teams/webhook` (webhook URL pasted
   into `config.webhook_url`, validated by host + path prefix; mirror the Discord route
   shape `integrations.py:416`), `POST /api/v1/integrations/teams/test` (posts a test
   card, updates `last_used_at`/`error_count`, mirror `:464`), and a `send_teams_message`
   backend sender (never-raise `{"success": bool, ...}` contract, mirror
   `send_discord_message` `:303-329`). CRUD/logs endpoints are type-agnostic and reused
   (`GET/PATCH/DELETE /integrations/{id}`, `GET /{id}/logs`). Webhook URL stored
   plaintext in `config`, same as Discord — no encryption, no OAuth.
2. **URL validation** — accept the two real webhook shapes: classic Incoming Webhook
   (`https://outlook.office.com/webhook/…`) and the Workflows connector
   (`https://<tenant>.webhook.office.com/webhookb2/…`). Anything else → 422 with a
   human-readable message.
3. **Payload** — MessageCard (`@type: "MessageCard"`, `@context`,
   `http://schema.org/extensions`, `summary`, `title`, `text`, `themeColor: "6264A7"`).
   Works with both classic webhooks and the Workflows connector. Plain-text fallback when
   the caller has only text (health-drop path mirrors the Slack text/block split).
4. **Worker dispatch** — `send_teams_message_webhook` sibling to
   `alerts.py:226-284` (raise-on-failure contract, 10s timeout); Teams branches in
   `notification_dispatch.py` `dispatch_health_drop_alert` (:333-536) and `dispatch_alert`
   (:578-672) org-wide per org, gated the same way as Slack/Discord; counts keys gain
   `"teams"` (:361, :607).
5. **Automations notify** — `KNOWN_NOTIFY_CHANNELS` gains `"teams"` in the backend engine
   (`automation_engine.py:35`) and the worker mirror (`automation_feedback_trigger.py:87`);
   an org-wide Teams branch mirrors the Slack branch (`automation_engine.py:611-667`).
   Result shape gains a parallel `teams_sent` key; `slack_sent` is **not** renamed (would
   break execution-log rendering and characterization tests).
6. **Playbook notify** — `playbook_engine.py` `_handle_notify` gains a `channel == "teams"`
   branch beside discord (:662-691) via the generic `_dispatch_external_notify` helper;
   the frontend `PlaybookEditor` `NOTIFY_CHANNELS`/`NOTIFY_CHANNEL_LABELS` (:32-38) and
   `lib/api/playbooks.ts` channel union gain `'teams'`.
7. **Per-user preference** — `UserAlertPreference.channel_teams` (backend model + Alembic
   migration + worker mirror column + API round-trip with the `None = unchanged` sentinel,
   mirroring P5's `channel_discord`); Settings → Notifications gains the Teams toggle
   (default **on**, opt-out, decoupled from the Slack toggle).
8. **Frontend** — `TeamsIcon` component (brand `#6264A7`, mirrors `DiscordIcon.tsx`);
   replace the "Coming Soon" tile with a live tile linking to
   `/settings/integrations/new?type=teams`; Discord-style webhook branch in
   `new/page.tsx` (type union :38, validator, submit branch :160, header :205-230,
   placeholder :489-519) and detail page `[id]/page.tsx` (test dispatch :167-169, header
   :281-295, copy :311-315/:369-374/:518); `lib/api/integrations.ts` gains
   `createTeamsWebhook` + `testTeams` (+ non-Slack template-variables call if applicable).
9. **Docs & landing honesty** — landing `lib/integrations.ts` entry (`status:
   'available'`, mirror the Slack entry :96-134); README.md:62 outbound row gains Teams;
   SELF_HOSTING.md privacy table (:142), a "Teams alerts" section (mirror the Discord
   section :763-808), and the automations notify claim (:1004-1007). Optionally a sibling
   blog post (Slack post precedent `batch5.ts:7-75`).

### Should-have

- Discord-parity test coverage: backend connector suite, worker dispatch suite, frontend
  tile/page tests mirroring the `.discord.test.tsx` files.
- `feedback_source.py` comment cleanup or a one-line note that Teams inbound is out of
  scope (documented, not silently left).

### Nice-to-have

- Teams option in the "Test" dispatch ternary (`page.tsx:178-180`) with a dedicated test
  button icon/color.
- Blog post announcing Teams support.

## Technical Considerations

- **Services:** backend-api (routes, engine, model+migration), worker-service (senders,
  dispatch, mirrors), frontend-web (pages, api client, icons), landing-web (entry),
  docs.
- **No new deps** — httpx is already the HTTP client in both processes.
- **Multi-tenancy:** unchanged — all dispatch is org-scoped via `organization_id` and the
  existing `Integration` selection queries.
- **Duplication doctrine (P7):** add Teams as a sibling sender per process
  (`integrations.py` backend, `alerts.py` worker) — **no** provider-abstraction refactor
  of the Slack/Discord paths. The P7 decision is recorded here and in the planning docs.
- **The "two copies" doctrine:** the worker cannot import backend-api; every change is
  mirrored deliberately (engine vs `automation_feedback_trigger`, backend model vs worker
  mirror, sender pairs). Tests must pin both copies.
- **Migration:** one Alembic migration for `channel_teams` on `user_alert_preferences`,
  chained off the current single head (CI asserts one head).
- **API contracts:** new routes `POST /api/v1/integrations/teams/webhook`,
  `POST /api/v1/integrations/teams/test`; existing CRUD/logs reused.

## Risks & Open Questions

- **P7 duplication (known):** adding a fifth provider makes the 4×/3× duplication
  worse by one. Accepted deliberately — the abstraction was declined once
  (DEV-TRACKING P7) and a Teams slice must not balloon into a refactor.
- **Webhook flavors drift:** Microsoft's incoming-webhook story is in flux (classic vs
  Workflows). Mitigated by accepting both URL shapes and using MessageCard, which both
  accept. If a future URL shape appears, the validator is one function.
- **MessageCard rendering quality:** text-only rendering with title/summary; no
  markdown parity with Slack Block Kit. Honest limits stated in SELF_HOSTING.
- **`teams_sent` result key:** parallel to `slack_sent`, never repurposed. Execution-log
  surfacing reads both.
- **Blank `channel_name`:** Teams `config` stores only `webhook_url` (no channel/team
  name, unlike Slack's OAuth payload). `integration_to_response` and the detail page
  render `channel_name`/`team_name` — the Teams branches must hide or omit those fields
  rather than render blanks.
- **Discoverability limit:** the automations `channels` list has no editor; a rule can
  reach Teams only via an API-created rule or the playbook editor's notify-channel
  select. Stated honestly in SELF_HOSTING; the channels editor stays out of scope.
- **Open:** none blocking. (Inbound Teams source, automations channels editor, Teams
  OAuth — all explicitly out of scope.)

## Out of Scope

- **Inbound Teams feedback source** (`feedback_source.py:16` reserves it) — outbound
  notifications only in slice 1.
- **Teams OAuth / app registration** — webhook-URL connect only, matching the
  Zendesk/Jira/Asana/Intercom BYO-token precedent.
- **Automations channels editor** — still does not exist; Teams lands on the hardcoded
  channel list like Slack and Discord do (unchanged, documented).
- **Adaptive Cards / rich payloads** — MessageCard only.
- **The P7 provider-abstraction refactor** — recorded, not executed.
- **Per-user custom webhook routing / multiple Teams channels per org** — one org-wide
  integration, same as Slack/Discord.