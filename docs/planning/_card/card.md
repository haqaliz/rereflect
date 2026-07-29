# Card — Intercom/Zendesk ingestion: shipped, invisible, and half-documented

**Type:** chore (docs/marketing) · **Slug:** `ingestion-source-visibility`
**Branch:** `chore/intercom-zendesk-docs`
**Source:** Freeform — no GitHub issue. **DEV-TRACKING P1**, *Post-1.0.0 User Feedback
Backlog*, opened 2026-07-29 (batch 2).

---

## The user's words

> "Love the BYOK setup and self-hosted angle, feels rare these days. One thing that would
> make it way more useful for me is integrating directly with **Intercom or Zendesk so
> feedback flows in automatically** instead of pasting tickets manually. Would save a ton of
> time on weekly reviews."

Triaged against the shipped code on 2026-07-29. **Both integrations already exist.** The
user could not find them. Same class as the P3 analytics-trends discoverability item — with
the difference that one half of the ask (Intercom) is genuinely unreachable on a fresh
self-host.

## What is actually true in the code

| | Zendesk | Intercom |
|---|---|---|
| Connect method | subdomain + agent email + API token (BYO token) | **OAuth only** |
| Operator env vars needed | none (per-org, in-app) | `INTERCOM_CLIENT_ID`, `INTERCOM_CLIENT_SECRET`, `INTERCOM_REDIRECT_URI` |
| Those env vars documented | n/a | **nowhere** |
| Pull / polling ingestion | real incremental poller | **unimplemented placeholder** |
| Webhook ingestion | yes (HMAC-SHA256, fails closed) | yes (HMAC-SHA1, **skips verification if secret unset**) |
| `SELF_HOSTING.md` section | yes, "Connecting Zendesk" | **none** |
| Registered source type | `available=True` | `available=True` |

Evidence (all verified 2026-07-29, not inferred):

- `services/backend-api/src/api/routes/feedback_sources.py::list_source_types` registers
  `slack`, `intercom`, `webhook`, `linear`, `jira`, `zendesk`, `asana` all with
  `available=True`. Only `discord` and `email` differ.
- `services/backend-api/src/api/routes/integrations.py:34-36` reads the three `INTERCOM_*`
  env vars; line 754 raises **500** *"Intercom OAuth is not configured. Set
  INTERCOM_CLIENT_ID environment variable."* when the client id is empty. (Corrected — the
  initial triage called this a 403; it is a 500. There is **no** role check on these routes
  at all, which is its own finding — see the understanding note.)
- `INTERCOM_REDIRECT_URI` defaults to `http://localhost:8000/api/v1/integrations/intercom/oauth/callback`,
  so every non-localhost deployment **must** override it and register the same value in the
  Intercom app.
- Those three vars appear in **no** `.env.example`, **no** `.env.prod.example`, **neither**
  docker-compose file, and **nowhere** in `docs/SELF_HOSTING.md`.
- `services/backend-api/src/api/routes/source_webhooks.py:276`
  `POST /api/v1/webhooks/intercom/events` — HMAC-SHA1 over the raw body via the
  `X-Hub-Signature` header, keyed by `INTERCOM_CLIENT_SECRET`. `verify_intercom_signature`
  (line 256) **skips verification with a warning** when the secret is unset, unlike Zendesk
  which fails closed — the contrast is called out in `_verify_zendesk_signature`'s docstring.
- `services/worker-service/src/tasks/integrations.py:167` `IntercomConnector.fetch_new_items`
  logs `"IntercomConnector.fetch_new_items called (not implemented)"` and returns nothing —
  *"TODO: Implement actual Intercom API integration in Month 2"* — while line 30 still
  selects `Integration.type.in_(["intercom", "zendesk"])` for polling.
- `README.md:38` and `README.md:61` both describe inbound sources as "CSV, email, webhooks
  and Slack", omitting all five of Zendesk, Intercom, Jira, Linear, Asana.
- `services/landing-web/lib/integrations.ts:147` sells Intercom as
  *"Authorize via OAuth in one click."*

## Scope — in

1. **README source list.** Fix `README.md:38` and `README.md:61` to reflect what ships,
   distinguishing **inbound sources** (CSV, email, webhooks, Slack, Zendesk, Intercom) from
   **outbound work-management targets** (Jira, Linear, Asana).
2. **Intercom setup docs** in `docs/SELF_HOSTING.md`, mirroring the existing "Connecting
   Zendesk" section (~line 1330): creating the Intercom app, the three env vars, the webhook
   endpoint + HMAC-SHA1 verification, and the handled conversation topics.
3. **`.env.prod.example`** — add the three `INTERCOM_*` vars.
4. **State the webhook-only limitation honestly.** Intercom has no pull path; if the webhook
   is not wired, nothing arrives. The user's ask was "flows in automatically", which is
   exactly the missing path, so this must not be glossed.
5. **Consider softening** `services/landing-web/lib/integrations.ts:147`, which promises
   one-click OAuth that in fact requires undocumented operator setup.

## Scope — out (recorded as P1 Part B follow-ups in `DEV-TRACKING.md`)

- Implementing `IntercomConnector.fetch_new_items` against the Conversations API.
- Adding a token-paste (non-OAuth) Intercom connect path following the
  Zendesk/Jira/Asana BYO-token precedent.

**No backend, worker or frontend application code changes.** Docs, example env, and
marketing copy only.

## Why it matters

Zendesk already fully satisfies the user's ask and they did not know. Intercom is marketed
on the landing page and offered in the UI, but errors out on a fresh self-host with no
documented remedy — the same credibility problem as the P0 automations bugs, on the
acquisition path instead of the notification path.

## Open questions for the PRD

- Is the missing-secret **signature-verification skip** on the Intercom webhook in scope to
  *document as a warning*, out of scope entirely, or serious enough to escalate as its own
  security item? (It is a real fail-open on an unauthenticated public endpoint.)
- Does the landing-page copy get softened, or does documenting the setup make the
  "one click" claim true enough to leave alone?
- Does `.env.example` (the minimal local-dev file) get the vars too, or only
  `.env.prod.example`?
