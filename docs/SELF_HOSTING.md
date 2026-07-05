# Self-Hosting Rereflect

Rereflect is open source (MIT) and designed to run entirely on your own
infrastructure. **All features are unlocked** on a self-hosted instance — there are
no paid tiers, seat limits, or feedback quotas. The `SELF_HOSTED=true` flag (the
default) treats every instance as fully featured.

- [Prerequisites](#prerequisites)
- [Quick start (Docker Compose)](#quick-start-docker-compose)
- [Required environment variables](#required-environment-variables)
- [Running with no API key ($0, fully local)](#running-with-no-api-key-0-fully-local)
- [Fully-local LLM, including the AI Copilot (Ollama / OpenAI-compatible)](#fully-local-llm-including-the-ai-copilot-ollama--openai-compatible)
- [Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok)
- [Send product-usage events](#send-product-usage-events)
- [Connecting HubSpot CRM enrichment](#connecting-hubspot-crm-enrichment)
- [Connecting Salesforce CRM enrichment](#connecting-salesforce-crm-enrichment)
- [Connecting Jira](#connecting-jira)
- [Connecting Zendesk](#connecting-zendesk)
- [Production notes](#production-notes)

## Prerequisites

- Docker + Docker Compose
- (Optional) Your own LLM API key for AI features — **not required**

## Quick start (Docker Compose)

The bundled `docker-compose.prod.yml` brings up Postgres, Redis, the backend, the
Celery worker and the frontend together.

```bash
# 1. Copy and edit the production env template
cp .env.prod.example .env

# 2. Generate the required secrets and fill them into .env (see below)

# 3. Build and start everything
docker compose -f docker-compose.prod.yml up -d --build
```

Then open the frontend at `http://localhost:3000` and log in with the `ADMIN_EMAIL` /
`ADMIN_PASSWORD` you set in `.env` (the first admin user is seeded on startup).

Generate the two required secrets:

```bash
# JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"

# LLM_ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Required environment variables

Set these in your `.env` (see [`.env.prod.example`](../.env.prod.example) for the full
annotated list):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret for signing auth tokens (random 32+ chars) |
| `LLM_ENCRYPTION_KEY` | Fernet key used to encrypt stored BYOK LLM keys |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeds the first admin account |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `SELF_HOSTED` | Keep `true` — unlocks all features |
| `ai_analysis_enabled` | `false` by default — runs on free local VADER |

## Running with no API key ($0, fully local)

Out of the box (`ai_analysis_enabled=false`, no LLM key), Rereflect runs the **free
local VADER + keyword analysis pipeline**. Sentiment, pain-point, feature-request, and
heuristic churn detection all work end-to-end with **no external API and no cost**.
This is the default and recommended starting point.

## Fully-local LLM, including the AI Copilot (Ollama / OpenAI-compatible)

You can run **every** AI feature — LLM analysis, the AI Copilot (natural-language
queries, NL→SQL, analysis, reports) **and** the Copilot's template matching — against a
local model with **no cloud API key at all**. Point Rereflect at [Ollama](https://ollama.com)
or any OpenAI-compatible endpoint (vLLM, LM Studio, LocalAI):

1. Run a model and an embedding model locally, e.g.:
   ```bash
   ollama pull llama3.1        # generation
   ollama pull nomic-embed-text # embeddings (used by the Copilot's template matching)
   ```
2. In the app, go to **Settings → AI** and set the provider to **Ollama /
   OpenAI-compatible** with the **Base URL** of your endpoint (e.g.
   `http://localhost:11434/v1`). No API key is required for local providers.

The Copilot generates and runs queries through your local model; the same SQL safety
checks (read-only, organization-scoped, join/row limits, timeouts) apply regardless of
provider. **Answer quality scales with the model you run** — a small local model may
produce weaker queries than a frontier cloud model, and when it can't produce a safe
query you get an honest "couldn't answer that with the current model" message rather than
a wrong-but-confident answer.

> Embeddings are provider/dimension-aware: switching the embedding model re-embeds the
> built-in query templates automatically on the next startup. Vectors from different
> providers are never mixed.

## Adding your own LLM key (BYOK)

To use a hosted frontier model for analysis and the AI Copilot instead of (or alongside)
a local one, bring your own key:

- **In-app (canonical):** Sign in, go to **Settings → AI**, and paste your OpenAI /
  Anthropic / Google key. Keys are encrypted at rest with `LLM_ENCRYPTION_KEY` (Fernet)
  and scoped per organization.
- **From env (single-tenant convenience):** You may also seed an operator key via
  `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_AI_API_KEY` in `.env`. This is
  treated as **your own key** for your own instance — Rereflect never provides or
  proxies a key.

There is no system/vendor key. If an organization has no key configured, AI features
degrade gracefully back to the free VADER pipeline rather than erroring.

## Send product-usage events

Rereflect can ingest per-customer product activity and surface it on the Customer 360
profile — giving you a real engagement signal alongside feedback-based health scores.

### How it works

1. **Create an ingest-scoped API key** in **Settings → API Keys**. Select the
   `ingest` scope. The key starts with `rrf_`.

2. **POST events** to the ingest endpoint:

   ```bash
   curl -X POST http://localhost:8000/api/v1/webhooks/usage \
     -H "X-API-Key: rrf_YOUR_INGEST_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "events": [
         {
           "type": "track",
           "email": "alice@acme.com",
           "event": "feature_used",
           "name": "export_csv",
           "timestamp": "2026-06-28T10:00:00Z",
           "messageId": "evt_abc123",
           "properties": { "plan": "team" }
         },
         {
           "type": "identify",
           "email": "alice@acme.com",
           "timestamp": "2026-06-28T10:01:00Z",
           "messageId": "evt_abc124",
           "traits": { "name": "Alice" }
         }
       ]
     }'
   ```

   The endpoint is Segment-compatible. Supported types: `track`, `identify`. Events
   are matched to customers by the `email` field; events without a resolvable email
   are skipped and counted in the `skipped` response field.

3. **Verify it's working**: open the customer's profile page. Within one Celery cycle
   (typically < 30 s), the **Usage Activity** card shows `Last Active`, login counts,
   and active-days.

4. **Optionally factor usage into health scores**: go to
   **Settings → Preferences** and raise the **Usage Activity** weight above 0
   (the five weights must sum to 100). The default is 0 so existing scores are
   unchanged until you opt in.

### Schema reference

| Field | Required | Notes |
|-------|----------|-------|
| `type` | Yes | `"track"` or `"identify"` |
| `email` | Yes | Identifies the customer — must match an email in your org |
| `event` | No | Machine-readable event key (e.g. `"login"`, `"feature_used"`) |
| `name` | No | Human-readable event/feature name |
| `timestamp` | No | ISO 8601; defaults to ingest time |
| `messageId` | No | Dedup key — safe to replay; idempotent |
| `properties` | No | Arbitrary JSON, max 16 KB |
| `traits` | No | For identify events (e.g. `{"name": "Alice"}`) |

Max batch size: **1 000 events per request**. Oversized requests return `413`.

### In-app docs

Full setup docs are also available in the app under
**Settings → Usage Events** (admin/owner only).

## Connecting HubSpot CRM enrichment

Rereflect can sync contacts and company data from HubSpot to enrich the Customer 360
profile (company name, lifecycle stage, ARR, renewal date, open deals). You can also
opt in to push customer health scores back to HubSpot as a custom contact property.
Only one CRM (HubSpot or Salesforce) can be connected per organization at a time.

### 1. Create a private-app access token in HubSpot

1. Log in to HubSpot and go to **Settings → Integrations → Private apps**.
2. Click **Create app**, give it a name (e.g., "Rereflect").
3. Under **Scopes**, enable the following (minimum required for read access):
   - `crm.objects.contacts.read`
   - `crm.objects.companies.read`
   - `crm.objects.deals.read`
4. Click **Create app**. Copy the **Access token** (it starts with `pat-`).

To enable health-score writeback (optional), also grant the write scope:
   - `crm.objects.contacts.write`

### 2. Connect from the app

The token is **not** set via an environment variable — it is pasted into the app and
stored encrypted per organization. (Encryption uses `LLM_ENCRYPTION_KEY`, which must
already be set on the backend — see [Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok).)

Go to **Settings → Integrations → HubSpot** (admin/owner only) and paste the access
token in the **Access Token** field. Click **Connect**. Rereflect will immediately
test the token and start syncing contacts and company data.

### Verify

- **Settings → Integrations → HubSpot** shows connection status, sync counts, and
  the last sync time once the first sync completes (daily, or trigger manually via
  **Test Connection**).
- A connected customer's **Customer 360** profile shows a **HubSpot** badge on the
  CRM / Company card.

### Enable writeback (optional)

To push customer health scores back to HubSpot whenever they change, follow these steps:

1. **Create a custom contact property in HubSpot:**
   - In HubSpot, go to **Settings → Data Management → Objects → Contacts**.
   - Click **Create property**.
   - Set **Property type** to **Number**.
   - Set an **Internal name** (e.g., `rereflect_health_score`). Note this name — you'll
     need it in the app.
   - Set the **Label** to something user-friendly (e.g., "Rereflect Health Score").
   - Click **Create**.

2. **Grant the write scope:**
   - Go back to **Settings → Integrations → Private apps** and select the Rereflect app.
   - Under **Scopes**, enable `crm.objects.contacts.write` and click **Save**.

3. **Enable writeback in Rereflect:**
   - In Rereflect, go to **Settings → Integrations → HubSpot**.
   - Toggle **Enable health score writeback** on.
   - Enter the **Property name** you created in HubSpot (e.g., `rereflect_health_score`).
   - Click **Validate** to confirm the property exists and is writable.

Health scores are pushed to HubSpot whenever a customer's score changes by 2 or more
points. When you first enable writeback, scores for all customers are backfilled to
HubSpot. If the token is missing the `write` scope or the property is deleted in
HubSpot, writeback will silently pause — the inbound CRM sync remains unaffected.

## Connecting Salesforce CRM enrichment

Rereflect can sync Accounts, Contacts, and Opportunities from Salesforce to
enrich the Customer 360 profile (company, lifecycle stage, ARR, renewal date,
open deal). Only one CRM (HubSpot or Salesforce) can be connected per
organization at a time.

### 1. Create a Connected App in Salesforce

1. In Salesforce Setup, go to **App Manager → New Connected App**.
2. Enable **OAuth Settings** and set the **Callback URL** to
   `https://<your-backend-domain>/api/v1/integrations/salesforce/callback`
   (use `http://localhost:8000/api/v1/integrations/salesforce/callback` for
   local development).
3. Add the OAuth scopes: **`refresh_token offline_access api`** (these three
   are required — no more, no less).
4. Save, then note the **Consumer Key** (client ID) and **Consumer Secret**
   (client secret). Salesforce may take a few minutes to activate a new
   Connected App.

### 2. Configure environment variables

Set these in your backend `.env`:

| Variable | Purpose |
|----------|---------|
| `SALESFORCE_CLIENT_ID` | Connected App Consumer Key |
| `SALESFORCE_CLIENT_SECRET` | Connected App Consumer Secret |
| `SALESFORCE_REDIRECT_URI` | Must exactly match the Connected App's Callback URL |
| `SALESFORCE_LOGIN_BASE` | `https://login.salesforce.com` (production/Developer Edition) or `https://test.salesforce.com` (sandbox) |
| `SALESFORCE_API_VERSION` | Defaults to `v60.0` — bump if you need a newer Salesforce API |
| `FRONTEND_URL` | Used to build the post-OAuth redirect back to the app |

Restart the backend after setting these so the OAuth routes pick them up.

### 3. Connect from the app

Go to **Settings → Integrations → Salesforce** (admin/owner only) and click
**Connect with Salesforce**. You'll be redirected to Salesforce to log in and
approve the requested scopes, then redirected back to Rereflect connected.

### Verify

- **Settings → Integrations → Salesforce** shows instance URL, org ID, and
  contact sync counts once the first sync completes (daily, or trigger
  manually via **Test Connection**).
- A connected customer's **Customer 360** profile shows a **Salesforce** badge
  on the CRM / Company card.

> **Cross-origin note:** the OAuth flow relies on an HttpOnly cookie to bind
> the authorization request to your browser session. If your frontend and
> backend are on different origins, your reverse proxy / CORS config must
> send `Access-Control-Allow-Credentials: true` with a specific (non-`*`)
> allowed origin, or the callback will fail to verify.

### Enable writeback (optional)

To push customer health scores back to Salesforce whenever they change, follow these
steps. (The `api` scope you already granted the Connected App permits field updates —
no reconnect is needed.)

1. **Create a custom field on the Contact object in Salesforce:**
   - In Salesforce Setup, go to **Object Manager → Contact → Fields & Relationships**.
   - Click **New**, choose a **Number** type (Number, Currency, or Percent all work),
     and finish the wizard.
   - Note the field's **API name** — Salesforce custom fields end in `__c`
     (e.g., `Rereflect_Health_Score__c`). You'll need it in the app.
   - Make sure the field is **writable** for the user whose OAuth connection Rereflect
     uses (field-level security must not be read-only for that profile).

2. **Enable writeback in Rereflect:**
   - In Rereflect, go to **Settings → Integrations → Salesforce**.
   - Toggle **Enable health score writeback** on.
   - Enter the **field API name** you created (e.g., `Rereflect_Health_Score__c`).
   - Click **Validate** to confirm the field exists, is a numeric type, and is writable.

Health scores are pushed to the matched Contact (by email) whenever a customer's score
changes by 2 or more points. When you first enable writeback, scores for all matched
customers are backfilled. If the field is deleted, made read-only, or the token loses
write access, writeback silently pauses (status shows the reason) — the inbound CRM sync
and health scores are unaffected. If a customer's email maps to more than one Salesforce
Contact, the lowest Contact Id is chosen deterministically and the status notes the
ambiguity.

## Connecting Jira

Rereflect can create Jira issues directly from feedback items, with sentiment and
customer context included automatically. Jira is **not** a CRM — it doesn't enrich
the Customer 360 profile, and connecting it has no effect on HubSpot/Salesforce.

**Jira Cloud only in this release.** Jira Server, Data Center, and native OAuth
(3LO) app installation are not supported yet; the connection uses a personal
Atlassian API token over Basic auth against the Jira Cloud REST API.

### 1. Mint an Atlassian API token

1. Log in to [id.atlassian.com](https://id.atlassian.com) and go to
   **Security → Create and manage API tokens**.
2. Click **Create API token**, give it a label (e.g., "Rereflect"), and confirm.
3. Copy the token immediately — Atlassian only shows it once.

### 2. Connect from the app

The token is **not** set via an environment variable — it is pasted into the app
and stored encrypted per organization. (Encryption uses `LLM_ENCRYPTION_KEY`,
which must already be set on the backend — see
[Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok).)

Go to **Settings → Integrations → Jira** (admin/owner only) and fill in:

| Field | Format |
|-------|--------|
| Site URL | `https://{your-site}.atlassian.net` (also accepts the bare site name, e.g. `your-site`) |
| Account email | The email address of the Atlassian account that owns the API token |
| API token | The token you created in step 1 |

Click **Connect**. Rereflect resolves and validates the site URL (rejecting
anything that isn't a `*.atlassian.net` host, including private/loopback
addresses, as an SSRF safeguard), verifies the token against `GET /myself`,
and encrypts it at rest. The API token is never returned in any API response
or shown again in the UI.

### Verify

- **Settings → Integrations → Jira** shows connection status, the connected
  account, and a **Test Connection** action to re-validate the stored token.
- Any feedback item can create a linked Jira issue via **Create Jira Issue** —
  pick a project and issue type, and Rereflect creates the issue and keeps a
  link back to the originating feedback.

### All features unlocked

Because Rereflect is self-hosted and open-source, Jira issue creation has no
plan gate, seat limit, or usage cap — it's available to every organization
running the app.

## Connecting Zendesk

Unlike Jira (which Rereflect writes *out* to), Zendesk is an **inbound feedback
source**: new support tickets become feedback items, analyzed like any other
source, and enriched into Customer 360 by the requester's email address.

**Shipped scope for this release:**

- **New tickets only** — tickets created from the moment you connect. There is no
  historical backfill.
- **One feedback item per ticket** — the ticket subject and description become the
  feedback text. Per-comment / conversation-thread ingestion is not included.
- **Exactly-once** — tickets are de-duplicated by ticket ID across both polling and
  webhooks, so the same ticket never produces duplicate feedback.
- **Pull by default, webhook optional** — Rereflect polls for new tickets on a
  schedule out of the box; a Zendesk trigger/webhook adds real-time delivery.
- **Basic auth (agent email + API token)** against the Zendesk REST API v2 — there
  is no OAuth flow, tag/view filtering, or custom-field mapping in this release.

### 1. Create a Zendesk API token

1. In Zendesk, open **Admin Center → Apps and integrations → APIs → Zendesk API**.
2. Enable **Token access**, then click **Add API token**.
3. Optionally give it a description (e.g., "Rereflect"), then **copy the token
   immediately** — Zendesk only shows it once.

### 2. Connect from the app

Like the Jira token, the Zendesk API token is **not** set via an environment
variable — it is pasted into the app and stored encrypted per organization.
(Encryption uses `LLM_ENCRYPTION_KEY`, which must already be set on the backend —
see [Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok). A missing key
returns a validation error, never a 500.)

Go to **Settings → Integrations → Zendesk** (admin/owner only) and fill in:

| Field | Format |
|-------|--------|
| Subdomain | The `{subdomain}` in `{subdomain}.zendesk.com` (e.g. `acme` for `acme.zendesk.com`) |
| Agent email | The email address of the Zendesk agent that owns the API token |
| API token | The token you created in step 1 |

Click **Connect**. Rereflect normalizes and validates the subdomain (rejecting
anything that doesn't resolve to a public `*.zendesk.com` host, including
loopback/private addresses, as an SSRF safeguard), verifies the credentials against
`GET /api/v2/users/me.json`, and encrypts the token at rest. The API token is never
returned in any API response or shown again in the UI.

Connecting also **auto-provisions a Zendesk feedback source** for the org, so new
tickets start flowing in without a second setup step. Rereflect displays a
**webhook URL** and a **signing secret** on connect — copy them now if you plan to
enable real-time delivery in step 3 (the secret is shown once).

### 3. Optional: real-time via webhook

Without a webhook, Rereflect polls Zendesk for new tickets automatically. To get
tickets delivered the moment they're created, wire a Zendesk webhook:

1. Copy the **webhook URL** (`POST <your-api-base>/api/v1/webhooks/zendesk/events`)
   and the **signing secret** shown when you connected.
2. In Zendesk, open **Admin Center → Apps and integrations → Webhooks** and create
   a webhook pointing at that URL. Use the signing secret so Rereflect can verify
   deliveries.
3. Add a **Trigger** on **"Ticket is created"** that notifies the webhook, so each
   new ticket is posted to Rereflect.

Rereflect verifies every delivery over the **raw request body**. The signature
scheme is:

```
X-Zendesk-Webhook-Signature           = base64(HMAC-SHA256(signing_secret, timestamp + raw_body))
X-Zendesk-Webhook-Signature-Timestamp = timestamp used in the HMAC
```

Deliveries that fail verification are rejected. Both the pull loop and the webhook
funnel through the same ingestion path, so exactly-once de-duplication by ticket ID
holds no matter how a ticket arrives.

### Verify

- **Settings → Integrations → Zendesk** shows connection status, the connected
  agent account, and a **Test Connection** action to re-validate the stored token.
- New tickets appear as feedback items — analyzed for sentiment and mapped to the
  requester by email — within minutes. Tickets with no requester email are still
  ingested (just without a `customer_email`); an unmatched subdomain or missing
  source is logged rather than silently dropped.

### All features unlocked

Because Rereflect is self-hosted and open-source, the Zendesk integration has no
plan gate, seat limit, or usage cap — polling, webhooks, and Customer 360
enrichment are available to every organization running the app.

## Production notes

- **The frontend bakes its API URL at build time.** `NEXT_PUBLIC_API_URL` is embedded
  into the frontend image during `docker build`. If you deploy on a real host/domain,
  set `NEXT_PUBLIC_API_URL` to your backend's public URL and **rebuild** the frontend
  image:
  ```bash
  docker compose -f docker-compose.prod.yml build frontend
  ```
- **No TLS in the bundled compose.** Services bind plain HTTP on `:3000` (frontend) and
  `:8000` (backend). For internet-facing deployments, put a reverse proxy (Caddy, nginx,
  Traefik) in front for TLS.
- **Backups.** Your data lives in the Postgres volume. Snapshot it (or run
  `pg_dump`) on a schedule before upgrades.
