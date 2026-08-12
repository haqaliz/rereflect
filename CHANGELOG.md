# Changelog

All notable changes to Rereflect (the open-source, self-hosted edition) are documented here.
Every feature is unlocked; the app runs on your own infrastructure with your own (or a local) LLM key.

Prior work lives in the git history and the tracking files (`AI-TRACKING.md`, `DEV-TRACKING.md`).

## Unreleased

### Customer outreach — shared email primitives (opt-out, unsubscribe, cooldown)

The foundation for reaching churn-risk customers by email, shared by the playbook
`send_email` step and the bulk "Trigger outreach campaign" action (both consume these
primitives; the send surfaces themselves land with their own changes):

- **Opt-out, honored on every send path** — `customer_health_scores.outreach_opt_out`
  (default false). Customers opt out via the tokenized **`List-Unsubscribe`** link every
  outreach email carries (`GET /api/v1/outreach/unsubscribe?token=…` — public, stateless
  HMAC token keyed by `LLM_ENCRYPTION_KEY`, no token table). Operators can also flip the
  flag with `PATCH /api/v1/customers/{email}` (admin/owner, `{"outreach_opt_out": bool}` —
  extra fields 422). An opted-out customer is never emailed; the skip is loud
  (`skipped: opted out`), never silent.
- **Per-recipient cooldown** — one outreach per customer per window per org (Redis DB 1,
  `outreach_cooldown:{org_id}:{customer_email}`, window `OUTREACH_COOLDOWN_HOURS`, default
  24, env-configurable). In-cooldown sends record `skipped: in cooldown`.
- **Built-in template registry** — `GET /api/v1/outreach/templates` exposes the two seeded
  template keys (`re_engagement`, `weekly_digest_entry`) with plain-text bodies; registry is
  data, so content can iterate without code.
- **Honest no-key failure** — with `RESEND_API_KEY` unset, every send attempt records
  `failed: email not configured` instead of a false success.
- **Audit trail schema** — `outreach_campaigns` + `outreach_campaign_recipients` tables
  (per-campaign + per-recipient status/error rows) land with this change; the bulk send path
  that writes them ships with its own aspect.

Resend-only, BYO-key: no SMTP, nothing phones home. See *Outbound email (Resend)* in
`docs/SELF_HOSTING.md`.

### Playbook `send_email` steps now execute (worker engine)

The seeded playbooks' `send_email` steps ("At-Risk Outreach" → weekly digest to the CS
assignee; "Silent-Churn Watch" → re-engagement email to the customer) actually send now
instead of failing every run as `unsupported action type`. Recipients: `customer` (the
execution's customer email) or `cs_assignee` (the customer's assigned CS owner — missing
owner is a loud per-step failure, never silent). Rendered from the built-in registry via
the worker mirror; every outcome (sent/skipped/failed) is recorded loudly in the playbook
execution's `action_log`. Opt-out, cooldown, List-Unsubscribe and no-key handling remain
the shared sender's (above) — no reimplementation here.

### Bulk "Trigger outreach campaign" — send, preview, audit trail, retry

The operator-facing bulk send path on `/customers` now exists (admin/owner):

- **`POST /api/v1/customers/bulk/outreach`** — resolve a cohort (`emails[]` list or the
  same filter vocabulary as the customers list), write one `outreach_campaigns` row + one
  `outreach_campaign_recipients` row per customer, and enqueue one Celery task per
  sendable recipient. Responds `202 {matched, queued, skipped, errors}` — the request
  returns a summary, never a blocking send.
- **Loud queue-time skips** — blank/non-email, opted-out (`outreach_opt_out`) and archived
  customers land in `skipped` with a reason on their recipient row; filter-mode default
  excludes archived from `matched` exactly like the customers list UI. Cooldown is not
  checked at queue time — the worker sender re-checks at send time.
- **`?count_only=true` preview** — `200 {matched, queued: 0, skipped, errors: []}` with
  zero mutation, so the UI can show the true count before the 500-cap 422 on the real run.
- **Campaign audit trail** — `GET /api/v1/outreach/campaigns` (page/page_size, newest
  first) returns per-campaign recipient status counts (`queued/sent/skipped/failed`) from
  one GROUP BY — no N+1.
- **Dead-worker recovery** — `POST /api/v1/outreach/campaigns/{id}/retry` re-enqueues only
  `queued` recipients (terminal rows are immutable); no-op 200 zeros when nothing is
  queued; cross-org campaign id → 404.
- **AI draft** — `POST /api/v1/customers/bulk/outreach/draft` LLM-drafts `{subject, body}`
  from org context (product name, brand voice, tone) plus optional cohort context (count +
  dominant segment only — raw emails/search never reach the model). 409 when no LLM is
  configured. The draft never sends: no campaign rows, no dispatch.

Task-name discipline: the worker task `tasks.outreach.send_outreach_email` is dispatched by
name from both send endpoints — a single string, pinned by tests in both suites.

### Playbook editor: `send_email` steps are now editable, and the profile can opt a customer out

The frontend half of the outreach send surfaces:

- **Per-step config in the playbook editor** — a `send_email` step now shows **template**
  and **recipient** selects (options from `GET /api/v1/outreach/templates`; the two
  contract-pinned built-in keys `re_engagement` / `weekly_digest_entry` fall back if the
  registry is unreachable, so editing never bricks). Cloning "At-Risk Outreach" or
  "Silent-Churn Watch" pre-populates both selects and re-saves the exact seeder shape
  `{type: "send_email", config: {template, recipient}}`. Unknown template keys from old
  playbooks render with a warning and are preserved on save, never blanked. The template
  card badge shows a Mail icon + "Send Email".
- **Per-customer opt-out toggle** — the Customer 360 profile header now has a "Send
  outreach emails" switch (admin/owner) that PATCHes `{"outreach_opt_out": bool}`; the
  switch is hidden entirely for members.

### Notifications — Discord now has its own per-type channel preference

Settings → Notifications now shows a **Discord** channel switch for each alert type, default
on. Slack and Discord are routed independently:

- A type can now be **Discord-only** (Slack off) or **Slack-only** (Discord off) — previously
  Discord rode the Slack toggle, so "Slack off" also silenced Discord.
- The one behavior change: a type with Slack **off** and Discord **on** now delivers to
  Discord. Existing installs (both on, or both off) behave exactly as before.
- Automations' `send_notification` action still cannot target Discord (unchanged).

