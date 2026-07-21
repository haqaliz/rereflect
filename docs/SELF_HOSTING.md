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
- [Public API — bulk feedback writes & taxonomy CRUD](#public-api--bulk-feedback-writes--taxonomy-crud)
- [Connecting HubSpot CRM enrichment](#connecting-hubspot-crm-enrichment)
- [Connecting Salesforce CRM enrichment](#connecting-salesforce-crm-enrichment)
- [CRM churn-label suggestions (opt-in)](#crm-churn-label-suggestions-opt-in)
- [Connecting Jira](#connecting-jira)
- [Connecting Zendesk](#connecting-zendesk)
- [Connecting Asana](#connecting-asana)
- [Single Sign-On (OIDC)](#single-sign-on-oidc)
- [Single Sign-On (SAML 2.0)](#single-sign-on-saml-20)
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

## Telemetry (there isn't any)

Rereflect collects **no telemetry, no usage analytics, and no crash reports**. A default
install makes no outbound network calls of its own — nothing is sent to the maintainers
or to any third party. There is no opt-out to find, because there is nothing running.

The only outbound calls a Rereflect instance ever makes are ones you configure yourself:

| Call | When |
|---|---|
| Your LLM provider (OpenAI / Anthropic / Google) | Only if you add a BYOK key **and** set `ai_analysis_enabled=true`. Omit the key and nothing is contacted. |
| Your local model endpoint (Ollama, etc.) | Only if you point Settings → AI at one. Stays on your network. |
| Integrations (Slack, Jira, Zendesk, Asana, HubSpot, Salesforce) | Only for integrations you explicitly connect and authorize. |
| Your Sentry project | Only if you set `SENTRY_DSN` — see below. |

### Optional error tracking (Sentry), off by default

If you want crash reports for your own instance, set `SENTRY_DSN` to **your own** Sentry
project's DSN. Leave it unset (the default) and the Sentry SDK is never initialized.

```bash
# .env — all optional, all default to off/empty
SENTRY_DSN=                      # empty => Sentry never initializes
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

When enabled, Rereflect sets `send_default_pii=False`, so the SDK does not attach user
emails, usernames or IP addresses to events. The same variable controls the backend, the
Celery worker and the Next.js frontend (the frontend's browser-side reporting reads
`NEXT_PUBLIC_SENTRY_DSN`, which is baked in at build time — rebuild the frontend image
after changing it).

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

### Urgency classifier (M5.2 v3)

Rereflect also trains a per-org **urgency** classifier on your `urgency` corrections
(when you flip a feedback item's urgent flag from the dashboard or the public API).
It shares the same spine and Settings surface, with its own independent
`urgency_classifier_mode` toggle (off/shadow/auto) and its own accuracy card.

Two things specific to the urgency head, both chosen for safety:

- **Binary, keyword-baseline incumbent.** It's a two-class model (`urgent` /
  `not_urgent`) whose challenger must beat the built-in keyword+sentiment urgency
  heuristic on your held-out corrections before it can promote — the same
  ≥ +0.02 macro-F1 bar. Macro-F1 (not accuracy) is the gate, so a lazy model that
  just predicts "not urgent" for everything can never win.
- **Add-only in `auto` (no silent de-escalation).** In `auto`, the model may
  **escalate** an item to urgent (`not_urgent → urgent`) but will **never** clear an
  urgent flag the heuristic raised. Because the urgent flag drives churn alerts and
  the urgent queue, a thin per-org model can only ever add urgency, never hide it.
  `shadow` still logs both directions (including would-be de-escalations) so you can
  evaluate accuracy before trusting `auto`.

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
   **Settings → AI → Health Score Weights** and raise the **Usage Activity** weight above 0
   (all six weights must sum to 100). The default is 0 so existing scores are
   unchanged until you opt in.

### Usage trend (decline detection)

Once usage events are flowing, Rereflect tracks the **direction** of a customer's engagement,
not just its current level. The **Usage Activity** card shows a trend state:

- **Stable** — engagement is holding steady (or rising).
- **Declining** / **Sharp Decline** — the customer's active-days over the last two weeks have
  fallen meaningfully versus their *own* activity about two weeks earlier, shown with the signed
  percentage change. This is the case a level-only score misses: a customer disengaging while
  still nominally active.
- **Warming up** — the trend needs about two weeks of daily history before it can report. A
  freshly-installed instance shows "Warming up" for its first ~2 weeks. **This is expected, not a
  fault** — there is no back-fill; history accumulates one daily snapshot at a time.

When you have opted into usage weighting (step 4), a declining trend applies a small, bounded
penalty to the **usage component of the health score only**. It never affects churn probability
or its calibration.

**Honest caveats.** This is a heuristic decline signal computed on your own data — there is no
accuracy-lift claim, and nothing is compared across tenants. A company-wide event (a holiday, a
seasonal lull) can read as a decline for many customers at once; per-org tuning and seasonality
handling are not yet implemented.

> **Upgrade note.** This release also corrected a defect where a customer's activity counters
> stopped decaying once they went quiet. If you had already opted into usage weighting, some
> health scores will **drop** after upgrading — those scores were previously overstated. Scores
> for organizations at the default usage weight of 0 are unchanged. Because a lower score can
> cross a risk-level boundary, the **first daily recompute after upgrade may fire a burst of
> health-drop alerts and health/risk automation runs** for customers whose scores were inflated —
> all correct, but arriving at once. If you run automations on health score or risk level,
> consider pausing them for the first daily cycle after upgrade.

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

## Public API — bulk feedback writes & taxonomy CRUD

Two additions to the `/api/public/v1` public API (see [docs/API.md](API.md) for the full public
API reference): bulk-patching feedback in one request, and full CRUD over your custom
categories. Both require a `write`-scoped API key (`rrf_...`, created in **Settings → API
Keys**); listing categories only needs `read`.

### Bulk feedback writes

`POST /api/public/v1/feedback/bulk` applies one uniform `patch` to up to 500 feedback ids in a
single request. The `patch` object accepts exactly the same fields as the single
`PATCH /api/public/v1/feedback/{id}` (`workflow_status`, `resolution_note`, `correction`, `tags`,
`is_urgent`) — see the [API docs](API.md) for their semantics.

```bash
curl -X POST http://localhost:8000/api/public/v1/feedback/bulk \
  -H "Authorization: Bearer rrf_YOUR_WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "ids": [101, 102, 103],
    "patch": { "workflow_status": "resolved", "tags": ["billing"] }
  }'
```

Response:

```json
{
  "matched": 3,
  "updated": 2,
  "skipped": 1,
  "results": [
    { "id": 101, "status": "updated" },
    { "id": 102, "status": "noop" },
    { "id": 103, "status": "skipped", "reason": "not_found" }
  ]
}
```

- `ids` accepts 1–500 entries; duplicates are deduped and `results` is returned in deduped
  input order.
- Ids that don't exist, or belong to a different organization, come back as `skipped` — they
  are never treated as errors.
- `tags` / `is_urgent` / `correction` are applied per item and are non-contagious: one item
  failing doesn't roll back the rest of the batch (it comes back as `status: "error"`).
  `workflow_status` is applied as one batched status change across all matched items.
- Pass `?count_only=true` to dry-run the request — it returns `matched`/`skipped` counts with
  `updated: 0` and an empty `results` list, and mutates nothing.
- An empty `patch` (no recognized fields set) returns `400`, same as the single `PATCH`.

### Custom-category (taxonomy) CRUD

`GET/POST/PATCH/DELETE /api/public/v1/categories` manage the same custom
pain-point/feature-request/urgency/general categories as **Settings → Categories**, over the
API.

```bash
# List (optionally filter by category_type)
curl http://localhost:8000/api/public/v1/categories?category_type=pain_point \
  -H "Authorization: Bearer rrf_YOUR_READ_KEY"

# Create
curl -X POST http://localhost:8000/api/public/v1/categories \
  -H "Authorization: Bearer rrf_YOUR_WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Shipping delay", "category_type": "pain_point", "description": "Late deliveries"}'

# Update (category_type is immutable — omit it, sending it 422s)
curl -X PATCH http://localhost:8000/api/public/v1/categories/42 \
  -H "Authorization: Bearer rrf_YOUR_WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'

# Delete
curl -X DELETE http://localhost:8000/api/public/v1/categories/42 \
  -H "Authorization: Bearer rrf_YOUR_WRITE_KEY"
```

- Creating a duplicate `(category_type, name)` within your organization returns `409`.
- An id that doesn't exist, or belongs to another organization, returns `404`.
- `category_type` cannot be changed after creation — `PATCH` rejects it as an unknown field
  (`422`, `extra="forbid"`).
- `DELETE` hard-deletes the category and returns `204`. If the category's name is referenced
  by an **active** automation rule (a `feedback_category_match` trigger), the response also
  carries an `X-Rereflect-Warning` header naming the rule(s) — the delete still succeeds; this
  is advisory only, there is no cascade to the rule.

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

## CRM churn-label suggestions (opt-in)

Churn prediction learns from **churn labels** — records of customers who actually
left. Until now you produced those by hand (Customer 360 → **Mark as churned**) or by
CSV import. If you've connected HubSpot or Salesforce, your CRM already knows which
renewals were lost, and this feature reads them for you.

It produces **suggestions, not labels.** A suggestion is a proposal that sits in a
review queue until a human confirms it. **Nothing is ever auto-applied** — no
suggestion reaches the training set without an operator clicking Confirm. That is
deliberate, and it is the whole design: **a lost renewal is not always a churn.** A
deal can close lost because it merged into another contract, because procurement
re-papered it, because the champion moved to a new department, or because someone
mis-staged it. Only a human knows which.

Two more things this feature does **not** do, stated plainly:

- It makes **no claim about churn-prediction quality.** It produces labels. Whether
  more labels change the model is a separate, open question (see `AI-TRACKING.md`,
  M5.3) — nothing here should be read as a promise that predictions get better.
- Churn prediction remains **a calibrated heuristic**, not machine learning. This
  feature does not change that.

### 1. Connect a CRM

Follow [Connecting HubSpot CRM enrichment](#connecting-hubspot-crm-enrichment) or
[Connecting Salesforce CRM enrichment](#connecting-salesforce-crm-enrichment) first.
Only one CRM (HubSpot or Salesforce) can be connected per organization at a time.
No extra scope is needed — the `crm.objects.deals.read` scope (HubSpot) and the `api`
scope (Salesforce) you already granted are sufficient.

### 2. Enable and choose your renewal set

Go to **Settings → Integrations → HubSpot** (or **Salesforce**), admin/owner only, and
find the **CRM Churn-Label Suggestions** card.

1. Toggle **Enable churn-label suggestions** on.
2. Choose your renewal set:
   - **HubSpot** — pick your **Renewal pipelines**. The picker lists the deal pipelines
     live from your portal.
   - **Salesforce** — pick your **Renewal opportunity types**, listed live from your
     `Opportunity.Type` picklist.
3. Save.

**The picker locks while the feature is enabled.** To re-point it at a different
pipeline or type, toggle the feature off, change the selection, and toggle it back on.
(This stops a live harvest having its renewal set changed out from under an in-flight
run.) The toggle itself is never locked — you can always turn it off.

Once enabled, the harvest runs inside the **existing daily CRM sync** — 03:15 UTC for
HubSpot, 03:45 UTC for Salesforce. **No new schedule, no new worker.**

### 3. Default-deny: nothing happens until you pick

This feature is **off by default and denies by default.** Concretely:

- No suggestions exist until you both enable the toggle **and** name at least one
  renewal pipeline / opportunity type.
- Enabling the toggle while selecting **nothing** produces **nothing**. The card warns
  you: *"No renewal pipelines selected — no suggestions will be created. Pick the
  pipeline your renewals close in."*
- A deal or opportunity whose pipeline / type is **null or unrecognised produces no
  suggestion, ever.** There is no guessing, no fuzzy matching, no regex over pipeline
  names. If it isn't in the set you named, it is skipped.
- **An organization that ignores this feature sees no change anywhere** — no new rows,
  no new counters, no change to churn scores.

### 4. Backfill your history (optional, on-demand)

Enabling only harvests going forward. To reach back over closed-lost history, use
**Backfill history** on the same card.

- **On-demand only.** It never runs automatically and is **not** triggered by enabling
  the feature. It runs when you click **Run**, and never otherwise.
- **You choose the window** from the **Backfill window** picker: **12 / 24 / 36 / 60**
  months back. Default **24**; **60 months (5 years) is the hard maximum** — the API
  rejects anything outside 1–60.
- **It produces suggestions, not labels.** Exactly like the daily harvest, every row
  lands in the review queue for a human. A backfill can never mark anyone churned.
- **Resumable and idempotent.** Re-running completes the remainder instead of
  duplicating: suggestions are unique per `(organization, provider, external id)`.
- **Cancellable.** Click **Cancel** while it runs. Cancellation is checked at each
  company/account boundary, so it stops shortly after you ask rather than instantly;
  progress already made is kept.
- **Progress is live.** The card polls every 5s and shows **Scanned**, **Suggested**
  and **Skipped**.
- **The cap is not silent.** A run is capped at **2,000 suggestions**. If it truncates,
  the card raises an alert naming both the count and how far back it actually got —
  e.g. *"37 dropped by the per-run cap; covered window: since 7/15/2024."* Narrow the
  window (or confirm/reject what's queued) and run it again to continue.

**Run** stays disabled until the feature is enabled and at least one pipeline / type is
selected — default-deny applies to backfill too.

### 5. Review the queue — the step that creates labels

Suggestions accumulate as **pending** and go nowhere on their own. When any are
waiting, admins and owners see a **CRM churn suggestions** card on the **Customers**
page linking to **Customers → CRM churn suggestions**
(`/customers/churn-suggestions`).

The queue lists **Customer**, **Provider**, **Evidence** (the CRM deal/opportunity
detail behind the suggestion), and **Close date**. For each row:

- **Confirm** — opens **Confirm churn suggestion**. A **Reason** is **required**
  (Price, Competitor, Product Quality, No Longer Needed, Silent Churn, Other), and an
  optional note is stored with the event. The **CRM close date** is shown read-only and
  is used as the churn date — you cannot edit it.
- **Reject** — dismisses the suggestion.

**Confirming is what creates a label.** It writes a real churn event with
`source='manual'`, stamped with your user id and linked back to the suggestion for
provenance — identical to a label created by hand via **Mark as churned**, and fully
trainable. Rejecting writes no event.

**Bulk review.** Select rows and use **Confirm selected** / **Reject selected**, capped
at **500** per action. A bulk confirm requires one Reason applied to the whole
selection — if the customers churned for different reasons, confirm them individually.
A filter-based selection larger than the cap processes the first 500 and tells you what
it didn't process; an explicit selection over 500 is rejected outright rather than
silently trimmed.

If a customer was already marked as churned by other means, confirming resolves the
suggestion against the existing event rather than creating a duplicate, and reports it
as skipped.

> **Known rough edge:** the **note** field on the *reject* dialog is **not persisted** —
> there is no column for it yet. Reject notes are discarded. The note on the *confirm*
> dialog is stored normally. Also, a bulk **reject** reports its tally as
> *"N confirmed"* — a contract-parity artifact in the response field name, not a sign
> anything was confirmed.

### Verify

The **CRM Churn-Label Suggestions** card shows **last harvest time**, **last harvest
status**, **suggestions created**, and **last harvest error**. **Settings → AI →
Readiness** shows **pending suggestions** as its own counter — deliberately **not**
counted toward readiness, because a pending suggestion is not a label.

### Troubleshooting

- **No suggestions at all.** By far the most likely cause: no renewal pipelines /
  opportunity types are selected. Check the card for the empty-state warning. Otherwise
  there may genuinely be no lost renewals in the window — this is common and not a bug.
- **Suggestions look wrong.** Your renewal set is probably too broad (e.g. a new-business
  pipeline selected alongside renewals). Toggle off, narrow the selection, toggle on.
  Reject the bad rows — rejecting is free and nothing was labeled.
- **`403` from the CRM.** The token is missing the deal/opportunity read scope. Re-grant
  it (HubSpot: `crm.objects.deals.read`) and re-run.
- **`429` from the CRM.** You're throttled. The harvest backs off and retries on the next
  daily sync; a backfill retries with a delay. No action needed.
- **Daily harvest cap.** The daily harvest is capped at **200** suggestions per run
  (separate from backfill's 2,000). Overflow is logged with a `dropped_by_cap` count —
  never silently dropped — and the next run picks up where it left off.
- **Backfill won't start.** **Run** is disabled unless the feature is enabled with at
  least one pipeline/type selected. A `409` means a backfill is already running. A `502`
  means the task queue (Redis/Celery) couldn't be reached — check the worker is up.

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

### Real-time webhook (optional)

Status-sync above always works by polling — no public URL required. If your
Rereflect instance is publicly reachable, you can additionally enable a
real-time inbound webhook so a Jira issue's status change lands on the linked
feedback item in seconds instead of waiting up to ~15 minutes for the next
poll:

1. On **Settings → Integrations → Jira**, click **Enable webhook** under
   "Real-time webhook" (admin/owner only). This calls
   `POST /api/v1/integrations/jira/webhook/enable`, which generates a fresh
   HMAC secret and returns it **once** together with the inbound URL
   (`POST <your-api-base>/api/v1/webhooks/jira/inbound`) — copy both now,
   Rereflect never shows the secret again (re-enabling rotates it).
2. In Jira, open **Settings → System → WebHooks** (site-admin) and create a
   webhook pointed at that URL, scoped to **Issue: updated**, with the secret
   from step 1 configured as the webhook's signing secret.
3. Jira Cloud signs each delivery over the raw request body and sends
   `X-Hub-Signature: sha256=<hex HMAC-SHA256(secret, raw_body)>`. Rereflect
   verifies every delivery against that header, resolving the org by trying
   each org's configured secret (fail-closed: a missing/invalid signature, or
   no org's secret matching, is rejected with `401` — never processed).

Only `jira:issue_updated` deliveries that include a `status` field in the
changelog are reconciled; every other Jira webhook event is acknowledged
`200` and ignored. The webhook reconciles through the exact same
category-based mapping and race-safe apply as the poll above, so enabling it
can never cause the two paths to disagree or double-write — turning it off
(**Disable webhook**) simply falls back to poll-only, with no other effect.

A per-status-name (rather than per-category) mapping editor is planned for a
future release.

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
Asana is **not** a CRM and does not enrich the Customer 360 profile. Task
**creation** is outbound, but Rereflect can optionally sync a linked task's
**completion status** back onto the feedback item (see
[Syncing Asana status back to feedback](#syncing-asana-status-back-to-feedback-opt-in)
below). It still does not pull assignees, comments, or due dates back in from
Asana.

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

### Syncing Asana status back to feedback (opt-in)

Once a task is linked, Rereflect can optionally keep the feedback item's
status in step with the Asana task — so when the task is marked complete, the
feedback item follows without anyone updating it by hand.

- **Off by default.** Turn it on under **Settings → Integrations → Asana**
  with the status-sync toggle (admin/owner). The tile shows the last sync
  time and any error, plus a **Sync now** button.
- **Poll-based (works behind a firewall).** A background job checks your
  linked tasks every ~15 minutes over the same personal access token — no
  webhook or public URL required, so it works on a self-hosted box behind
  NAT. This always runs, even if you also enable the real-time webhook below.
- **Completion-based mapping — Asana has only two states.** An Asana task is
  either **completed** or **not**, so Rereflect maps:
  - not completed → `new`
  - completed → `resolved`
  The default mapping is `{done: resolved, new: new}`. There is **no
  `in_review` / intermediate state** from Asana in this release — unlike
  Jira, which exposes a real "in progress" status category, Asana only
  exposes a completed/not-completed flag on a task. Section-name or
  custom-field mapping that could add an intermediate state is a planned v2
  follow-up.
- **Remap per-organization.** Override the mapping via
  `PATCH /api/v1/integrations/asana/status-sync` with
  `{ "enabled": true, "status_mapping": { "done": "closed" } }`
  (admin/owner) — e.g. resolve to `closed` instead of `resolved`. Invalid
  keys/values are rejected (422).
- **Non-destructive and bidirectional.** Turning it on does **not**
  retroactively rewrite feedback you already linked — the first poll records
  the task's current state as a baseline and only moves a feedback item when
  the task *changes* afterward. It will not fight a status you set by hand
  unless the linked Asana task genuinely changes. If a task is later
  **re-opened** in Asana (completed → not completed), the linked feedback
  reverts back toward `new`, with a timeline entry recording the change
  (tagged `source=asana`).
  If a feedback item is linked to several Asana tasks, the most-advanced
  status wins.

Section/custom-field → intermediate-state mapping and OAuth connection are
planned for a future release.

### Real-time webhook (optional)

Status-sync above always works by polling — no public URL required. If your
Rereflect instance is publicly reachable, you can additionally enable a
real-time inbound webhook so an Asana task's completion change lands on the
linked feedback item in seconds instead of waiting up to ~15 minutes for the
next poll.

Unlike Jira/Zendesk (where Rereflect generates its own signing secret
locally), **Asana requires a handshake**: Rereflect registers the webhook
directly with Asana's API, and Asana's *first delivery* to that webhook
carries a fresh secret in an `X-Hook-Secret` header, which Rereflect must
persist and echo back immediately (HTTP 200, same header, no other work) —
this is how Asana knows the endpoint is alive. Every delivery after that is
signed with `X-Hook-Signature: <hex HMAC-SHA256(secret, raw_body)>` (no
`sha256=` prefix, unlike Jira). You never see or copy a secret yourself —
Rereflect handles both sides automatically:

1. On **Settings → Integrations → Asana**, click **Set up webhook** under
   "Real-time webhook" (admin/owner only), then pick the **workspace and
   project** to watch (v1 scope: a single project — see "Known limitation"
   below; this reuses the same workspace/project picker as task creation).
2. Click **Enable webhook**. This calls
   `POST /api/v1/integrations/asana/webhook/enable`, which mints an
   unguessable per-webhook URL token and registers a webhook with Asana
   (`POST https://app.asana.com/api/1.0/webhooks`) targeting
   `POST <your-api-base>/api/v1/webhooks/asana/inbound/{webhook_url_token}`
   — **not** your integration's id — and stores the returned webhook gid.
   Asana then performs the handshake against that URL automatically — no
   copy/paste step, and neither the secret nor the URL/token is ever shown
   in the UI (the operator never needs them — Asana auto-registration
   handles both sides).
3. The card immediately shows "Real-time webhook" as **Enabled**; the
   handshake itself (secret capture) completes server-side within moments
   of Asana's first delivery, with no further action needed.

Rereflect resolves *which* organization a delivery belongs to from the
unguessable `webhook_url_token` embedded in the URL it registered in step 2
(rather than matching against every org's secret, as Jira/Zendesk do, or a
guessable sequential id) — this works even before any secret exists yet,
which the very first handshake delivery requires. Every subsequent event is
fail-closed: a missing/invalid `X-Hook-Signature`, or an org with no
captured secret, is rejected with `401` — never processed. Critically, an
org that has **already** completed its handshake also rejects any further
`X-Hook-Secret` request with `401` and leaves the stored secret untouched —
a handshake can only ever set a secret once per webhook, closing off any
attempt (however the URL was obtained) to overwrite an established secret.
Re-enabling the webhook always registers a fresh one at Asana, mints a new
URL token, and clears the old secret, so a new handshake against the new
URL is required — the old URL stops resolving immediately.

Task completion changes are reconciled through the exact same
completion-based mapping and race-safe apply as the poll above, so enabling
the webhook can never cause the two paths to disagree or double-write.
Clicking **Disable webhook** fully unreaches it: Rereflect clears the stored
webhook gid, secret, *and* the unguessable URL token, so the old
`/api/v1/webhooks/asana/inbound/{webhook_url_token}` URL 401s immediately —
even someone who still holds that URL cannot re-establish a handshake
against a disabled integration — and falls back to poll-only handling.

### Known limitation: team-scoped projects

Rereflect lists projects with a **flat workspace → project picker**
(`GET /api/v1/integrations/asana/projects?workspace_gid=...`). Asana projects
that are scoped to a specific **team** and not visible at the workspace level
may not appear in that list, depending on your Asana workspace's permission
model. If a project you expect is missing, check whether it's team-only in
Asana. A team-aware project selector (choose a team first, then its
projects) is planned as a v2 follow-up — for now, only workspace-visible
projects can be selected. This also applies to the real-time webhook above —
it subscribes to a **single project** per organization, not the whole
workspace; multi-project/workspace-wide subscriptions are a planned v2
follow-up.

### All features unlocked

Because Rereflect is self-hosted and open-source, Asana task creation and
status-sync have no plan gate, seat limit, or usage cap — they're available
to every organization running the app.

## Single Sign-On (OIDC)

Rereflect supports OIDC-based single sign-on alongside the existing password and Google
login — an operator can wire up their identity provider (Okta, Azure AD, Google
Workspace, Keycloak, or any standards-compliant OIDC provider) so a team logs in with
corporate credentials instead of a Rereflect password. Password and Google login are
unaffected either way. **All features are unlocked** on self-hosted, so SSO carries no
plan gate.

**Prerequisite:** SSO configuration (including the client secret) is stored encrypted, so
`LLM_ENCRYPTION_KEY` must already be set — see
[Adding your own LLM key (BYOK)](#adding-your-own-llm-key-byok). Without it, saving an
SSO config returns a validation error, never a 500.

### 1. Register a client with your identity provider

Create an OIDC client/application in your IdP with:

| Setting | Value |
|---------|-------|
| Redirect / callback URL | `{BACKEND_URL}/api/v1/auth/oidc/callback` — e.g. `http://localhost:8000/api/v1/auth/oidc/callback` for a local install. **This must match exactly** what you whitelist in the IdP. |
| Scopes | `openid email profile` |
| Response type | `code` |
| PKCE | **S256** (required — Rereflect always sends a PKCE challenge) |

This works with any IdP that signs ID tokens with RS256, including Okta, Azure AD
(Entra ID), Google Workspace, and Keycloak in their default configurations.

### 2. Configure in the app

Go to **Settings → SSO** (`/settings/sso`, admin/owner only) and fill in:

| Field | Notes |
|-------|-------|
| Issuer URL | Your IdP's OIDC issuer (discovery is fetched from `{issuer}/.well-known/openid-configuration`) |
| Client ID | From your IdP client registration |
| Client secret | From your IdP client registration — encrypted at rest, never shown again after saving |
| Allowed email domains | See below — **required**, or nobody can sign in |
| Button label | Optional custom text for the "Sign in with SSO" button |
| Enabled | Turns the login button on/off |

### 3. Allowed email domains: empty means deny-all

An empty `allowed_email_domains` list is **not** "allow anyone" — it is **deny-all**.
You must list at least one domain (e.g. `acme.com`) before any SSO login can succeed;
an identity outside the list is rejected with no account created or linked.

**Do not list an over-broad public domain** (e.g. `gmail.com`) if your issuer is a
multi-tenant IdP endpoint (Google's own OIDC, or an Azure AD app registered for "any
organizational directory"). Doing so would auto-provision **any** account from that
provider into your organization, since every such account already satisfies
`email_verified: true`. Scope the issuer to your own tenant/directory and the allowlist
to your own domain(s).

### One enabled configuration per deployment

At most one OIDC configuration can be `enabled` at a time across the whole deployment —
there is no per-org SSO in this release. Enabling a second organization's config while
another is already enabled is rejected.

### JIT provisioning and account linking

- **New user, no existing Rereflect account:** the first successful SSO login
  auto-creates a `member` in the organization that owns the enabled config. There is no
  invite step.
- **Existing password or Google account with the same email:** it is linked to the SSO
  identity (its auth method becomes "both") — **only if the IdP asserts
  `email_verified: true`**. An unverified email is rejected outright; no account is
  created or linked.

### Known limitation: RS256 only

ID tokens must be **RS256-signed**. This is the default for Okta, Azure AD, Google, and
Keycloak, so most operators won't notice — but Rereflect does not negotiate signing
algorithms with the IdP, and an issuer that signs only with ES256 or another algorithm
is currently rejected. Stated here plainly rather than discovered at login time.

### Testing against a local Keycloak

For a quick end-to-end test without a real IdP, the bundled `docker-compose.yml`
includes a dev-only Keycloak service, gated behind a profile so it never starts with a
plain `docker compose up`:

```bash
docker compose --profile dev-idp up keycloak
```

Open the admin console at `http://localhost:8080` and log in with the dev credentials
(`admin` / `admin`). Create a realm, then a confidential client inside it with the
redirect URI `http://localhost:8000/api/v1/auth/oidc/callback` and the scopes/response
type/PKCE settings from step 1 above. Paste the realm's issuer URL
(`http://localhost:8080/realms/<realm-name>`) into `/settings/sso`.

### Troubleshooting

A failed SSO login redirects to `/login?sso_error=<code>`:

| Code | Meaning |
|------|---------|
| `disabled` | No OIDC configuration is currently enabled |
| `state` | The CSRF state or session cookie was missing, expired, or didn't match |
| `denied` | The user declined consent at the identity provider |
| `exchange` | The authorization code exchange with the IdP failed (network, SSRF check, or token endpoint error) |
| `token` | The ID token failed validation (signature, issuer, audience, expiry, nonce, or missing `sub`) |
| `unverified` | The IdP did not assert `email_verified: true` (or no email was present) |
| `domain` | The verified email's domain is not in `allowed_email_domains` |
| `config` | Building the authorization request failed (bad issuer, discovery/SSRF failure) |

Every code above is generic by design — no issuer or validation detail is ever exposed
to the browser.

### All features unlocked

Because Rereflect is self-hosted and open-source, SSO has no plan gate, seat limit, or
usage cap — it's available to every organization running the app.

## Single Sign-On (SAML 2.0)

Rereflect also supports **SP-initiated SAML 2.0** single sign-on, alongside password,
Google, and OIDC login (see [Single Sign-On (OIDC)](#single-sign-on-oidc) above) — none
of those change. **All features are unlocked** on self-hosted, so SAML carries no plan
gate. This is a **slice-1** implementation: it covers the common enterprise IdP-login
case, not the full SAML 2.0 feature surface — see [Known limitations](#known-limitations-slice-1)
below before you commit to it.

**No new secret is required.** Unlike the OIDC client secret, the IdP's X.509 signing
certificate you paste in is **public** material — it is stored as plain PEM, never
Fernet-encrypted, so `LLM_ENCRYPTION_KEY` is **not** a prerequisite for SAML (it's still
required for OIDC/CRM secrets if you use those).

### macOS dev note: building `xmlsec`/`lxml` locally

If you run `services/backend-api` directly on macOS (e.g. via `./start.sh`, outside
Docker) rather than through `docker-compose`, `pip install -r requirements.txt` compiles
`lxml` and `xmlsec` **from source** (see the comments above the pins in
`services/backend-api/requirements.txt`) — they must link the same `libxml2`, and the
Docker image's Debian package version doesn't match what's typically on a Mac. Before
installing, install the native libs via Homebrew and point the build at them:

```bash
brew install libxmlsec1 libxml2 pkg-config

export PKG_CONFIG_PATH="$(brew --prefix libxmlsec1)/lib/pkgconfig:$(brew --prefix libxml2)/lib/pkgconfig:$PKG_CONFIG_PATH"
export CPPFLAGS="-I$(brew --prefix libxmlsec1)/include -I$(brew --prefix libxml2)/include"
export LDFLAGS="-L$(brew --prefix libxmlsec1)/lib -L$(brew --prefix libxml2)/lib"

pip install -r requirements.txt
```

The pinned `xmlsec` version differs by platform for the same reason — `1.3.13` on the
Debian container image, `1.3.16` on a brew host — but the Python API the code imports
(`onelogin.saml2.*`) is identical either way; you don't need to change any application
code to develop on macOS.

### 1. Register Rereflect as a SAML SP with your IdP

Create a SAML application/client in your IdP with:

| Setting | Value |
|---------|-------|
| ACS (Assertion Consumer Service) URL | `{BACKEND_URL}/api/v1/auth/saml/callback` — **HTTP-POST binding** — e.g. `http://localhost:8000/api/v1/auth/saml/callback` for a local install. Must match exactly what you register. |
| SP Entity ID | `{BACKEND_URL}/api/v1/auth/saml/metadata` — e.g. `http://localhost:8000/api/v1/auth/saml/metadata`. This is an **identifier string only**: Rereflect does **not** serve a metadata document at that URL in this release, so register it as a literal value with your IdP, not as a fetchable link. |
| NameID format | Any format is accepted. If it's `emailAddress` and contains `@`, Rereflect reads the email straight from the NameID. Otherwise it falls back to an attribute (see the **email attribute** field below, then a default chain of common email-claim names). |
| Assertion signing | **The IdP must sign the assertion itself** (not just the outer response). Rereflect rejects an unsigned or response-only-signed assertion. |

This works with any IdP that can sign SAML assertions and POST them to an ACS URL —
Okta, Azure AD (Entra ID), OneLogin, ADFS, Google Workspace, and Keycloak all qualify.

**The signed assertion must bind to the request it answers.** For this SP-initiated flow,
the IdP's response must echo the original AuthnRequest's ID back as `InResponseTo` on the
assertion's `SubjectConfirmationData` — standard behavior for any SP-initiated SAML
exchange, and every IdP listed above does this by default. This is what stops
assertion-substitution: without it, a validly-signed assertion issued for a *different*
login attempt (the IdP's or another SP's) could be replayed against this one. Note that
Rereflect does **not** require `wantMessagesSigned` (signing the outer Response, on top of
the assertion) — the `InResponseTo` binding lives inside the signed assertion itself, so
requiring message-level signing too would add no further anti-substitution guarantee for
mainstream IdPs.

### 2. Configure in the app

Go to **Settings → SSO** (`/settings/sso`, admin/owner only) — the SAML card sits below
the OIDC card on the same page — and fill in:

| Field | Notes |
|-------|-------|
| IdP Entity ID | Your IdP's SAML issuer/entity identifier |
| IdP SSO URL | Your IdP's SAML SSO endpoint (HTTP-Redirect binding). Must be `https://` and passes an SSRF host check on save. |
| IdP X.509 signing certificate | Paste the IdP's public PEM certificate. Validated as parseable X.509 on save (422 if it isn't). The app never echoes the PEM back — it shows a SHA-256 fingerprint you can cross-check against your IdP console. |
| Email attribute (optional) | Name of the SAML attribute carrying the user's email, if your IdP doesn't send NameID as an email address. Leave blank to use the default chain (`email`, the LDAP `mail` OID, or the standard `emailaddress` claim URI). |
| Allowed email domains | See below — **required**, or nobody can sign in |
| Button label | Optional custom text for the "Sign in with SSO" button |
| Enabled | Turns the login button on/off |

### 3. Allowed email domains: empty means deny-all

An empty `allowed_email_domains` list is **not** "allow anyone" — it is **deny-all**.
You must list at least one domain (e.g. `acme.com`) before any SAML login can succeed;
an identity outside the list is rejected with no account created or linked.

### One SSO protocol per deployment

Rereflect allows **at most one SSO protocol enabled at a time** — SAML and OIDC are
mutually exclusive *when enabled*, not mutually exclusive to configure. You may have
both a SAML config and an OIDC config saved; enabling one while the other is already
enabled is rejected (422 — "only one SSO protocol may be active per deployment"). Only
one SSO button ever appears on the login page.

### JIT provisioning and account linking

- **New user, no existing Rereflect account:** the first successful SAML login
  auto-creates a `member` in the organization that owns the enabled config. There is no
  invite step.
- **Existing password, Google, or OIDC account with the same email:** it is linked to
  the SAML identity (its auth method becomes "both") — matched case-insensitively.
- **Trust model differs from OIDC:** SAML has no `email_verified` claim. A validly
  **signed** assertion's email is trusted outright (the IdP is asserting it under
  signature). An assertion with no usable email is rejected; no account is created or
  linked.

### Known limitations (slice 1)

- **SP-initiated only** — there is no IdP-initiated login (starting from an IdP's own
  app dashboard/tile will not work).
- **No Single Logout (SLO).**
- **No SCIM / directory provisioning** — users are created just-in-time on first login
  only; there is no background directory sync or deprovisioning.
- **Signed, not encrypted, assertions** — Rereflect requires and validates a signed
  assertion but does not support encrypted assertions.
- **Single IdP, single signing certificate** per deployment — one SAML config, one cert.
- **Cert rotation:** because a config holds exactly one certificate, rotate by pasting
  the **new** certificate into `/settings/sso` while the **old** one is still valid and
  configured at the IdP (an overlap window), then cut the IdP over to sign with the new
  key. There is no dual-cert grace period on the Rereflect side. If a bad rotation locks
  out your SSO users, **owner email/password login still works** — that's the
  deliberate fallback, not an oversight.

### Testing against a local Keycloak (SAML)

The same dev-only Keycloak service used for OIDC testing also speaks SAML:

```bash
docker compose --profile dev-idp up keycloak
```

Open the admin console at `http://localhost:8080` and log in with the dev credentials
(`admin` / `admin`). Create a realm, then add a **SAML client** inside it:

- Set the client's **ACS URL** / valid redirect to
  `http://localhost:8000/api/v1/auth/saml/callback`, **POST** binding.
- Enable **assertion signing** for the client (client signature / "Sign assertions").

Then copy the realm's SAML descriptor values — IdP Entity ID, SSO URL, and signing
certificate, visible at `http://localhost:8080/realms/<realm-name>/protocol/saml/descriptor`
— into `/settings/sso`.

### Troubleshooting

A failed SAML login redirects to `/login?sso_error=<code>`:

| Code | Meaning |
|------|---------|
| `disabled` | No SAML configuration is currently enabled |
| `config` | Building the AuthnRequest failed (bad IdP config or an SSRF-gated URL) |
| `state` | The RelayState nonce was missing, malformed, or its signature/TTL check failed |
| `signature` | The assertion's XML signature failed validation against the configured certificate |
| `assertion` | The response/assertion was malformed, unsigned, or failed a structural check |
| `audience` | The assertion's `Audience` did not match the SP entity ID |
| `recipient` | The assertion's `Recipient`/`Destination` did not match the ACS URL |
| `expired` | The assertion was outside its validity window (`NotBefore`/`NotOnOrAfter`, ±60 seconds of clock-skew tolerance) |
| `replay` | This assertion's request ID was already consumed (replay) |
| `unsolicited` | The assertion's `InResponseTo` didn't match a request Rereflect issued |
| `unverified` | No usable email was present in the assertion |
| `domain` | The email's domain is not in `allowed_email_domains` |
| `token` | The assertion had no subject (`NameID`) — rejected before any identity lookup |

Every code above is generic by design — no IdP or validation detail is ever exposed to
the browser.

**A note on `InResponseTo`:** your IdP's signed assertion must include a
`SubjectConfirmationData` element carrying the request's `InResponseTo` attribute —
standard behavior for SP-initiated SAML — since that's what binds the returned
assertion to the specific AuthnRequest Rereflect issued. IdPs that only support
IdP-initiated flows (and so never populate `InResponseTo`) are not compatible with this
slice. Also note the two timestamp checks are held to different tolerances: the
assertion's `Conditions` window (`NotBefore`/`NotOnOrAfter`) gets a ±60 second clock-skew
allowance, while the `SubjectConfirmationData` bearer window is enforced with no added
tolerance.

### All features unlocked

Because Rereflect is self-hosted and open-source, SAML has no plan gate, seat limit, or
usage cap — it's available to every organization running the app.

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

### Redis is required for automation cooldowns

Churn/health automation rules (including the `run_playbook` action triggered by a
`churn_probability_threshold` rule) use a per-(rule, customer) Redis cooldown to fire
at most once per window, so a customer sitting above the threshold doesn't re-trigger
the same rule on every recompute. Redis is already required as the Celery broker in
this stack, so this isn't a new dependency — but if Redis becomes unreachable, the
cooldown check is disabled (fails open) and a persistently-at-risk customer could
re-trigger an `active`-mode rule on every churn-probability recompute instead of once
per window. Keep Redis healthy in production for correct automation behavior, not just
for the task queue.
