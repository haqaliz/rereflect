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
- [Local transformer sentiment model (opt-in, air-gap capable)](#local-transformer-sentiment-model-opt-in-air-gap-capable)
- [Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok)
- [Send product-usage events](#send-product-usage-events)
- [Connecting HubSpot CRM enrichment](#connecting-hubspot-crm-enrichment)
- [Connecting Salesforce CRM enrichment](#connecting-salesforce-crm-enrichment)
- [Connecting Jira](#connecting-jira)
- [Connecting Zendesk](#connecting-zendesk)
- [Connecting Asana](#connecting-asana)
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
This is the default and recommended starting point. A further, still-local, still-$0,
opt-in upgrade to a transformer-based sentiment model is also available — see
[Local transformer sentiment model](#local-transformer-sentiment-model-opt-in-air-gap-capable)
below.

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

## Local transformer sentiment model (opt-in, air-gap capable)

VADER (keyword-based) remains Rereflect's **default** sentiment engine — it's free,
fast, and needs nothing extra. A CPU transformer model
([`cardiffnlp/twitter-roberta-base-sentiment-latest`](https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest))
is available as a **per-organization opt-in** (Settings → AI). This section only
covers *getting the model weights onto your box* — the accuracy trade-offs of
enabling it are documented separately, not here.

### Fastest path (online, no pre-bake)

Just enable the setting. The backend/worker containers download the model and
tokenizer and cache them into `HF_HOME=/app/models` the first time any org's feedback
is analyzed with the transformer provider selected — no rebuild needed. This requires
one-time outbound network access from the container. The cache persists for the life
of the container; if you recreate the container (`docker compose up --force-recreate`,
image upgrades, etc.) with no volume mounted at `/app/models`, it re-downloads on next
use. Mount a volume at `/app/models` if you want the cache to survive container
recreation (same idea as the bundled `postgres_data`/`redis_data` volumes).

### Air-gapped path (pre-bake at build time)

For hosts with no runtime network access at all, bake the weights into the image at
build time instead:

```bash
BAKE_SENTIMENT_MODEL=true docker compose -f docker-compose.prod.yml build backend worker
```

This runs the same `from_pretrained` download during `docker build` (so it still
needs network access **at build time only**) and stores the result in `HF_HOME`
inside the image — the resulting containers need no runtime network access for
sentiment analysis. Belt-and-suspenders for a genuinely air-gapped box, also set these
in your `.env` so the containers never attempt an outbound call even if one becomes
reachable later:

```bash
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

Default builds (`BAKE_SENTIMENT_MODEL` unset or `false`) make **no** network call to
Hugging Face and bake **no** weights — nothing changes for operators who never touch
this setting.

### Minimum RAM / first-request latency

> Approximate, CPU-only, `roberta-base`-class model; confirm on your own hardware.
> These are estimates, not a benchmark result — not marketing numbers.

| | Estimate |
|---|---|
| Additional RAM per worker process (model loaded) | ~500 MB – 1 GB |
| Cold model load (first request after container start) | low single-digit seconds |
| Steady-state inference per feedback item (CPU) | tens of ms |

### Image size note

The `torch`/`transformers` **packages** themselves add roughly 250–350 MB to the
worker/backend images unconditionally (present whether or not any org enables the
transformer setting, since the deps must be importable for the opt-in to work at all).
The `BAKE_SENTIMENT_MODEL=true` pre-bake additionally adds ~450–500 MB of model
weights **only** when explicitly requested.

## Per-Org Corrections Classifier (M5.2, self-improving)

Rereflect can train small per-organization classifiers — one for **sentiment** and
one for **category** (pain-point / feature-request) — on your own corrections, run
them locally (CPU-only, offline), and auto-promote each when it measurably beats the
default analyzer. Both are **off by default** and are controlled **independently** —
your analyzer output stays byte-identical until you enable them.

### What it is

The per-org classifier is a **small, fully-offline model** trained exclusively on
your organization's own feedback text + your own sentiment corrections (stored in
`AICorrection`). Under the hood it's a **TF-IDF + logistic regression model**
(scikit-learn, CPU-only, no GPU needed, ~few KB JSON artifact). It improves the
more you correct feedback, runs locally with no cloud dependency, and retrains
weekly on a schedule. This is different from the M5.1 transformer model (which is
shared/generic); this one is yours alone.

### Three modes

Go to **Settings → AI** to choose:

| Mode | Behavior | Use case |
|------|----------|----------|
| **off** (default) | Analyzer output unchanged, no classifier trained. | Safe default. |
| **shadow** | Classifier trains silently on your corrections. Shows you the accuracy delta vs the incumbent but **never changes stored values**. | Watch the model's accuracy without risk. |
| **auto** | Classifier trains. When it beats the incumbent by ≥ +0.02 macro-F1 on held-out corrections **and** meets minimum volume thresholds, it auto-promotes and becomes the live model. You see the delta and can roll back. | Opt in to automatic self-improvement. |

### Activation gate: per-type correction volume

The classifier only trains when you've made enough corrections of a specific type.
The minimum threshold is **20 corrections of a given type** (sentiment, category,
etc.). The **Accuracy tab** (Settings → AI → Accuracy) shows your current per-type
correction counts and whether each type is ready.

- Below the threshold: the card shows "not ready — 5/20 sentiment corrections" and
  nothing trains.
- At or above: the model trains weekly (Mondays 06:30 UTC) and the card shows the
  incumbent vs challenger macro-F1 with the delta.

This is an honest gate — real-org self-improvement needs enough training data to be
meaningful.

### How to read the accuracy card

Once you've collected enough corrections, the **Accuracy tab** (Settings → AI) shows:

- **Model type**: "Per-org TF-IDF + logistic regression"
- **Label count** (`n`): the number of corrections used to train
- **Incumbent macro-F1**: the default analyzer's accuracy on held-out corrections
- **Challenger macro-F1** + **delta**: the per-org model's accuracy and how much
  better (or worse) it is than the incumbent
- **Decision**: "promoted" (now live), "retained" (challenger not good enough),
  or "skipped" (not enough data)
- **History**: last 10 training runs, showing the trend

If you enable `auto` mode and the model gets promoted, the card displays a
**Roll back** button — one click reverts to the previous model.

### Category classifier (M5.2 v2)

Alongside sentiment, Rereflect trains a per-org **category** classifier on your
`category` corrections (when you fix an AI-assigned pain-point or feature-request
category). It shares the same spine and Settings surface, with a **separate**
`category_classifier_mode` toggle and its own accuracy card — so you can run
sentiment in `auto` while category is still in `shadow`, or vice versa.

Two things specific to the category head, both chosen for honesty:

- **Dynamic labels from your data.** Its label set is exactly the categories that
  appear in *your* corrections (built-in categories and any custom ones), not a
  fixed list — so it adapts to how your team actually categorizes.
- **Unambiguous routing (no silent mis-writes).** In `auto`, a predicted label
  overrides the item's `pain_point_category` **or** `feature_request_category`
  **only when the label maps unambiguously to exactly one** built-in vocabulary. A
  label that matches neither (e.g. a custom category) or both is **shadow-logged
  only** and never written to a guessed field.
- **Fair accuracy comparison.** The challenger is scored **only over labels the
  keyword baseline can produce** ("evaluated on labels the baseline can produce" on
  the card) — so a custom-only category the baseline could never guess can't inflate
  the challenger's win and trigger a promotion.

### Known limitation

The category head is a **single unified model**, so it predicts one category per
item — it can set the pain-point *or* the feature-request field, not both
independently on the same item. Separate per-kind heads (pain-point vs
feature-request vs urgency) and multi-label items are the v3 follow-on.

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

### AI-drafted issue/task content

When an LLM is configured (cloud BYOK **or** a local Ollama / OpenAI-compatible endpoint), the
"create work item from feedback" wizard (Jira / Asana) shows a **✨ Draft with AI** button. It
generates a cleaned-up issue/task **title + body** from the feedback item, populated into the
editable fields for you to review and edit before creating — it never creates the work item on its
own. When no LLM is configured the button is simply hidden and the wizard works exactly as before,
with the feedback text seeded into the fields. Draft quality tracks whatever model you point at.

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

## Customer segments

Every customer is assigned exactly one `segment` (rule-based, **not** ML) on ingest and
refreshed nightly. Rules are evaluated top-down; the first match wins:

1. `at_risk` — high churn risk
2. `silent_churner` — usage-dependent
3. `dormant` — usage-dependent (falls back to a feedback-recency check when no usage data exists)
4. `power_user` — usage-dependent
5. `happy_advocate` — health/sentiment-based
6. `new` — recently created, little feedback history
7. `unsegmented` — nothing else matched

**`silent_churner`, `power_user`, and the usage-based arm of `dormant` require product-usage
events to be wired** (see [Send product-usage events](#send-product-usage-events) above). If
you haven't sent usage events for a customer, those three rules simply can't match — the
customer falls through to a health/sentiment-based segment (`happy_advocate`, `new`) or,
failing that, `unsegmented`. `dormant` still works without usage data via its feedback-recency
fallback arm.

The `segment` field is nullable and distinct from the `unsegmented` slug: `null` means the
segment hasn't been computed yet for that customer; `unsegmented` means it *has* been computed
and no rule matched. It's exposed on the customer list (`GET /api/v1/customers/`, with a
`?segment=` filter) and on the Customer 360 profile (internal and public API) — see
[docs/API.md](API.md) for the full slug reference.

## Customer bulk actions

The **Customers** page supports selecting a *cohort* of customers — either an explicit row
selection, or "Select all N matching this filter" (segment / risk level / search) — and running
a bulk action against it:

- **Export CSV** — streams `GET /api/v1/customers/export` (same filters as the list) as a file
  download. No row limit; the backend paginates internally rather than materializing the whole
  org in memory.
- **Tag** — add or remove operator-managed tags across the cohort (`POST
  /api/v1/customers/bulk/tags`). Admin/owner only. Tags are capped at 50 characters and 20 tags
  per customer; a customer that would exceed the cap is left unchanged and reported back in the
  response instead of being silently truncated.
- **Assign owner** — set (or clear, via "Unassign") the CS owner across the cohort (`POST
  /api/v1/customers/bulk/assign-owner`). Admin/owner only. The chosen owner must be an active
  member of your organization.
- **Run playbook** — queue a churn playbook across the cohort (`POST
  /api/v1/playbooks/{id}/run-batch`). Requires the Business+ `churn_playbooks` feature. The
  run-batch cohort only supports **segment** or an explicit **email list** (not the full
  risk-level/search filter vocabulary) — narrow a risk-level- or search-only selection to a
  single segment, or select customers individually, before running a playbook. The UI shows an
  affected-count preview (`?count_only=true` — never queues anything) before you confirm, and
  blocks the run if the resolved cohort exceeds the **500-customer batch cap** (a real run
  returns `422` for the same reason if you bypass the UI).

Tags and the assigned CS owner are visible as chips/badges on both the customer list and the
Customer 360 profile page.

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

### Syncing Jira status back to feedback (opt-in)

Once an issue is linked, Rereflect can keep the feedback item's status in step
with the Jira issue — so when an engineer moves the ticket to *In Progress* or
*Done*, the feedback item follows without anyone updating it by hand.

- **Off by default.** Turn it on under **Settings → Integrations → Jira** with the
  **"Sync issue status back to Rereflect"** toggle (admin/owner). The tile shows
  the last sync time and any error, plus a **Sync now** button.
- **Poll-based (works behind a firewall).** A background job checks your linked
  issues every ~15 minutes over the same API token — no public URL or inbound
  webhook required, so it works on a self-hosted box behind NAT.
- **Category-based mapping.** Rereflect maps Jira's status *category* — not each
  custom status name — so it works with any Jira workflow:
  - *To Do* → `new`
  - *In Progress* → `in_review`
  - *Done* → `resolved`
  You can override this per-organization if your team uses the feedback statuses
  differently.
- **Non-destructive.** Turning it on does **not** retroactively rewrite the status
  of feedback you already linked — it records the current Jira status as a baseline
  and only moves a feedback item when the Jira issue *changes* afterward. It will
  not fight a status you set by hand unless the Jira issue genuinely moves. If a
  feedback item is linked to several Jira issues, the most-advanced status wins.

Real-time webhook sync (instead of polling) and a per-status-name mapping editor
are planned for a future release.

### All features unlocked

Because Rereflect is self-hosted and open-source, Jira issue creation and
status-sync have no plan gate, seat limit, or usage cap — they're available to
every organization running the app.

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

Each org connects its own Zendesk account with its own validated credentials — two
different Rereflect orgs must not point at the same Zendesk subdomain, or tickets
from that subdomain would be attributed to both.

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

**Known limitation:** if you enable BOTH the scheduled pull and the real-time
webhook, a rare timing overlap (a webhook arriving while the ~15-min pull runs for
the same brand-new ticket) can create a duplicate feedback item. Sequential
redelivery and repeated syncs are always de-duplicated by ticket ID.

### Verify

- **Settings → Integrations → Zendesk** shows connection status, the connected
  agent account, and a **Test Connection** action to re-validate the stored token.
- New tickets appear as feedback items — analyzed for sentiment and mapped to the
  requester by email — within minutes. Tickets with no requester email are still
  ingested (just without a `customer_email`); an unmatched subdomain or missing
  source is logged rather than silently dropped.

### Syncing Zendesk ticket status back to feedback (opt-in)

Once a support ticket has become a feedback item (via ingestion, above), Rereflect
can keep that feedback item's status in step with the Zendesk ticket — so when an
agent marks the ticket *Solved*, the feedback item follows without anyone updating
it by hand.

- **Off by default.** Turn it on with `PATCH /api/v1/integrations/zendesk/status-sync`
  (admin/owner-only, JSON body `{"enabled": true}`) — the same endpoint also accepts
  an optional `status_mapping` override (see below). This surfaces as a toggle on
  **Settings → Integrations → Zendesk** as the in-app UI for it ships.
- **Poll is the guaranteed path.** With status-sync on, a background job checks your
  Zendesk-linked feedback every ~15 minutes over the same API token — no public URL
  or inbound webhook required, so it works on a self-hosted box behind NAT. This is
  always active once enabled, independent of whether you also configure the
  real-time webhook below.
- **Real-time webhook (additive, optional).** If you've already wired the ingestion
  webhook (see "Optional: real-time via webhook" above), you can extend it for status
  changes instead of waiting for the next poll:
  1. In Zendesk, open **Admin Center → Apps and integrations → Triggers** (or Views →
     Triggers) and create a **second** trigger — separate from the "Ticket is
     created" one — that fires on **Ticket updated / Status changed**.
  2. Point it at the **same webhook URL and signing secret** you already configured
     (`POST <your-api-base>/api/v1/webhooks/zendesk/events` — the HMAC scheme is
     identical, since both triggers deliver through the one webhook connection).
  3. Set the trigger's JSON body to include the anti-spoof discriminator field
     `"event": "ticket.status_changed"` — **required**, distinct from the ingestion
     trigger's body — plus the ticket id and Zendesk's `{{ticket.status}}`
     placeholder:
     ```json
     {
       "event": "ticket.status_changed",
       "subdomain": "your-subdomain",
       "ticket": {
         "id": "{{ticket.id}}",
         "status": "{{ticket.status}}"
       }
     }
     ```
     Without the `"event": "ticket.status_changed"` field, Rereflect cannot tell a
     status-change delivery apart from a ticket-creation one, so this field is what
     routes the delivery to the status-sync path instead of feedback ingestion.
  4. Rereflect reconciles that single ticket immediately on a verified delivery — no
     apply happens if status-sync is off for the org, if the ticket isn't linked to a
     feedback item, or if this is the first status ever observed for it (that first
     observation is recorded as a baseline, not applied — see "Non-destructive"
     below). Every delivery is ACKed 200 regardless, so Zendesk never retries a
     well-formed, verified request.
  5. **The 15-minute poll remains the fallback either way** — if the webhook is never
     configured, misfires, or a delivery is missed, the next poll catches the ticket
     up. Whichever path (poll or webhook) observes a given status change first
     applies it; the other is a no-op, so you never get a duplicate status-change
     event from having both enabled.
- **Category-based mapping.** Rereflect maps Zendesk's ticket `status` field to a
  feedback `workflow_status`:
  - `new` → `new`
  - `open` / `pending` / `hold` → `in_review`
  - `solved` → `resolved`
  - `closed` → `closed`
  You can override this per-organization via the `status_mapping` field on the same
  `PATCH .../status-sync` call.
- **Non-destructive.** Turning it on does not retroactively rewrite the status of
  feedback you already linked — the first status observed for each ticket (via poll
  or webhook, whichever happens first) is recorded as a baseline only, and a feedback
  item's `workflow_status` moves only when the Zendesk ticket's status genuinely
  *changes* afterward.

### All features unlocked

Because Rereflect is self-hosted and open-source, the Zendesk integration has no
plan gate, seat limit, or usage cap — polling, webhooks, status-sync, and
Customer 360 enrichment are available to every organization running the app.

## Connecting Asana

Like Jira, Rereflect writes *out* to Asana — it creates tasks directly from
feedback items, with sentiment and customer context included automatically.
Asana is **not** a CRM and does not enrich the Customer 360 profile. This is
**one-way, outbound task creation**: Rereflect does not sync task status,
assignees, or comments back in from Asana.

### 1. Mint a Personal Access Token

1. In Asana, open your profile settings (click your avatar) and go to
   **Apps → Manage Developer Apps**.
2. Click **Create new token**, give it a name (e.g., "Rereflect"), and confirm.
3. Copy the token immediately — Asana only shows it once.

### 2. Connect from the app

The token is **not** set via an environment variable — it is pasted into the
app and stored encrypted per organization. (Encryption uses
`LLM_ENCRYPTION_KEY`, which must already be set on the backend — see
[Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok).)

Go to **Settings → Integrations → Asana** (admin/owner only) and paste the
personal access token you just created, then click **Connect**. Rereflect
verifies the token against your Asana account and encrypts it at rest. The
token is never returned in any API response or shown again in the UI.

### Verify

- **Settings → Integrations → Asana** shows connection status, the connected
  account, and a **Test Connection** action to re-validate the stored token.
- Any feedback item can create a linked Asana task via **Create Asana Task** —
  pick a workspace and project, and Rereflect creates the task and keeps a
  link back to the originating feedback. Creating a task twice from the same
  feedback item surfaces the existing linked task instead of duplicating it.

### Known limitation: team-scoped projects

Rereflect lists projects with a **flat workspace → project picker**
(`GET /api/v1/integrations/asana/projects?workspace_gid=...`). Asana projects
that are scoped to a specific **team** and not visible at the workspace level
may not appear in that list, depending on your Asana workspace's permission
model. If a project you expect is missing, check whether it's team-only in
Asana. A team-aware project selector (choose a team first, then its
projects) is planned as a v2 follow-up — for now, only workspace-visible
projects can be selected.

### All features unlocked

Because Rereflect is self-hosted and open-source, Asana task creation has no
plan gate, seat limit, or usage cap — it's available to every organization
running the app.

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
