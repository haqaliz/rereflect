# Understanding: Microsoft Teams notification integration

**Slug:** `teams-notifications` — worktree `feat-teams-notifications`

## What this is really asking

Close the last named-but-missing outbound notification provider. `Integration.type`
(`services/backend-api/src/models/integration.py:13`) and `feedback_source.py:16` both
reserve `'teams'`; nothing implements it. Outbound alerts are Slack + Discord + email +
dashboard. Teams completes the notification surface for Microsoft-365 orgs, BYO webhook
URL — no OAuth, no vendor lock-in, fits the OSS/self-hosted posture.

## Affected areas (from the dig)

| Service | Seam |
|---|---|
| backend-api | `integrations.py` — `POST /discord/webhook` (:416), `POST /discord/test` (:464) + Discord host validator (:151-166), `send_discord_message` (:303-329) are the Teams templates. No type migration needed (comment already names `teams`); webhook URLs live plaintext in `config` like Discord. |
| backend-api | `automation_engine.py` — `KNOWN_NOTIFY_CHANNELS = {"dashboard","email","slack"}` (:35) + slack org-wide branch in `_execute_notify` (:611-667); result shape `{"notifications_created", "slack_sent", "error"}` (:679-683). |
| worker-service | `tasks/alerts.py:226-284` — the **single** low-level sender home (slack webhook, discord webhook, slack oauth). Teams sender is a sibling here. |
| worker-service | `notification_dispatch.py` — `dispatch_health_drop_alert` (:333-536, `_dispatch_slack/_discord_health_alert` :97-177), `dispatch_alert` (:578-672), counts keys `{"inapp","slack","discord","email"}` (:361,:607). |
| worker-service | `automation_feedback_trigger.py` — mirror `KNOWN_NOTIFY_CHANNELS` (:87) + slack branch (:763-811). |
| worker-service | `playbook_engine.py` — `_handle_notify` (:580-722) with slack/discord/dashboard branches + generic `_dispatch_external_notify` (:725-747). |
| worker-service | `models/__init__.py:390-408` — `UserAlertPreference` has `channel_slack`/`channel_discord`/…; a `channel_teams` column is the Discord-parity move (P5 precedent). |
| frontend-web | Integrations list `page.tsx` — test-dispatch ternary (:178-180), icon/color ternary (:301-317), and the **"Microsoft Teams — Coming Soon" placeholder tile (:1447-1465)** to replace. `new/page.tsx` Discord webhook branch (:38,:160,:205-230,:489-519) + detail `[id]/page.tsx` (:167-169,:281-295,:311-315,:369-374,:518); `lib/api/integrations.ts` needs `createTeamsWebhook` + `testTeams`; notifications `CHANNEL_CONFIG` (:120-126) + `renderChannelIcon` (:276-287) for a `channel_teams` toggle; `PlaybookEditor.tsx` `NOTIFY_CHANNELS` (:32-38). New `components/icons/TeamsIcon.tsx` (brand `#6264A7`). |
| landing-web + docs | `lib/integrations.ts` entry (Slack entry :96-134 is the template), README.md:62 outbound row, SELF_HOSTING.md privacy table (:142), Discord alerts section (:763-808) template, automations notify claim (:1004-1007). |

## Duplication state (P7, DEV-TRACKING:237-244)

Selection loops duplicated ~8× (worker) + ~2× (backend); low-level senders are **1× in
the worker** (`alerts.py:226-284`) and 2× in the backend (`integrations.py:303, :332`).
Decision: add Teams as a sibling sender per process (bounded), do **not** refactor
Slack/Discord paths. Record the P7 decision in the planning docs.

## Ambiguities / open questions for the interview

1. **URL validation:** accept classic Incoming Webhook (`outlook.office.com/webhook/…`)
   and/or the Workflows URL (`*.webhook.office.com/webhookb2/…`, `*.logic.azure.com`)?
   Discord precedent validates host + path prefix — Teams should mirror.
2. **Payload format:** MessageCard (`@type: "MessageCard"`, `themeColor: 6264A7`) is the
   pragmatic choice — works with classic webhooks and the Workflows connector. Confirm
   over Adaptive Cards.
3. **Per-user preference:** add `UserAlertPreference.channel_teams` (migration + toggle,
   Discord P5 parity, default true/opt-out) or org-wide-only v1?
4. **Which notify surfaces:** automations `send_notification` (backend + worker mirror)
   **and** playbook `notify` action (`playbook_engine` + editor)? Card says both; confirm.
5. **Inbound:** `feedback_source.py:16` names teams as a source type — explicitly out of
   scope for v1 (outbound only), documented as such.
6. **Docs honesty:** README + landing + SELF_HOSTING updated in the same PR; landing
   placeholder tile → live tile.

## Contradictions / flags

- DEV-TRACKING P2/P5 twice excluded Discord from the automations notify channel because
  "no channels editor". There is now a channels select in the playbook editor
  (`PlaybookEditor.tsx:32-38`) but still no per-channel editor for automations rules.
  Teams should not wait on that editor (out of scope here, unchanged).
- The `slack` result key (`slack_sent`) is Slack-named in the automation result shape —
  a Teams branch must not repurpose it; add a parallel key or fold into the same count
  honestly (open question for the dig/plan).