### Security — Inbound webhooks accepted unsigned requests, and could write to the wrong organization

**If you run Rereflect with more than one organization on a single instance, upgrade.**
Set `SLACK_SIGNING_SECRET` and `RESEND_INBOUND_WEBHOOK_SECRET` if you use the Slack or
inbound-email sources; see *Inbound webhook signing secrets* in `docs/SELF_HOSTING.md`.

Three problems, each of which was the shipped default rather than an edge case:

- **Signature verification failed open.** The Intercom, Slack, inbound-email and Linear
  verifiers each returned "valid" when their signing secret was unset — and none of those
  secrets appeared in any `.env.example`, compose file or doc, so unset *was* the default
  state of every install. Zendesk, Jira and Asana were already correct.
- **A missing tenant discriminator matched every organization.** The worker's source-matching
  query is not scoped by organization; each provider branch narrows it only when a
  payload-supplied id is present. Four branches had no guard for the missing case and fell
  through to "every active source on the instance." Only Zendesk was guarded — it had been
  fixed once, in isolation, and the identical shape was left standing everywhere else.
- **`/api/internal/events/emit` shipped with a public default secret.** It defaulted to the
  literal `"dev-secret"` in an open-source repository, compared it non-constant-time, and
  took the target `org_id` straight from the request body. This one required no integration
  to be configured at all.

**What this means in practice.** On a default install, an unauthenticated caller who knew a
webhook URL could cause writes attributed to organizations they had no relationship with. We
want to be precise rather than dramatic about what those writes were: a separate payload-shape
bug meant Intercom deliveries never produced feedback items, so what actually landed was a
source-event log row carrying attacker-supplied JSON under another organization's id. That bug
was an accident, not a safeguard — it was the only thing standing between this and arbitrary
feedback injection, which is why the tenancy fix landed first and why the shape fix is
deliberately still pending.

**Fixed:** Intercom and Linear now fail closed; the tenancy guard is applied to all four
unguarded branches; `INTERNAL_EVENTS_SECRET` has no default and is compared in constant time.
A new test enumerates every signature verifier in the codebase and asserts each fails closed,
so this cannot be fixed one verifier at a time again.

**Grace period for Slack and inbound email.** Both are in live use, so flipping them closed
immediately would have silently stopped real feedback for anyone running without a secret.
They still accept unsigned deliveries for now, but log a `SECURITY-SHADOW` warning on every
request, warn at startup when an active integration has no secret, and are flagged in
Settings → Integrations. A future release rejects them. The test allowlisting them fails the
moment that happens, so the grace period cannot quietly become permanent.

### Fixed — Intercom ingestion never produced a feedback item, in any release

If you connected Intercom and saw events arriving but no feedback appearing, that was this
bug, not your configuration.

Deliveries were received and authenticated correctly, but the webhook route handed the
worker's Intercom adapter only the inner `data` object while the adapter reads `topic` and
`data.item` off the **full** envelope. It therefore saw an empty topic and an empty item on
every delivery, extracted empty text, and stopped before creating anything. The route now
passes the whole envelope.

**Why it survived two green test suites.** Both halves were tested and both passed — the
adapter against the full envelope, the route against the stripped one — and they disagreed
with each other. Nothing tested the *seam*, because the two halves live in different
services that cannot import each other. The fix therefore ships with a golden envelope
fixture committed once and read by both suites: the backend asserts "this is what I send",
the worker asserts "given this, I produce a feedback item". Either side drifting now breaks
its own assertion.

### Security — `JWT_SECRET` is now required, and two webhook weaknesses are closed

**If you never set `JWT_SECRET`, set one before upgrading — the app will not start without
it, and that is deliberate.**

`JWT_SECRET` fell back to a value published in this repository, and `.env.example` shipped
the variable commented out, so unset was the default state of an install following the docs.
Every authentication token on such an install could be forged by anyone who read the source;
the same key signs OIDC and Salesforce OAuth state. Generate one with `openssl rand -hex 32`.
Existing sessions are invalidated when you set it — tokens signed with the old default should
never have been trusted. Setting `JWT_SECRET` to that former default is rejected explicitly.

**Zendesk webhook replay.** The signature timestamp was included in the HMAC but never
checked for freshness, so a captured delivery could be resent indefinitely and would verify
every time. Because status reconciliation runs before de-duplication, a replayed "ticket
closed" could undo manual triage repeatedly. Deliveries older or newer than 300 seconds are
now rejected, matching the guard Slack's verifier already had.

**Credentials in the event log.** The generic inbound webhook stored all request headers
verbatim, including the source's own `X-Webhook-Secret` — the credential that authenticates
the endpoint — so read access to that table was enough to forge deliveries. Credential
headers are now stripped before anything is persisted.

### Fixed — Editing an automation rule's categories did nothing

The automation detail page wrote its category-match settings under key names the backend does
not read, so editing an existing rule appeared to save and changed nothing about what the rule
matched. Creating a rule was unaffected. Rules saved while this was broken still show their
values in the editor, and saving them again now persists correctly.

### Added — Intercom now connects with a pasted token and pulls on its own

Intercom was the last integration that still required registering an OAuth app, which is
awkward on a self-host and is exactly why every other integration — Zendesk, Jira, Asana,
HubSpot — takes a pasted credential instead.

**Connect with an access token.** Create a private app in your Intercom Developer Hub, copy
its Access Token from Configure → Authentication, and paste it into
**Settings → Integrations → Intercom**. Rereflect validates it, resolves your workspace and
provisions the feedback source. This is Intercom's own recommended path for accessing your
own workspace. Existing OAuth connections keep working; an organization uses one path or the
other.

