# Changelog

All notable changes to Rereflect (the open-source, self-hosted edition) are documented here.
Every feature is unlocked; the app runs on your own infrastructure with your own (or a local) LLM key.

This is the first tagged release. Prior work lives in the git history and the tracking files
(`AI-TRACKING.md`, `DEV-TRACKING.md`).

## Unreleased

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
