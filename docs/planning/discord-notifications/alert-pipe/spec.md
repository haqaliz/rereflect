# Spec — `alert-pipe`

**Parent PRD:** `../prd.md` · Three parallel tracks (backend / worker / frontend)

## THE CONTRACT — Discord webhook payload

Discord webhooks accept a JSON body that **must** contain `content` and/or `embeds`.
Posting anything else returns **400**. Always send both: `content` as a short plain-text
fallback (it is what shows in notification previews), `embeds` for the formatted body.

```jsonc
{
  "content": "Rereflect: urgent feedback",          // short plain fallback
  "embeds": [{
    "title":       "Urgent feedback from acme@example.com",
    "description": "Body text in DISCORD markdown",
    "url":         "https://app.example.com/feedbacks/123",  // makes title a link
    "color":       15548997,                          // decimal, not hex string
    "fields":      [{"name": "Sentiment", "value": "negative", "inline": true}],
    "timestamp":   "2026-07-29T12:00:00.000Z"         // ISO 8601
  }]
}
```

Constraints that will bite if ignored:
- `color` is a **decimal integer**, not `"#ff0000"`.
- Max **10** embeds per message; max **25** fields per embed. Truncate, do not error.
- `description` ≤ 4096 chars; total embed payload ≤ 6000. Truncate with an ellipsis.
- **Discord markdown, not Slack mrkdwn.** `**bold**` not `*bold*`; `>` quote works;
  Slack's `<url|text>` link syntax does **not** — use `[text](url)`.
- Discord webhooks cannot render buttons. Where the Slack builder emits an `actions` block
  with a button (`build_health_alert_blocks`), put the URL in the embed's `url` or body.

## Sender contracts — DO NOT MIX (PRD R1)

| Process | Function | On failure |
|---|---|---|
| backend-api `src/api/routes/integrations.py` | `send_discord_message(webhook_url: str, embeds: list, content: str = "Rereflect Alert") -> dict` | catch `httpx.HTTPError`, return `{"success": False, "error": str(e)}` — **never raises** |
| worker-service `src/tasks/alerts.py` | `send_discord_message_webhook(webhook_url: str, embeds: list, content: str) -> Dict` | let it **raise** (`response.raise_for_status()`, nothing caught) |

Mirror `send_slack_message:216` and `send_slack_message_webhook:208` respectively, including
the fact that the worker version takes `content` as a **required** positional.

---

## Track A — backend (`services/backend-api`)

- **A1** `send_discord_message` in `src/api/routes/integrations.py`, next to
  `send_slack_message` (:216), returns-dict contract.
- **A2** `DiscordWebhookCreateRequest` mirroring `SlackWebhookCreateRequest` (:57-71). URL
  validator accepts **only** `https://discord.com/api/webhooks/` or
  `https://discordapp.com/api/webhooks/` (legacy host, still issued by old servers). Reuse the
  `triggers` (:73-80) and `included_fields` (:82-93) validators verbatim — they are
  provider-neutral.
- **A3** `POST /discord/webhook` creating `Integration(type="discord", config={"webhook_url":
  ..., "integration_type": "webhook"})`. No OAuth path — Discord webhooks need none.
- **A4** Make the Test button work for Discord (PRD R3): `/slack/test` filters
  `Integration.type == "slack"` at :413 so a Discord row 404s. Add `POST /discord/test` or
  generalise the existing route. Your choice; it must work and be tested.
- **A5** Tests in `tests/test_integrations.py`, mirroring `test_create_slack_webhook_success`
  (:84) and especially **`test_create_slack_webhook_invalid_url` (:111)** — the validator
  test. Cover: valid `discord.com`, valid `discordapp.com`, rejected `hooks.slack.com`,
  rejected arbitrary https, and the test route.
- **DO NOT** add a `require_feature("discord_integration")` gate. `SELF_HOSTED=true` makes
  these inert and adding gates is a known regression class here.
- **DO NOT** create an Alembic migration — `Integration.type` is an unconstrained `String(50)`.

## Track B — worker (`services/worker-service`)

- **B1** `send_discord_message_webhook` in `src/tasks/alerts.py` next to
  `send_slack_message_webhook` (:208). **Raising** contract.
- **B2** Embed builders alongside the existing block builders, **same argument lists** so call
  sites only branch on `integration.type`:
  - `build_discord_health_alert_embeds(...)` beside `build_health_alert_blocks`
    (`src/notification_dispatch.py:100-184`). The Slack version's `actions`/button block has
    no Discord equivalent — put the customer URL in the embed `url`.
  - inline embed construction for the two single-section sites.
