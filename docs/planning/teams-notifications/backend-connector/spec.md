# Spec: backend-connector

## Problem slice

The backend can connect, validate, test and send to a Teams webhook — the provider
plumbing Slack/Discord already have in `services/backend-api/src/api/routes/integrations.py`.

## In-scope

- `POST /api/v1/integrations/teams/webhook` — webhook URL in `config.webhook_url`,
  mirroring `POST /discord/webhook` (:416).
- URL validator: accept `https://outlook.office.com/webhook/…` (classic) and
  `https://<tenant>.webhook.office.com/webhookb2/…` (Workflows); else 422 with a
  human-readable message. One validator function, unit-tested.
- `POST /api/v1/integrations/teams/test` — posts a MessageCard test card, updates
  `last_used_at`/`error_count` bookkeeping (mirror `:464`, :512-523).
- `send_teams_message(webhook_url, title, text, summary) -> dict` sender with the
  never-raise `{"success": bool, ...}` backend contract (mirror `send_discord_message`
  :303-329). MessageCard builder: `@type: "MessageCard"`, `@context:
  "http://schema.org/extensions"`, `summary`, `title`, `text`, `themeColor: "6264A7"`.
- Reuse type-agnostic `GET/PATCH/DELETE /integrations/{id}` + `GET /{id}/logs`.
- No encryption (webhook URL plaintext in `config`, Discord precedent); no OAuth.

## Out-of-scope

Adaptive Cards; multiple channels per org; inbound source; P7 refactor.

## Acceptance criteria

- Connect with a valid classic URL → 200, `integration_type` reflects webhook.
- Connect with a valid Workflows URL → 200.
- Connect with `https://example.com/…` → 422, message names the accepted hosts.
- Test posts a MessageCard body (`@type == "MessageCard"`, `themeColor == "6264A7"`),
  increments `last_used_at`, sets `error_count` on failure without raising.
- Sender returns `{"success": false, "error": ...}` on HTTP error (never raises).
- `integration_to_response` (:275) does not emit blank `channel_name`/`team_name` for
  Teams (config has neither — omit the fields rather than render empty strings).
- Slack/Discord characterization tests untouched and green.

## Dependencies / sequencing

First aspect (the worker, engine and frontend all import or call this shape).