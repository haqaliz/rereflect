# PRD — Discord as an outbound alert destination

**Slug:** `discord-notifications` · **Branch:** `feat/discord-notifications`
**Type:** feat · **Created:** 2026-07-29 · **Card:** `../_card/card.md` · **DEV-TRACKING P2**

---

## Problem Statement

A v1.0.0 user asked to be pinged in "Slack **or Discord**". Slack works. Discord does not
exist as an outbound destination anywhere — every `discord` string in the repo today is a
comment, a disabled "Coming Soon" card, or part of the unrelated *inbound* feedback-source
system.

Pointing the generic webhook feature at a Discord URL does not work and cannot be made to:
the URL validator accepts any `https://` URL so it **saves**, but the dispatcher posts
Rereflect's own JSON envelope while Discord's webhook API requires a body containing
`content` or `embeds`. Discord returns **400**, visible only in the delivery log.

So the gap is a payload formatter plus a provider registration — not a transport.

## Scope decision (made with the full map in hand)

**In: the alert pipe and integration CRUD. Out: the automations notify channel.**

The notify channel (`channels: ["discord"]` in `_execute_notify`) was the original plan, and
it is the wrong first slice: **there is no channels editor anywhere in the automations UI.**
Both `new/page.tsx` and `[id]/page.tsx` hardcode `channels: ['dashboard']`, so today
`channels: ["slack"]` reaches the engine only via a seeded template or a direct API call.
Adding `"discord"` there would ship something a user cannot reach.

What users actually receive alerts from is `dispatch_alert` and friends. That is the slice.

---

## Requirements

### Must-have

- **R1 — Two senders, one per process, matching that process's error contract.** This is the
  single highest-risk requirement.

  | Process | Function | Contract |
  |---|---|---|
  | backend-api (`routes/integrations.py`) | `send_discord_message(...) -> dict` | returns `{"success": bool, ...}`, **never raises**, catching `httpx.HTTPError` — mirrors `send_slack_message:216` |
  | worker-service (`tasks/alerts.py`) | `send_discord_message_webhook(...) -> Dict` | **raises** on failure — mirrors `send_slack_message_webhook:208` |

  Reusing the returns-dict version in the worker makes every failure look like a success
  (callers only count successes after a non-raising call). Reusing the raising version in the
  backend turns a recorded `channel_errors` entry into an escaped exception. Both directions
  silently invert failure semantics — the exact bug class this session has fixed repeatedly.

- **R2 — Integration CRUD.** `DiscordWebhookCreateRequest` with a host validator accepting
  `https://discord.com/api/webhooks/` **and** legacy `https://discordapp.com/api/webhooks/`,
  rejecting anything else (mirroring the Slack validator's strictness so a pasted wrong URL
  fails at save time, not at first alert). `POST /discord/webhook`. Discord is
  **webhook-only** — no OAuth path.
- **R3 — Fix `/slack/test` for Discord.** It filters `Integration.type == "slack"`
  (`integrations.py:413`), so a Discord row's Test button 404s today. Either add
  `POST /discord/test` or generalise. Implementer's choice; the test must work.
- **R4 — Discord on the three real alert sites**, each with an embed builder alongside the
  existing Slack block builder, same argument list, branching on `integration.type`:
  - `worker-service/src/notification_dispatch.py::_dispatch_slack_alert` (~:501) — the main
    pipe: `urgent_feedback`, `sentiment_spike`, `churn_risk`, `volume_spike`. **Must also
    write back `last_used_at` / `error_count` / `last_error`** as the Slack version does
    (:566-573), or the integration-health UI goes stale.
  - `worker-service/src/notification_dispatch.py::_dispatch_slack_health_alert` (~:59)
  - `worker-service/src/tasks/anomaly.py::_send_anomaly_slack` (~:219) — easy to miss, it
    does not live in `notification_dispatch.py`.
  > **Note (2026-08-18, `worker-cleanup-smalls`):** the third site no longer exists —
  > `_send_anomaly_slack` (and its Discord twin) were never wired and were deleted.
  > Anomaly alerts route through the main pipe: `_dispatch_anomaly_alerts` →
  > `dispatch_alert` → `_dispatch_slack_alert` / `_dispatch_discord_alert`.
- **R5 — Frontend must not lie.** Today a Discord row would render with a **Slack icon** and
  a Test button that 404s. Fix the two-way `intercom ? … : Slack` ternaries
  (`integrations/page.tsx:281-286`, `:160`; `[id]/page.tsx:259`, `:149`), add a
  `DiscordIcon`, widen `IntegrationType` (`new/page.tsx:36`), and un-disable the Coming Soon
  card (`page.tsx:1347`).