- **B3** Discord dispatch at all **three** alert sites, each fanning out over
  `Integration.type == "discord"`, `is_active == True`, mirroring the Slack loop:
  - `notification_dispatch.py::_dispatch_slack_alert` (~:501) — the main pipe
    (`urgent_feedback`, `sentiment_spike`, `churn_risk`, `volume_spike`).
    **Must write back `last_used_at` / `error_count` / `last_error` exactly as the Slack
    version does (:566-573)** or the integration-health UI silently goes stale.
  - `notification_dispatch.py::_dispatch_slack_health_alert` (~:59)
  - `tasks/anomaly.py::_send_anomaly_slack` (~:219) — **easy to miss, not in
    notification_dispatch.py**
  > **Note (2026-08-18, `worker-cleanup-smalls`):** the third site no longer exists —
  > `_send_anomaly_slack` (and its Discord twin) were never wired and were deleted.
  > Anomaly alerts route through the main pipe: `_dispatch_anomaly_alerts` →
  > `dispatch_alert` → `_dispatch_slack_alert` / `_dispatch_discord_alert`.
- **B4** Tests: patch at the **import site** (`src.services.<module>.send_discord_message_webhook`
  / `src.tasks.anomaly...`) because these modules import at module top. Getting this wrong
  gives a test that passes while patching nothing. Assert the raising contract is caught and
  recorded, per-integration, without aborting the others.
- **B5** Assert the payload actually contains `embeds` (and `content`) — a Discord payload
  missing both is the 400 this whole feature exists to fix.

## Track C — frontend (`services/frontend-web`)

- **C1** `components/icons/DiscordIcon.tsx` (none exists). Brand colour `#5865F2`.
- **C2** Widen `IntegrationType` at `settings/integrations/new/page.tsx:36` to include
  `'discord'`; add the provider tile (:202-214); ensure the OAuth/connection-method blocks
  (:261-320, :322-350) are **skipped** for Discord — it is webhook-only.
- **C3** Un-disable the "Coming Soon" Discord card at `settings/integrations/page.tsx:1347-1364`
  and link it to `/settings/integrations/new?type=discord`.
- **C4** **Fix the two-way ternaries that assume "not intercom means Slack"** — otherwise a
  Discord row renders with a Slack icon:
  `page.tsx:281-286` (icon + background), `page.tsx:160` (`testSlack` called for any row),
  `[id]/page.tsx:259` (unconditional `SlackIcon`), `[id]/page.tsx:149` (`testSlack`),
  `[id]/page.tsx:473` (Slack-mrkdwn help text — wrong for Discord).
- **C5** `lib/api/integrations.ts`: add `createDiscordWebhook` and `testDiscord` beside the
  Slack equivalents (:110, :124).
- **C6** Tests. **Note there is no existing harness for the integrations pages** —
  `__tests__/settings/` has only webhook and notification tests. These are net-new; test
  behaviour (correct icon rendered, correct API called per type), not the mock.

## Acceptance criteria

1. `POST /discord/webhook` with a `discord.com` URL → 201; with `discordapp.com` → 201.
2. Same with a `hooks.slack.com` URL or any other host → 422.
3. The Discord test endpoint posts a payload containing `embeds` and returns success.
4. An urgent-feedback alert reaches an active Discord integration via `dispatch_alert`.
5. That path updates `last_used_at` on success and `error_count`/`last_error` on failure.
6. A health-drop alert and an anomaly alert each reach Discord.
7. A failing Discord send is caught per-integration and does not abort the others.
8. A Discord row in the integrations list renders a Discord icon, not a Slack one.
9. Slack behaviour is entirely unchanged (all existing suites pass).

## Test commands

```
cd services/backend-api   && ./venv/bin/pytest tests/test_integrations.py -v
cd services/worker-service && SENTRY_DSN="" ./venv/bin/pytest tests/ -q      # baseline 1394 passed
cd services/frontend-web  && ./node_modules/.bin/vitest run                  # baseline 1507 passed
```

## Deliberately NOT abstracting

The Slack integration-selection loop is already duplicated three times and the sender twice.
Discord makes that a fourth and third copy. **We are not introducing a provider abstraction in
this branch** — it would touch every Slack path at once, and the scope decision was to ship
the alert pipe. Log it as follow-up debt in DEV-TRACKING instead of half-doing it here.