**Conversations pull every 15 minutes.** Previously Intercom had no pull at all — if the
webhook was not wired, nothing ever arrived. This is what the original request ("so feedback
flows in automatically") actually asked for. The pull and the webhook share one
de-duplication path, so a conversation becomes one feedback item however it reaches you.

**Webhook signatures are now verified per workspace.** The 1.0.0 notes recorded this as
impossible: *"a valid signature cannot identify a tenant here"*, because the signing key was
a single global environment variable. Supplying your app's Client Secret at connect time
changes that — deliveries are verified against your workspace specifically. It is optional;
without it the pull still works, and webhook deliveries are rejected rather than trusted.

**Intercom feedback now reaches Customer 360.** Items carry the customer's email, so they
feed health scores and churn signals like every other source. A reply written by one of your
own admins will not overwrite the customer on the item.

*Honest limits:* up to 15 minutes of latency without a webhook; the pull ingests the first
message of a conversation, with replies and ratings arriving via webhook only; a large
backlog drains over several runs. No claim is made about analysis quality — this changes
whether feedback arrives and whether it links to a customer, nothing else.

### Fixed — A weekly cleanup job had never run

The beat schedule referenced `tasks.churn_playbooks.purge_old_executions`, missing the `src.`
prefix every other entry carries, so it resolved to nothing and the 90-day purge of playbook
execution records never ran. Found by a new test that resolves every scheduled task name to
a real function — the same "wired at one end, dead at the other" shape as the Intercom
envelope bug above, caught by a guard rather than by a user.

Fixing it activates a delete, so the timing matters: churn playbooks shipped 2026-07-19, so
no execution is 90 days old yet and the first run removes nothing. Left unfixed for another
three months, the first successful run would have purged a real backlog with no warning.

### Fixed — We were telling people shipped integrations didn't exist

A 1.0.0 user asked us to build Intercom and Zendesk ingestion "so feedback flows in
automatically instead of pasting tickets manually." Both already shipped. They asked
because our own landing-page FAQ told them Zendesk was **planned** — four months after it
shipped — and because the README described the product as ingesting only "CSV, email,
webhooks and Slack," omitting Intercom, Zendesk, Jira, Linear and Asana.

Corrected everywhere: the FAQ, both README source lines, and the `SELF_HOSTING.md`
outbound-call table (which claims to be the exhaustive list of every network call a
Rereflect instance makes, and was missing Intercom, Linear and Discord — a gap that
undercuts the zero-telemetry claim it exists to support).

The landing page also advertised Intercom **"Two-Way Sync"** — adding notes back to
conversations and closing resolved tickets. That never worked. The code exists but nothing
in the app has ever called it, so the claim is removed rather than softened.

### Added — Intercom self-hosting guide

`docs/SELF_HOSTING.md` gained a "Connecting Intercom" section. Intercom is the one
integration that requires OAuth rather than a pasted token, which means the operator must
register an Intercom app and set `INTERCOM_CLIENT_ID`, `INTERCOM_CLIENT_SECRET` and
`INTERCOM_REDIRECT_URI` before anything works — and none of that was documented anywhere,
so clicking "Connect to Intercom" on a fresh install just failed with no way to find out
why. The three variables are now in `.env.example` and `.env.prod.example` too.

**Known limitations, stated plainly in the guide:** Intercom is **webhook-only** — unlike
Zendesk there is no polling fallback, so if you don't subscribe the webhook, nothing
arrives at all. `INTERCOM_REDIRECT_URI` defaults to `localhost:8000` and must be overridden
on any real deployment. The integration must be connected *before* you create the feedback
source. Intercom feedback is not linked to a customer profile automatically — the contact
email lands in `source_metadata`, not on the item itself, so Customer 360 enrichment does
not happen the way it does for Zendesk.

If you want support tickets flowing in with the least setup, Zendesk remains the better
path: a pasted API token, and polling that works without exposing any public URL.

### Added — Discord alerts

Rereflect can now post alerts to Discord. Settings → Integrations → Discord, paste a
webhook URL from your server, done — no OAuth app to create.

Urgent feedback, sentiment spikes, churn risk, volume spikes, and customer health
drop/recovery alerts all reach Discord.

This closes the last piece of a 1.0.0 user request for "Slack **or Discord**" pings.
Pointing the existing custom-webhook feature at a Discord URL never worked: it saves,
because the validator accepts any `https://` URL, but Discord requires a body with
`content` or `embeds` and we posted our own envelope, so Discord returned 400 and only the
delivery log showed it.

**Known limitation:** Discord has no channel preference of its own yet, so it rides on the
existing **Slack** toggle in Settings → Notifications. If you enable Discord but switch that
toggle off, you get nothing; if you have both integrations, both receive every alert. Also
not covered: automation-rule notifications, custom message templates (they're authored in
Slack `mrkdwn`, which renders as literal asterisks on Discord), the per-integration alert
log, and `429` retry. See `docs/SELF_HOSTING.md`.

### Added — Batch sentiment threshold automation trigger

A new automation trigger, `batch_sentiment_threshold`, fires when the share (or absolute
count) of a given sentiment across your **whole** incoming feedback stream crosses a
threshold over a trailing window.

Every existing trigger asks about one customer. The closest one, `sentiment_pattern`, fires
when a single customer sends N negative feedbacks within D days — so a spike of 30 angry
feedbacks from 30 *different* customers triggered nothing at all. That aggregate case is
what this covers, and it was a direct request from a 1.0.0 user who wanted to be pinged for
triage.

Configurable: `sentiment`, `window_hours` (1–168), `mode` (`percentage` or `count`),
`threshold`, and `min_total` — a sample floor, because two negative items out of three is
67% and a percentage threshold without a floor is a false-alarm generator.

The shipped "Batch Sentiment Alert" template starts in **shadow mode**. The defaults
(50% negative, 24h, floor of 5) are a reasoned starting point, **not a measured
calibration** — how often they fire depends entirely on your volume. Review the shadow
execution log, tune, then arm it. See `docs/SELF_HOSTING.md`.

Delivery reuses the existing notification channels, including the Slack channel fixed
earlier in this release.

### Fixed — Churn `resolution_time` factor was permanently dead

The `resolution_time` churn factor (10 of the 100 points in every customer's churn score)
has never actually run. `_compute_heuristic_churn_risk` imported `FeedbackWorkflowEvent`
from `src.models.feedback_workflow_event`, a submodule that has never existed in
worker-service — the class is exported from `src.models` directly. The `ModuleNotFoundError`
was swallowed by a bare `except Exception: pass`, so `resolution_score_pts` was always `0`
and every customer's factor breakdown showed `"Insufficient resolution data"` as if that
were a real finding, since churn explainability shipped (M1.4). This is the third instance
of the same bug class in this repo — worker-service importing a backend-api-only path inside
a bare `try/except` (see GitHub #3, `f5d43234`; and `52c763dd`).

**Effect on your data:** on each customer's next analysis, churn scores can rise by up to 10
points, and some customers will move up a risk band, purely because this factor starts
contributing for the first time — not because anything about those customers changed. This
is a correction, not new risk. Historical `churn_risk_factors` rows are **not** backfilled by
this fix (fix-forward, no bulk rewrite); they keep their stale `"Insufficient resolution
data"` label until each item is naturally re-analyzed. If you want existing rows recomputed
immediately, `services/backend-api/scripts/backfill_churn_factors.py` exists for exactly that
and can be run as an opt-in operator command — it is not run automatically by this fix.

While fixing this, the other four customer-level factors (`sentiment_trend`,
`feedback_frequency`, `pain_severity`, `feature_density`) — which shared the same untested
gap, just not the same bug — got DB-backed tests proving each one does score correctly.
The `except Exception: pass` blocks around all five customer-level factors now log a warning
naming the failed factor instead of swallowing it silently, so this class of bug can't hide
again the same way. Per-factor isolation is unchanged: one failing factor still can't void
the other eight.

### Security — Slack and Intercom OAuth tokens are now encrypted at rest

`Integration.oauth_access_token` is Fernet-encrypted before storage for Slack and Intercom,
exactly like every other integration credential. Both OAuth callbacks encrypt on write
(saving without `LLM_ENCRYPTION_KEY` returns 422, never 500), all read sites decrypt on read,
and the worker's alert/sync paths decrypt locally rather than importing the backend.

**If you are upgrading an existing install, set `LLM_ENCRYPTION_KEY` before running
migrations.** The upgrade migration encrypts existing plaintext rows in place and **fails
closed** when the key is unset — `alembic upgrade head` aborts with a `RuntimeError`
containing a generate-a-key command rather than leaving your OAuth tokens in plaintext.
Operators who never set the key (integration saves already required it) should generate one
with that command, add it to `.env`, and re-run `alembic upgrade head`. See *Integration
credential encryption & the upgrade requirement* in `docs/SELF_HOSTING.md`.

### Security — Linear webhook secrets are now encrypted at rest

`LinearIntegration.webhook_secret` — the HMAC key that authenticates inbound Linear
webhook deliveries — is Fernet-encrypted before storage, closing the last plaintext
credential in the system (every other integration already encrypted at rest). The OAuth
callback encrypts on write (saving without `LLM_ENCRYPTION_KEY` returns 422, never 500),
and the webhook receiver decrypts exactly once at signature verification, logging a
diagnostic warning when a stored secret cannot be decrypted instead of accepting the
delivery.

**Same upgrade requirement as the OAuth tokens above: set `LLM_ENCRYPTION_KEY` before
running migrations.** The upgrade migration encrypts existing plaintext rows in place and
fails closed when the key is unset. See *Integration credential encryption & the upgrade
requirement* in `docs/SELF_HOSTING.md`.

## v1.0.0 — 2026-07-26

**The 1.0 release.** Feature work for this milestone was already complete — every PRD in the
roadmap shipped. What 1.0 adds is the engineering foundation a project should have before it asks
anyone to depend on it:

- **Continuous integration.** The repo had no workflows at all. CI now runs the backend suite
  (against a real Postgres, migrated from scratch, with a single-Alembic-head assertion), the
  worker suite, and the frontend's lint + tests — on every pull request.
- **A green test suite**, verified in CI: **backend 4501, worker 1345, frontend 1496**. Around
  sixty tests across the three suites had rotted against the code they cover, and
  `test_report_ws.py` was excluded wholesale. All of it is fixed, or explicitly and visibly
  skipped with the reason recorded. Several of the failures were hiding real bugs: deleting a
  Copilot folder deleted it as a conversation, the automation trigger editor called a hook
  conditionally, the AI provider card crashed its own render on a missing field, and the
  sentiment-anomaly suite only passed at certain times of day.
- **The last of the SaaS scaffolding removed.** "Promo Codes" still appeared in the admin sidebar
  and rendered a page whose backend route was never mounted — a guaranteed-broken screen. That
  surface, the Stripe service stub behind it, and the dead `promo_code_used` column are gone.
- **Honest docs and versions.** Every service now reports 1.0.0, shipped PRDs moved out of the
  repo root into `docs/archive/prd/`, and the stale Stripe/plan-gating/npm references left over
  from the hosted era are corrected.

### Added — Durable classifier rollback + version history

### Added — Durable classifier rollback + version history

The per-org self-improving classifiers (M5.2) already let you roll back an auto-promoted
model, but that rollback didn't stick: the classifier refits **weekly (Mondays 06:30 UTC)**
and would silently re-promote a fresh challenger over your manual choice within a week.

Rollback is now **durable**. Rolling back pauses auto-promotion for that classifier type
(a per-type hold, shown as **"Auto-promotion paused"** on the Accuracy tab); the weekly
refit still trains and records the incumbent-vs-challenger delta but no longer changes the
live model until you click **Resume auto-promotion**. The Accuracy tab now also shows a
**version-history list** (fit date, macro-F1, labels, which is live) and lets an admin/owner
**roll back to any prior version**, not just the most recent. A *disable-only* rollback
(no prior version) does not pause auto-promotion, so a first model can still be trained.
Rollback, pause, and resume are recorded in the audit log. Holds are per classifier type —
pausing sentiment never affects category or urgency.

New endpoints (`/api/v1/settings/ai`): `GET /classifier/versions`, `POST /classifier/resume`,
and `POST /classifier/rollback` now accepts an optional `to_version_id`. Completes the M4.2
"model versioning / rollback if accuracy drops" item.

### Added — Local embedding model

A second in-process embedding option for the AI Copilot's template matching, alongside the
existing cloud/Ollama providers: an opt-in, CPU-only `sentence-transformers` provider
(`BAAI/bge-small-en-v1.5`, 384-dim) that runs directly inside the backend — no separate
Ollama/endpoint process required. Set per organization (Settings → AI, embedding provider
`local`).

- **In-process CPU provider.** No GPU, no separate model server; the `sentence-transformers`
  dependency already ships alongside the transformer sentiment model (M5.1), so this doesn't
  add a second heavy package family.
- **Air-gap pre-bake.** `BAKE_EMBEDDING_MODEL=true docker compose -f docker-compose.prod.yml
  build backend` bakes the ≈130 MB of weights into the image at build time (backend only —
  the worker has no embedding consumers); combined with `HF_HUB_OFFLINE=1` /
  `TRANSFORMERS_OFFLINE=1` for a container with no runtime network access at all. Off by
  default — a default build makes no network call and bakes no weights.
- **Model-keyed template matching.** Switching an org's embedding model/provider re-embeds the
  built-in query templates automatically; vectors from different providers/models are never
  mixed, so a model switch can't silently corrupt matching.
- **Committed, honest retrieval eval + accuracy card.** An offline harness scores candidate vs.
  baseline on recall@1, MRR, and false-match rate on held-out negatives; the result is
  committed and surfaced on the same **Settings → AI → Accuracy** tab as the sentiment/classifier
  cards.

#### Known limits, stated plainly

- Candidate `bge-small` beats the `nomic-embed-text` baseline by **+0.089 recall@1** (0.178 vs
  0.089) on the committed eval set (n=69: 45 held-out paraphrases / 24 negatives), with no
  false-match regression — a real, measured improvement.
- **Absolute recall@1 is still low** at the strict 0.85 match threshold the Copilot uses: most
  held-out paraphrases don't clear it and fall through to the LLM path rather than a fast
  template match. That's the safe failure mode (a slower, still-correct answer), not a broken
  one. MRR≈0.75 shows the right template usually ranks near the top even when it doesn't clear
  the threshold. This is not presented as a solved-accuracy claim.
- The Ollama embedding-model recommendation is now eval-backed too: `nomic-embed-text` remains
  the default (neither Ollama alternative clears the recall@1 bar), and `mxbai-embed-large` is
  documented as an optional modest upgrade (better ranking, fewer false matches, higher
  RAM/latency) — see [SELF_HOSTING.md](docs/SELF_HOSTING.md#embedding-model-choice-on-the-ollama-path-eval-backed).

### Added — Usage-decline churn-label suggestions

A second, CRM-free source of churn-label *suggestions* for the review queue introduced by
`crm-churn-labels`. Aimed at self-hosters with product usage telemetry but no HubSpot/Salesforce
connection — previously their only way to record a churned customer was typing it into "Mark
as churned" one at a time.

A customer qualifies only when their usage trend has held in `sharp_decline` for a configurable
number of **consecutive calendar days** (`sustain_days`, default 7, range 1–90) — the milder
`declining` state never qualifies, and it's a level-based streak read off the daily usage-trend
snapshot, not a one-shot edge trigger. Qualifying customers become a pending suggestion in the
**existing** churn-suggestions queue (`provider=usage_decline`), alongside CRM suggestions. **A
suggestion is never a label** — a human still has to confirm it from the review queue before it
becomes a real, trainable churn event. Nothing is auto-applied.

- **Off by default, with a shadow mode** (Settings → AI → Usage-Decline Churn Labels). Shadow
  evaluates and logs what it would suggest without writing anything — recommended first, since
  a sustained usage decline is weaker evidence than a lost renewal and more prone to false
  positives (seasonal dips, one customer on leave).
- **Population-level outage guard.** If more than 25% of an org's trend-eligible customers (once
  there are at least 20 of them) qualify in the same run, the entire run is suppressed and
  logged loudly instead of writing suggestions — the far more likely explanation at that scale
  is a broken usage pipeline, not simultaneous, independent churn.
- **Idempotent per decline episode.** Re-detecting the same ongoing streak never creates a
  duplicate suggestion; a genuinely new episode after a recovery can suggest again.
- **Runs after the daily usage-snapshot commit**, in its own transaction, isolated per customer
  so a single bad row can't fail the parent job.
- **Settings card shows a live precision read-out** — confirmed / rejected / pending counts for
  this source, since a self-hosted product has no way to report an aggregate number back to us.

#### Known limits, stated plainly

- **~12–16 day warm-up, plus the `sustain_days` window on top.** With the default of 7 days,
  routinely three weeks or more between an actual drop in activity and a suggestion appearing.
- **The ≥5 active-day baseline floor permanently excludes light-usage customers.** Inherited
  from the underlying trend classifier — a customer who was never very active can never produce
  a suggestion, which is also plausibly your most churn-prone segment.
- **Only recently-declining customers are visible.** A customer who went quiet or churned before
  the detector's lookback window has no baseline to compare against and will never surface here.
- **Requires usage events to already be flowing.** Inert if you haven't wired up the usage
  webhook.
- **This does not change churn prediction.** It changes label *supply*, not the churn model —
  whether more labels improve any model is a separate, open question, and no particular label
  count is promised.

### Added — Usage-trend timeline event and automation trigger

The usage-decline signal now reaches the action loop. Previously a declining customer only
nudged the usage health component — and since the usage weight defaults to `0`, for most
operators nothing observable happened at all.

**New `usage_trend` automation trigger.** Fires when a customer enters a worse trend state,
and can run a churn playbook via the existing `run_playbook` action (composing with the
churn-triggered playbooks shipped earlier).

- **Edge-triggered.** It fires on the *transition* into `declining` / `sharp_decline`, not for
  as long as the customer sits there. A customer who stays `declining` fires once, on the day
  they get there.
- **The first classification never fires.** A customer moving out of `insufficient_history` is
  a baseline observation, not a change — the same non-destructive first-observation rule the
  Jira/Zendesk/Asana status-syncs use. Without it, every customer whose history matured on the
  same day would fire at once.
- **Recoveries don't fire.** `declining → stable` is visible on the timeline but triggers
  nothing, for now.
- **Defaults to shadow mode** — uniquely among trigger types. Because the trend needs ~14 days
  of snapshot history before it can classify anything, a rule armed on day one would sit silent
  and then execute unobserved. Shadow lets you watch it first, then arm it.

**New `usage_trend_change` timeline event** on the Customer 360 profile, so an automated
outreach has a visible cause. Unlike the trigger, the timeline records *every* state change in
both directions, including recoveries.

**Pre-built "Usage Decline Outreach" template** in Settings → Automations, so the trigger is
findable without knowing it exists. It ships with a notification action rather than a playbook
action — playbook IDs are per-install, so a static template can't reference one; add your own.

**Readiness count.** The AI readiness surface now reports how many of your customers hold a real
(non-`insufficient_history`) trend state — i.e. whether this trigger can fire for you at all.

#### Known limits, stated plainly

- **~14-day warm-up.** Snapshot history only began accumulating recently, so expect little to
  happen at first.
- **Light-usage customers are permanently excluded.** Trend classification requires a baseline
  of at least 5 active days in the prior 14-day window. A customer below that never receives a
  trend state, so this trigger cannot fire for your quietest accounts. Inherited from the trend
  detector itself; not a bug, and not something this release changes.
- **Up to ~24h latency.** The trigger rides the daily 04:00 UTC recompute. There is no
  real-time path, and a 14-day-window trend wouldn't benefit from one.
- **This does not change churn prediction.** `churn_probability`, its confidence interval, and
  the calibration model are provably untouched — enforced by a test that drives a real trend
  transition and asserts every churn field is byte-identical.

### Fixed — Shadow-mode automation runs no longer look like failures

Automation executions in shadow mode were logged by the backend with status `shadow`, but the
frontend's status type didn't include it, so they rendered as a red **failed** badge with an
empty actions column — indistinguishable from a real failure. Shadow runs now render as their
own state. Affects all shadow-mode rules, not just the new trigger.

### Added — Product-usage trend as a churn signal

Rereflect now detects when a customer's product engagement is **declining**, not just whether
it's currently high or low — the case where a customer is quietly disengaging while still
nominally active, which the health score previously couldn't see.

- Each customer carries a **usage trend** — Stable, Declining, or Sharp Decline — derived daily
  by comparing their active-days over the last two weeks against their *own* activity about two
  weeks earlier. It shows on the **Usage Activity** card on the customer profile, with the signed
  change.
- A declining trend applies a **bounded penalty to the usage component of the health score** (and
  only that component). It never touches churn probability or its calibration — those remain
  driven by feedback signals, so existing churn models are unaffected.
- **Warm-up is honest.** The trend needs about two weeks of daily history before it can say
  anything; until then a customer shows **"Warming up"** rather than a fabricated "stable". A
  fresh install therefore shows warm-up for its first ~2 weeks — that's expected, not a fault.
- History is stored in a new bounded, self-pruning table (180-day retention), so it can't grow
  without limit.

This is a heuristic decline signal on your own data, stated as such — no accuracy-lift claim, and
nothing is shared across tenants. A company-wide holiday can read as a decline; per-org tuning and
seasonality handling are future work.

### Fixed — Health-score weights: usage is now editable, and saving no longer wipes usage/CRM

The **Settings → AI → Health Score Weights** editor showed four weights but the health score has
six components (the usage and CRM weights were added with the product-usage and CRM-enrichment
features). Two consequences, both now fixed:

- **You can now set the Usage Activity weight from the UI.** Previously it could only be changed
  through the API, and the in-app instructions pointed at a page that had no weight editor.
- **Saving weights no longer silently resets your usage and CRM weights to 0.** Because the save
  only sent four of the six weights, any usage or CRM weight you had configured was wiped on the
  next save — with a success message and no warning. The editor now sends all six, and the
  "must sum to 100" total counts all six.

If a weights load fails, saving is now blocked rather than proceeding from defaults — so a
transient error can't overwrite a configured weight with 0.

### Fixed — Product-usage metrics now track elapsed time

**If you have opted into usage weighting, some customer health scores will go down after this
upgrade. That is a correction, not a regression** — those scores were overstated.

The rolling-window fields on a customer's usage rollup (`active_days_7d/30d`,
`login_count_7d/30d`) were only ever recomputed when a new usage event arrived. For a customer
whose product usage slowed or stopped, they stayed frozen at their last-event values
indefinitely — only the recency signal decayed. Two consequences:

- **Health scores were inflated** for quiet customers, because the frequency part of the usage
  score (30% of it) kept reporting activity that had long since stopped.
- **The `silent_churner` segment could never fire.** It requires fewer than 5 active days in the
  last 30, and that number never fell. The segment built specifically to surface silent
  customers was unreachable for exactly those customers; they showed up as `dormant` instead.

The daily 04:00 UTC recompute now re-derives these windows against the current time, so a
customer who goes quiet — or merely slows down — is reflected in their usage score, health
score, and segment.

**Orgs that have not opted into usage weighting are unaffected.** The usage weight defaults to
0, and health scores in that case are byte-identical before and after; this is locked by a
characterization test.

> **If you have opted in, read this before upgrading.** The correction can move a customer's
> `risk_level` (in our test fixture, `moderate` → `at_risk`), not just their numeric score. A
> risk-level downgrade is on its own sufficient to dispatch a health-drop alert, and
> `health_score_threshold` / `churn_risk_level_change` automation rules key off the same
> transitions. So the **first daily recompute after upgrading may produce a burst of alerts and
> automation runs** for customers whose scores were previously inflated — correct outcomes, all
> at once. If you run automations against health or risk level, consider pausing them for the
> first run after upgrade.

Also adds an `active_days_14d` window field (nullable, populated on the first daily run after
upgrade; no backfill and no migration downtime).

### Added — Single sign-on (OIDC)

Self-hosted deployments can now wire in their own identity provider for login. It sits **alongside**
the existing email/password and Google sign-in — neither of those changes — and, like everything in
the open-source edition, it is fully unlocked with no tier or seat gate.

- **OIDC authorization-code login** (PKCE, signed state + nonce) against any provider that issues
  **RS256**-signed ID tokens — Okta, Azure AD, Google Workspace, Keycloak, and other conformant IdPs.
- **Configured in-app** at **Settings → SSO** (`/settings/sso`, admin/owner only): issuer URL, client
  id, client secret (stored Fernet-encrypted, never returned), an email-domain allowlist, and an
  enable toggle. One enabled configuration per deployment.
- **Just-in-time provisioning**: a first-time SSO user is created as a `member` in the configured
  organization; an existing password/Google account with the same **verified** email is linked rather
  than duplicated. `email_verified` is required.
- **Deny-by-default access**: the email-domain allowlist is deny-all when empty — you must name at
  least one domain, so a misconfigured multi-tenant issuer cannot mass-provision accounts.
- **Server-side hardening**: the operator-supplied issuer and every discovered endpoint
  (discovery, JWKS, authorize, token) are checked for HTTPS, private-IP/SSRF, and issuer-host
  containment before any request; the client secret is never logged or sent cross-host.
- Requires `LLM_ENCRYPTION_KEY` (the same Fernet key that protects other integration secrets) — now
  documented in `.env.example`. A dev **Keycloak** service is available via
  `docker compose --profile dev-idp up keycloak` for local testing. See the **Single Sign-On (OIDC)**
  section of `docs/SELF_HOSTING.md`.
- **Known limitation**: only RS256-signed ID tokens are accepted today (ES256 and other algorithms are
  not); SAML is supported separately — see the SAML entry below.

### Added — Single sign-on (SAML 2.0)

Self-hosted deployments can also wire in a **SAML 2.0** identity provider — a slice-1, SP-initiated
implementation covering the common enterprise-login case. It sits alongside password, Google, and OIDC
login (none of those change), and, like everything in the open-source edition, is fully unlocked with
no tier or seat gate.

- **SP-initiated SAML login** against a single operator-configured IdP: the IdP's assertion **must be
  signed** (unsigned or response-only-signed assertions are rejected). Identity is read only from the
  SAML library's signature-validated getters — never the raw XML — closing the XML Signature Wrapping
  (XSW) door.
- Strict validation of `Audience` (against the SP entity ID), `Recipient`/`Destination` (against the ACS
  URL), `NotBefore`/`NotOnOrAfter` (±60 second clock-skew tolerance on the assertion's `Conditions`
  window; the `SubjectConfirmationData` bearer window gets no added tolerance), and `InResponseTo` —
  plus one-time replay/unsolicited-response rejection via a server-side pending-request store.
- The IdP SSO URL is SSRF-gated (HTTPS + private-IP checks) both at config-save time and again at login
  time.
- **Configured in-app** at **Settings → SSO** (`/settings/sso`, admin/owner only, same page as OIDC):
  IdP Entity ID, IdP SSO URL, IdP X.509 signing certificate (PEM; the API returns a SHA-256 fingerprint,
  never the raw PEM back), an optional email-attribute override, an email-domain allowlist, a button
  label, and an enable toggle.
- **Just-in-time provisioning**: a first-time SAML user is created as a `member` in the configured
  organization; an existing password/Google/OIDC account with the same email (matched case-insensitively)
  is linked rather than duplicated. SAML has no `email_verified` claim — a validly **signed** assertion's
  email is trusted outright.
- **Deny-by-default access**: the email-domain allowlist is deny-all when empty, same as OIDC.
- **One SSO protocol per deployment**: enabling SAML while an OIDC config is enabled (or vice versa) is
  rejected — at most one of {OIDC, SAML} may be enabled at a time.
- No new secret: the pasted X.509 certificate is public material, stored as plain PEM (not
  Fernet-encrypted), so `LLM_ENCRYPTION_KEY` is not a SAML prerequisite. The dev **Keycloak** service
  (`docker compose --profile dev-idp up keycloak`) also speaks SAML for local testing. See the
  **Single Sign-On (SAML 2.0)** section of `docs/SELF_HOSTING.md`.
- **Known limitations (slice 1)**: SP-initiated only — no IdP-initiated login; no Single Logout (SLO);
  no SCIM/directory provisioning; assertions are signed but not encrypted; single IdP and single signing
  certificate per deployment (see the docs for the cert-rotation procedure and the owner-login lockout
  fallback).

### Fixed — telemetry: Sentry is now opt-in and off by default

Earlier builds initialized Sentry unconditionally with a **hardcoded DSN pointing at the
maintainer's Sentry project**, and with `send_default_pii=True` — in the backend, the Celery
worker, and the Next.js server/edge/browser runtimes. A self-hosted install therefore sent
crash reports (and, on the browser side, session replays) off-box with no disclosure and no way
to turn it off short of editing source. That contradicted the project's core claim that your
data never leaves your box.

- **Sentry now initializes only when you set `SENTRY_DSN`** (and `NEXT_PUBLIC_SENTRY_DSN` for
  browser-side reporting). Unset — the default — means the SDK is never initialized and the
  instance makes no outbound calls of its own.
- **`send_default_pii` is now `False`** everywhere, so no user emails, usernames or IPs are
  attached to events even when you do enable it.
- **No DSN is hardcoded anywhere.** If you enable Sentry, it reports to *your* project.
- Removed the Sentry wizard's leftover `/sentry-example-page` and `/api/sentry-example-api`
  routes, which shipped in the app and existed only to throw test errors.
- Telemetry is now documented in `docs/SELF_HOSTING.md` and guarded by regression tests
  (`services/backend-api/tests/test_sentry.py`), which previously passed vacuously — they
  asserted against logic copied into the test body instead of the real module.

**If you ran an earlier build:** rebuild your images (`docker compose -f docker-compose.prod.yml
build`) — a stale frontend image has the old DSN baked in at build time.

### CRM-sourced churn label suggestions (opt-in, human-confirmed)

- **Lost renewals from your CRM become churn *suggestions*** — if you've connected HubSpot or
  Salesforce, Rereflect can read closed-lost deals/opportunities and propose them as churn
  labels. **Off by default**, and **default-deny**: nothing is suggested until you enable it
  *and* name your **Renewal pipelines** (HubSpot) / **Renewal opportunity types** (Salesforce);
  a deal whose pipeline/type is null or unrecognised produces no suggestion, ever. An
  organization that ignores this feature sees no change anywhere. The harvest runs inside the
  existing daily CRM sync (03:15 / 03:45 UTC) — no new schedule.
- **Nothing is auto-applied.** Suggestions land in a review queue at **Customers → CRM churn
  suggestions** (admin/owner) and become labels only when a human clicks **Confirm** with a
  required reason code. Confirming writes a normal `source='manual'` churn event stamped with
  your user id and linked back to the suggestion; rejecting writes nothing. Bulk confirm/reject
  is capped at 500 per action. No suggestion is ever confirmed automatically, by design: **a lost
  renewal is not always a churn**, which is exactly why a person decides.
- **Optional on-demand backfill** — a one-time pass over closed-lost history with an
  operator-chosen window (12/24/36/60 months, default 24, hard max 60). It is never automatic
  and is not triggered by enabling the feature; it is resumable, idempotent, cancellable, and
  live-progress-reported. Runs are capped at 2,000 suggestions and truncation is **surfaced,
  not silent** — the card names the dropped count and how far back the run actually covered.
  Like everything here, it produces **suggestions, not labels**.
- **Fix — AI readiness now counts only *trainable* labels, so your number may go *down*.**
  `churn_labels_ready` previously gated on the unfiltered `churn_labels_total`; it now gates on
  the new `churn_labels_trainable`, which excludes `source='auto_suggested'` events the
  calibrator never trains on. If your organization has such events, the readiness figure on
  **Settings → AI → Readiness** will drop after this release. **The old number was overcounting;
  the new, lower one is the honest one.** A separate `pending_suggestions` field reports queued
  CRM suggestions and is deliberately **not** counted toward readiness — a pending suggestion is
  not a label.
- **No claim is made about churn-prediction quality.** This feature produces labels. Whether more
  labels change the model is M5.3's open question (see `AI-TRACKING.md`), and churn prediction
  remains a calibrated heuristic. See
  [CRM churn-label suggestions](docs/SELF_HOSTING.md#crm-churn-label-suggestions-opt-in) for setup.

### Public API: bulk feedback writes + custom-category CRUD (v3)

- **Bulk feedback writes** — `POST /api/public/v1/feedback/bulk` (`write` scope) applies one
  patch (`workflow_status` / `tags` / `is_urgent` / `correction` — the same fields as the
  single `PATCH /feedback/{id}`) to up to 500 feedback ids in a single request. The response
  reports `matched` / `updated` / `skipped` counts plus a per-id `results` array
  (`updated` / `noop` / `skipped` / `error`, with a `reason` on skip/error); ids outside your
  organization (or that don't exist) are skipped rather than erroring. Pass
  `?count_only=true` to preview how many ids would match without changing anything.
- **Custom-category (taxonomy) CRUD** — `GET/POST/PATCH/DELETE /api/public/v1/categories`
  (read scope for `GET`, write scope for the rest) lets you manage your custom pain-point /
  feature-request / urgency / general categories over the API, mirroring the existing
  Settings UI. Creating a duplicate `(category_type, name)` returns `409`; an id from another
  organization (or that doesn't exist) returns `404`; `category_type` can't be changed after
  creation. Deleting a category that's still referenced by an active automation rule succeeds
  (204) but carries an `X-Rereflect-Warning` response header naming the rule(s), so you don't
  silently break an automation.

### Self-improving on-device models (M5.2)

- **Per-organization urgency classifier** — a third self-improving head (after sentiment and category),
  trained on your own urgency corrections. It's a small, CPU-only, offline binary model
  (`urgent` / `not_urgent`) whose challenger is promoted only when it beats the built-in
  keyword+sentiment urgency heuristic on your held-out corrections (≥ +0.02 macro-F1), with one-click
  rollback. Off by default; independent `off` / `shadow` / `auto` toggle in Settings → AI.
- You now teach it by simply flipping a feedback item's **urgent flag** — from the new toggle on the
  feedback detail page or via `PATCH /api/public/v1/feedback/{id}`; each user-driven change is recorded
  as a training signal (the analyzer's own automatic flagging is not).
- **Add-only in `auto`, by design.** Because the urgent flag drives churn alerts and the urgent queue,
  the model in `auto` mode can only ever **escalate** an item to urgent — it never silently clears a
  flag the built-in heuristic raised. `shadow` mode logs both directions so you can judge accuracy first.

### Churn-triggered playbook auto-execution

- **Automations can now auto-run a churn-prevention playbook** when a customer's churn probability
  crosses a threshold — a new `churn_probability_threshold` trigger and `run_playbook` action on the
  existing automation-rule engine (Settings → Automations), alongside the existing health-score,
  sentiment, churn-risk-level, and feedback-category triggers.
- **Three-way rule mode**: `off`, `shadow` (evaluate and log what a rule *would* do, without running
  anything), and `active`. Use `shadow` to sanity-check a new rule against real customers before
  letting it take action.
- Auto-runs create the same `ChurnPlaybookExecution` record as a manual/batch run
  (`triggered_by="auto_probability"`) and appear on the customer's timeline as a `playbook_auto_run`
  event, so you can see exactly why a playbook fired.
- **Fires from the existing churn-probability recompute in the worker**, reusing the identical
  per-(rule, customer) Redis cooldown as the other automation triggers — see the new "Redis is
  required for automation cooldowns" note in `docs/SELF_HOSTING.md`.
- **Activating a rule seeds cooldowns for every currently-matching customer up front**, so turning on
  a rule against an existing at-risk cohort doesn't fire a stampede of playbooks in one pass.
- SMTP-free, and — like everything in the open-source edition — fully unlocked with no plan gate.

This closes the deferred "real-time playbook execution on probability threshold cross" item from the
Advanced Churn Prediction PRD (`PRD-ADVANCED-CHURN-PREDICTION.md:465`).

## v0.1.0 — 2026-07-13

First tagged release of the self-hosted edition. Headline theme: **close the integration loop**
(feedback status now stays in sync with your work-management and support tools) and **on-device,
self-improving models** (your data trains small models that run locally and only ship when they're
measurably better).

### Integrations — inbound status-sync (close the loop)

Rereflect could already create work items and ingest tickets; now it keeps the feedback item's
status in sync when the linked item changes on the other side.

- **Jira** inbound status-sync — a linked Jira issue moving to Done (or any status) updates the
  feedback item's workflow status. Poll-first (every 15 min), opt-in per org, off by default.
- **Asana** inbound status-sync — completing (or re-opening) a linked Asana task updates the
  feedback item. Bidirectional; Asana has no intermediate state, so it maps completed vs. not.
- **Zendesk** inbound status-sync — a linked ticket's status (new / open / pending / solved /
  closed) updates the feedback item, via **both** a 15-min poll and an optional real-time webhook.
- Common to all three: opt-in per organization (off by default), a non-destructive first-poll
  baseline (no retroactive bulk rewrites), a manual "Sync now" action, per-organization status
  mapping you can override, and an audit trail — every automatic change writes a timeline entry
  tagged with its source. A hand-set status is never overwritten by a sync unless the linked item
  genuinely changes.
- Built on a shared, provider-agnostic reconcile core, so adding the next tool is incremental.

### Self-improving on-device models (M5.2)

- **Per-organization sentiment and category classifiers** that train on your own feedback and your
  own corrections, run CPU-only and fully offline, and **auto-promote a new model only when it beats
  the current one on held-out data** — with one-click rollback. Off by default; the built-in
  analyzer stays the baseline until a challenger proves itself.
- Honest by design: these are small models, described as such. Churn remains a calibrated heuristic,
  sentiment defaults to VADER, and nothing claims accuracy it hasn't shown.

### Notes

- All of the above is **opt-in and off by default** — upgrading changes no behavior until you turn a
  feature on. Database migrations are additive.
- Fully compatible with bring-your-own-key cloud LLMs and local/offline models (Ollama or any
  OpenAI-compatible endpoint).

See `docs/SELF_HOSTING.md` for operator setup of each integration.
