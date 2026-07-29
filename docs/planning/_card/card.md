# Card — native Discord notification channel

**Type:** feat · **Slug:** `discord-notifications` · **Branch:** `feat/discord-notifications`
**Source:** direct v1.0.0 user request. No GitHub issue. **DEV-TRACKING P2.**

---

## The user's words

> "it would be great if you could plug in a **Slack or Discord** webhook to get pinged
> whenever a batch of new feedback crosses a certain sentiment threshold."

Third and last piece of that one sentence. The other two shipped:

| Piece | Status |
|---|---|
| Slack delivery actually works | `52c763dd` — the `slack` channel was silently dropped and logged as success |
| The batch sentiment trigger | `7bd735be` — `batch_sentiment_threshold`, first org-wide trigger |
| **Discord delivery** | **this card** |

## Why Discord isn't just "another webhook URL"

Rereflect already has generic outbound webhooks (Settings → Webhooks) and the URL validator
accepts any `https://` URL — so a Discord webhook URL *saves fine today*. It just doesn't
work: the dispatcher posts Rereflect's own JSON envelope, and Discord's webhook API requires
a body containing `content` or `embeds`. Discord replies **400**, and the failure only shows
in the delivery log.

So the gap is a **payload formatter**, not a transport. That is why this is a notification
channel rather than a webhook tweak.

## Decision already made

**Ship it as a `discord` notification channel**, mirroring the `slack` channel — `Integration`
rows with `type="discord"`, a `discord` member in `KNOWN_NOTIFY_CHANNELS`, and a Discord
embed formatter. Rejected: sniffing the URL in the generic webhook path, which would make
webhook behaviour depend on a hostname and still leave Discord unusable as an automation
notification channel.

Encouraging sign: `Integration.type`'s inline comment already reads
`# 'slack', 'discord', 'teams'` — the model anticipated this.

## The trap to avoid (learned the hard way this session)

The Slack senders have **two different error contracts**:

| Sender | Process | On failure |
|---|---|---|
| `send_slack_message` (`backend-api/src/api/routes/integrations.py:216`) | backend | returns `{"success": False, ...}`, **never raises** |
| `send_slack_message_webhook` (`worker-service/src/tasks/alerts.py:207`) | worker | **raises** |

The Discord senders must match the contract of whichever process they live in, and the
`_execute_notify` implementations differ accordingly. Mixing them up silently changes failure
semantics — the exact class of bug this session has fixed three times.

## Open questions for the PRD

- Which existing alert paths should also reach Discord? There are three separate Slack
  dispatch sites (`_dispatch_slack_health_alert`, `_dispatch_slack_alert`,
  `_send_legacy_slack_alerts`). Doing all of them is a much bigger job than the notify channel.
- Discord webhook URL validation: `discord.com/api/webhooks/` — but also the legacy
  `discordapp.com` host. Accept both? Reject non-Discord hosts like the Slack validator does?
- Embed vs plain `content`? Embeds look better and support fields/colour; `content` is
  simpler and never fails schema validation.
- Rate limits: Discord webhooks are ~5 requests/2s per webhook and return 429 with
  `retry_after`. Slack's sender ignores rate limiting entirely. Do we handle 429, or accept
  the same limitation for consistency?
