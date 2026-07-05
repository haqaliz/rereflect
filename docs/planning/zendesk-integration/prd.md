# PRD — Zendesk Inbound Feedback-Source Integration

**Slug:** `zendesk-integration` · **Branch:** `feat/zendesk-integration` · **Type:** feat (freeform)
**Status:** Draft (pre review-gate) · **Date:** 2026-07-05
**Positioning:** Open-source, self-hosted, BYOK. All features unlocked (no plan gating).

---

## Problem Statement

Support tickets are the single richest, highest-intent customer-feedback channel for most SaaS
teams, and **Zendesk is the most widely used support platform**. Rereflect already ingests
Intercom conversations and pushes to Jira/Linear, but a Zendesk-based team has **no first-class
path** to get their tickets analyzed — they'd fall back to manual CSV exports, losing freshness,
requester identity, and the automatic flow into churn/health scoring.

The integration surface is visibly incomplete: `AI-TRACKING.md:158` and `DEV-TRACKING.md:206`
list Zendesk as pending, and `services/worker-service/src/tasks/integrations.py:180` ships a
`ZendeskConnector` **placeholder** ("TODO: Implement actual Zendesk API integration") that returns
nothing. **Evidence it's real:** the exact same inbound-source slice has already shipped three
times (Intercom, Jira, Linear), and the landing site already advertises Zendesk as "coming soon"
(`services/landing-web/lib/integrations.ts:269`), so the demand signal is already public.

**Who has the problem:** self-hosting operators (founders / CS leads / support leads) whose
support system of record is Zendesk.

## Goals & Success Metrics

| Goal | Metric |
|---|---|
| A self-hoster can connect Zendesk and see tickets become feedback with zero code | Connect → first ticket analyzed, no manual step beyond pasting a token / setting a trigger |
| Zendesk tickets ride the full existing pipeline | Ingested items get sentiment, categories, churn/health signal, appear in Customer 360 by requester email |
| Ingestion is exactly-once | No duplicate feedback for the same ticket across repeated syncs / redelivered webhooks |
| Parity with shipped integrations | `zendesk` selectable in the source wizard; connect/status/disconnect/test all work; landing page flips to "available" |
| Ships green | All new backend/worker/frontend tests pass; branch stays green per task |

Non-numeric by design (single-tenant OSS; no central analytics to set adoption targets against —
consistent with the honest OSS brand).

## User Personas & Scenarios

- **Operator (admin/owner)** connects Zendesk in Settings → Integrations: pastes subdomain +
  agent email + API token, clicks Connect, sees "Connected as {agent}". Optionally sets up a
  Zendesk trigger/webhook for real-time. Creates a `zendesk` feedback source in the wizard.
- **Member** browses feedback and Customer 360; Zendesk-sourced items are labeled with a Zendesk
  icon and carry the requester as `customer_email`, so they roll into health/churn like any other.

## Requirements

### Must-have

1. **Connection (own-auth, Jira pattern).** `zendesk_integrations` table (one row/org),
   Fernet-encrypted API token. `POST/GET/DELETE /api/v1/integrations/zendesk/{connect,status,
   disconnect,test}`, `require_admin_or_owner`, org-scoped. Token never returned in any response.
2. **`ZendeskClient`** (mirror `jira_client.py`): Basic auth `("{email}/token", api_token)`, base
   `https://{subdomain}.zendesk.com/api/v2`, `validate()` → `GET /users/me.json`, typed error
   taxonomy (auth→422, transient→502, notfound).
3. **Two-layer SSRF gate:** route normalizes/asserts host is `*.zendesk.com` + `getaddrinfo`
   rejects loopback/private/link-local (422); client re-asserts scheme + host suffix at
   construction. Missing `LLM_ENCRYPTION_KEY` → 422, never 500.
4. **Source-type registration:** `zendesk` in `feedback_sources.py` `/types`
   (`requires_integration=False`, own-auth) and `valid_types`.
5. **Ingestion core (shared):** a `ZendeskAdapter(BaseSourceAdapter)` — `check_triggers`,
   `extract_content` (ticket subject + description → text + metadata), `get_external_ids`
   (dedup key = ticket id), optional `fetch_context`. Registered in `adapters/__init__.py`
   `get_adapter`. A `zendesk` branch in `source_events._find_matching_sources` matching
   `provider_context["subdomain"]` → the org's Zendesk source. **Both** ingestion entry points
   funnel through this one core and the existing `FeedbackItem` + `FeedbackSourceEvent` creation
   (so there is a single tested creation + dedup path).
6. **Ingestion entry point A — Pull (default):** Celery beat task polls
   `GET /api/v2/incremental/tickets` (or search) with the stored token, cursor = `last_synced_at`,
   **new tickets only** (from connection time forward, no historical backfill), synthesizes events
   and routes them through the ingestion core. Updates `last_synced_at` / `last_sync_status` /
   `last_error`.
7. **Ingestion entry point B — Webhook (optional real-time):** `POST /api/v1/webhooks/zendesk/events`,
   HMAC-verified (shared secret shown on connect), forwards the payload through the same ingestion
   core. Operator wires a Zendesk trigger/webhook to it.
8. **Granularity:** one feedback item per ticket (subject + description). Dedup on ticket id across
   both pull and webhook.
9. **Customer mapping:** set `feedback.customer_email` from the ticket requester email so items
   feed Customer 360 / health / churn.
9a. **Connection ↔ source relationship (must be explicit).** Connecting stores credentials only;
    tickets flow **only** once a `zendesk` `FeedbackSource` exists for the org (the wizard creates
    it, matched by subdomain). If a ticket arrives (pull or webhook) with **no matching active
    source**, it is a **logged no-op** — never a crash, never a silent "success". Decision for the
    plan: either (a) the connect flow **auto-provisions** a default `zendesk` source, or (b) the
    connect UI explicitly routes the operator to create one and status shows "connected, no source
    yet". Default recommendation: (a) auto-provision, so connect→flow works without a second step.