- **R6 — Embeds, with `content` as fallback text.** Parity with the Block Kit path.
  `build_health_alert_blocks`' action **button** has no Discord webhook equivalent — move the
  customer URL into the embed body or an embed `url`.

### Explicitly out of scope

- **The automations notify channel** (`KNOWN_NOTIFY_CHANNELS`, both `_execute_notify`
  mirrors). Unreachable without a channel picker; tracked as follow-up.
- **A channels picker in the automations UI.** Net-new UI, no existing test harness.
- **`UserAlertPreference.channel_discord`** and its Alembic migration. Per-user Discord
  preference is a schema change; the org-level integration is the first slice.
- **`_send_legacy_slack_alerts`** (`alerts.py:316`). Its whole value is the user's custom
  `message_template`, authored in Slack `mrkdwn`, which does not render on Discord.
- **`response_sender.send_via_slack`** — inbound-reply, not alerting. Different axis.
- **Rate-limit handling.** Discord returns 429 with `retry_after`; Slack's sender ignores
  rate limiting and so does this. Consistency over a half-built retry path — documented.

---

## Technical Considerations

- **No migration.** `Integration.type` is an unconstrained `String(50)` — `type="discord"`
  rows are already legal. A migration would only be needed for the per-user preference
  column, which is out of scope.
- **No plan gate.** The Slack routes carry `require_feature("slack_integration")`, inert
  under `SELF_HOSTED=true`. Do **not** add a `discord_integration` gate.
- **Slack mrkdwn ≠ Discord markdown.** `*bold*` renders as literal asterisks on Discord.
  This is why the custom-template path is out of scope; new Discord payloads must be authored
  in Discord markdown (`**bold**`).
- **List/detail/update/delete routes are already provider-generic** — no `type` filter — so
  a Discord row flows through them unchanged. Only `/slack/test` filters.
- **Test patch targets differ by module, and getting it wrong yields a test that passes while
  patching nothing:**
  - backend imports the sender **lazily inside the loop** → patch at the definition site,
    `src.api.routes.integrations.send_discord_message`
  - worker imports at **module top** → patch at the import site,
    `src.services.<module>.send_discord_message_webhook`
- **No frontend test harness exists for the integrations pages** — `__tests__/settings/`
  has only webhook and notification tests. Discord UI tests are net-new.

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Mixing the two sender contracts silently inverts failure semantics. | R1, stated explicitly; assert both contracts in tests. |
| 2 | Missing `_send_anomaly_slack` because it is not in `notification_dispatch.py`. | Named explicitly in R4. |
| 3 | `SlackAlertLog` is only written by the legacy path, which is out of scope — so a Discord integration shows an **empty log list** in the UI. | Accept and document. Pre-existing asymmetry: the health and dispatch paths do not log for Slack either. |
| 4 | Users may expect per-user Discord toggles in Settings → Notifications. | Out of scope, documented. Org-level integration first. |

> **Note (2026-08-18, `worker-cleanup-smalls`):** risk 2 is moot — `_send_anomaly_slack`
> was never wired and was deleted; the main pipe already covered Slack + Discord anomaly
> delivery. See `docs/planning/worker-cleanup-smalls/`.

**Open question:** should the "Coming Soon" Discord card on the marketing site
(`landing-web/lib/integrations.ts`) be updated in this branch? *Leaning yes for the app card
(R5), no for landing-web — marketing copy is a separate concern from shipping the feature.*

---

## Self-critique (Phase 4)

- 🟡 **The slice deliberately leaves an inconsistency**: Discord will receive the four alert
  types and health/anomaly alerts, but not automation-rule notifications. A user who reads
  the docs carefully will notice. Justified (the channel is unreachable anyway) but it is a
  seam, and the docs must state it rather than let someone discover it.
- 🟡 **No test harness for the integrations UI** means R5's frontend work ships with
  net-new tests written against a page nobody has tested before — higher chance of testing
  the mock rather than the behaviour.
- 🟢 Sender contracts, alert sites and registration points are all enumerated from a verified
  map rather than assumed.

**The question I'd want answered before greenlighting:** we are adding a second delivery
provider to a codebase where the Slack integration-selection loop is already duplicated three
times and the sender twice. Does Discord make that duplication permanent, and should the
embed/block split be the moment to introduce a provider abstraction instead of a fourth copy?