9b. **Graceful degradation (observability).** Missing requester email → ingest item with no
    `customer_email` (not dropped). Analysis failure, unmatched subdomain, or missing source →
    logged + reflected in `last_sync_status`/`last_error` (pull) or structured log (webhook); never
    a silent drop.
10. **Frontend (app):** `ZendeskIcon`, `lib/api/zendesk.ts`, connect page
    `settings/integrations/zendesk/page.tsx` (subdomain + email + token; mirror Jira), integrations
    list tile + Active block, the 4 feedback-source pages' `SOURCE_ICONS`/`SOURCE_COLORS`, the
    `new` wizard's `zendesk` branch, `TRIGGER_OPTIONS.zendesk`.
11. **Landing + docs:** flip landing `zendesk` entry `coming_soon`→`available`, fill
    `setupSteps`/`useCases`, swap the page to the full available layout; add Zendesk token +
    webhook setup to `docs/SELF_HOSTING.md`.
12. **TDD throughout:** mirror `test_jira_connection.py`, `test_jira_client.py`,
    `test_feedback_sources_jira.py`, `test_intercom_adapter.py`, `lib/api/__tests__/jira.test.ts`.

### Should-have

- Manual "Sync now" trigger on the connect page (reuse the beat task on demand).
- `last_error` surfaced in the connect UI (parity with Jira status display).

### Nice-to-have / v2 (out of scope, see below)

- Per-comment ingestion; status/tag/view filters; historical backfill; OAuth; multiple
  subdomains per org; write-back / bidirectional status sync to Zendesk.

## Technical Considerations

- **Services touched:** `backend-api` (model, migration, client, routes, source-type reg, webhook
  route), `worker-service` (adapter, source-matching branch, pull beat task), `frontend-web`
  (connect UI + wizard + api client + icon), `landing-web` (page + data).
- **Multi-tenancy:** every route org-scoped; `zendesk_integrations` unique on `organization_id`;
  ingestion resolves org via subdomain → Integration → FeedbackSource.
- **Reuse, don't fork:** connection = Jira template; ingestion core = Intercom adapter template;
  both ingestion entry points share the one `FeedbackItem`/`FeedbackSourceEvent` creation path.
- **Alembic:** repo has **multiple heads** — run `alembic heads`, set `down_revision` correctly
  (or add a merge revision) before authoring the `zendesk_integrations` migration.
- **Secrets:** API token Fernet-encrypted at rest; webhook HMAC secret stored per integration;
  neither ever logged or returned.

### Data Model (proposed)

`zendesk_integrations`: `id`, `organization_id` (FK, unique), `subdomain`, `email`,
`api_token` (encrypted), `token_hint`, `webhook_secret` (encrypted, nullable),
`account_user_id`, `display_name`, `is_active`, `last_synced_at`, `last_sync_status`,
`last_error`, `connected_by_user_id`, `connected_at`, `created_at`, `updated_at`.

### API Contracts (proposed)

- `POST /api/v1/integrations/zendesk/connect` — `{subdomain, email, api_token}` → status (+ webhook secret), no token.
- `GET /api/v1/integrations/zendesk/status` — connection status, hints, last sync/error.
- `DELETE /api/v1/integrations/zendesk/disconnect` — soft delete.
- `POST /api/v1/integrations/zendesk/test` — re-validate; never 500s.
- `POST /api/v1/webhooks/zendesk/events` — HMAC-verified ingestion entry point B.

## Risks & Open Questions

- **R1 — "Both" doubles ingestion surface.** Mitigated by the shared-core design (one creation +
  dedup path, two thin entry points), but there are still two entry points to test. *Accepted by
  user with eyes open.*
- **R2 — Un-productionized pull loop.** The existing poll loop is inert; we harden it by routing
  pulled tickets through the adapter/creation core rather than the legacy `BaseConnector` path.
  The legacy `ZendeskConnector` stub will be retired or left unwired.
- **R3 — Zendesk incremental API cursor + rate limits.** Cursor semantics (unix-time `start_time`,
  1000/page, `end_of_stream`, 5-min window rules) *and* **account-wide rate limits** (429 with
  `Retry-After`). The multi-org beat fan-out must throttle **per integration** and honor
  `Retry-After` — not just generic exponential backoff. Plan confirms exact endpoint + cursor +
  throttle.
- **R4 — Webhook requires public ingress**; documented as an optional real-time add-on, pull works
  without it. **Signature scheme to pin in the plan:** Zendesk modern webhooks send
  `X-Zendesk-Webhook-Signature` = base64(HMAC-SHA256(signing_secret, `timestamp + raw_body`)) with
  `X-Zendesk-Webhook-Signature-Timestamp`; verify over the **raw** body.
- **R5 — Alembic multiple heads** could misparent the migration. Resolve head before authoring.
- **R6 — Silent-drop risk.** See must-have 9a/9b: unmatched subdomain / no source / missing
  requester must be logged no-ops, asserted in tests, so ingestion failures are observable.
- **OQ1 — Webhook secret delivery UX:** generate on connect and display once, or regenerate button?
- **OQ2 — Auto-provision source on connect (9a option a) vs guided creation (option b)** — plan to lock.

## Out of Scope (explicit)

Per-comment / conversation-thread ingestion; historical backfill on connect; status/tag/Zendesk-view
filters; OAuth marketplace flow; multiple Zendesk subdomains per org; any write-back or status sync
**to** Zendesk; Zendesk Sell/Sunshine; AI-drafted ticket replies. All deferred to v2.
