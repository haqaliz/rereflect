# PRD — Intercom ingestion, operable on a self-host

**Slug:** `intercom-selfhost-ingestion`
**Branch:** `feat/intercom-selfhost-ingestion`
**Type:** feat (freeform; no GitHub issue)
**Status:** Draft for review gate
**Author:** Rereflect (via `rereflect-begin-fast`)
**Date:** 2026-07-30
**Inputs:** `docs/planning/_card/card.md` (brief), `docs/planning/_card/understanding.md` (dig)

---

## Problem Statement

**Intercom is a source that looks connected and produces nothing.**

It is registered as an `available=True` source type, listed in `README.md:38`, sold on
the landing page, and documented in `docs/SELF_HOSTING.md:1571`. A self-hoster can click
Connect, complete an OAuth flow, see webhook events arrive — and never get a single
feedback item. This has been true in **every release to date**
(`CHANGELOG.md:53-60`).

Three independent defects compose. Each alone is sufficient to produce nothing, which is
why they must be fixed together:

| # | Defect | Evidence |
|---|---|---|
| B1 | The webhook route strips the event envelope before the adapter sees it, so extracted text is always empty | `source_webhooks.py:333` vs `adapters/intercom.py:88-89` |
| B2 | There is no pull path at all — the "connector" is a stub returning `[]` | `worker-service/src/tasks/integrations.py:170-177` |
| B3 | Connect is OAuth-only and 403s without `INTERCOM_CLIENT_ID`; Intercom is the last integration still requiring OAuth | `routes/integrations.py:981-984` |

**Evidence the problem is real, not inferred.** A named external user asked for it
(`DEV-TRACKING.md:252-254`): *"integrating directly with Intercom or Zendesk so feedback
flows in automatically instead of pasting tickets manually. Would save a ton of time on
weekly reviews."* Triaged P1 on 2026-07-29. The Zendesk half of that ask is fully
delivered; the Intercom half is this PRD. Note the user's phrasing — *"flows in
automatically"* — is specifically the **pull** path (B2), the one thing that does not
exist at all.

### Why the credibility cost is the real cost

`DEV-TRACKING.md:298-300` frames this precisely: it is *"a shipped-and-marketed
integration that a self-hoster cannot actually turn on, which is the same credibility
problem as the P0 automations bugs, just on the acquisition path."* Four of the seven
post-1.0.0 user comments independently named privacy/BYOK/OSS as the hook
(`DEV-TRACKING.md:460-466`) — the acquisition path is doing real work, and this is a
visible hole in it.

---

## Goals & Success Metrics

| Goal | Metric | How measured |
|---|---|---|
| Intercom produces feedback items at all | A conversation event yields exactly one `FeedbackItem` | Seam test (route → adapter → item), the artifact whose absence caused B1 |
| Feedback "flows in automatically" without a webhook | A 15-minute beat ingests new/updated conversations since the cursor | Integration test over `intercom_sync.py` with a faked client |
| A self-hoster can connect without an OAuth app | Paste an Access Token → connected, workspace resolved, source auto-provisioned | Route tests mirroring `test_zendesk_integration.py` |
| Ingested feedback reaches the product's value loop | `customer_email` populated → item appears on Customer 360 / feeds health | Test asserting `customer_email` is set from the conversation's contact |
| Webhook signature becomes per-tenant | Verification uses the connecting org's secret, not a global env var | Extends `test_webhook_verifiers_fail_closed.py` (Intercom must stay off `SHADOW_ALLOWLIST`) |
| We can tell whether anyone actually uses it | An operator-visible connected/last-synced/item-count read-out | Status endpoint + settings card |

**Honesty constraint on metrics.** We are **not** claiming an improvement in analysis or
churn quality. This changes *whether feedback arrives at all* and whether it links to a
customer. No accuracy claim is made anywhere in the UI, docs, or changelog.

**Deliberately not a metric: adoption.** Whether self-hosters use Intercom at all is
**unvalidated** — this is failure-mode (1) in the pre-mortem below. The status read-out
exists to *measure* that rather than assume it, following the precedent set by
`usage-decline-churn-labels`' readiness counter.

---

## Users & Scenarios

**Primary persona — the self-hosting operator.** Runs Rereflect on their own
infrastructure, BYOK or local LLM, support team already on Intercom. Today they paste
Intercom conversations into CSV imports for weekly reviews.

*Scenario:* Operator opens Settings → Integrations → Intercom, creates a private app in
the Intercom Developer Hub, pastes the Access Token and the app's Client Secret.
Rereflect validates the token, resolves the workspace, auto-provisions an Intercom
feedback source, and begins pulling conversations every 15 minutes. New conversations
appear as analyzed feedback items linked to the customer who wrote them. Optionally the
operator points an Intercom webhook at Rereflect for real-time delivery; the same dedup
core guarantees one item per conversation either way.

**Secondary persona — an existing OAuth-connected operator.** Their connection keeps
working and starts producing feedback items for the first time, with no action required.

---

## Key Decisions (settled at interview, 2026-07-30)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Token-paste with a per-org `client_secret`**, shipping both pull and a per-tenant-verified webhook | Intercom's own docs designate the Access Token as the path for *"building a private app"* to access *"your own Intercom workspace"* — exactly this use case, and the HubSpot private-app-token precedent. Since the token requires creating an app, and `X-Hub-Signature` is HMAC-SHA1 over the body keyed by **that app's `client_secret`**, the operator necessarily has both. Storing the secret per-org makes verification per-tenant and **dissolves** the defect the 1.0.0 changelog recorded as unfixable: *"A valid signature cannot identify a tenant here."* |
| D2 | **`customer_email` side-loading is in scope** | Without it, Intercom feedback is invisible to Customer 360, health scores and churn (`SELF_HOSTING.md:1589-1592`). Ingesting items nobody can act on is a thin win — this is pre-mortem failure-mode (2). |
| D3 | **Delete the dead `BaseConnector` layer** in this branch | It is dead for **both** providers (`ZendeskConnector.fetch_new_items` is also a stub, `tasks/integrations.py:180-190`) yet `sync_all_integrations` runs on the daily beat (`celery_app.py:121`). Leaving it standing is what invites the next person to "just implement `fetch_new_items`" — the wrong seam. |
| D4 | **Keep the OAuth path** alongside token-paste | Removing it breaks existing connections. Cost is accepted: two credential sources and a union in the tenancy discriminator, which R1 below makes a tested requirement. |
| D5 | **No historical backfill.** Cursor starts at `connected_at` | Inherited verbatim from `zendesk_sync.py:36-37` (D1 there): never epoch/None, so a missing cursor can never trigger a mass backfill. |
| D6 | **One Intercom connection per org**, symmetric across both credential paths | Precedent: Zendesk's one-row-per-org, and the one-CRM-per-org guard (`AI-TRACKING.md:203`). Prevents the ambiguity R1 guards. |
| D7 | **No plan gate** | `CLAUDE.md` § *Plans & Feature Gating* — everything is unlocked; adding a gate is the drift class that broke ~40 tests before 1.0.0. |

---

## Requirements

### Must-have

**R1 — Fix the envelope handoff, and pin the seam.**
The route passes the **full payload** as `event_data`; the adapter is unchanged.
`tests/test_intercom.py:438` currently asserts `event_data=payload["data"]` and must be
**rewritten, not extended** — it pins the defect. A new **seam/contract test** must run
the route's actually-queued payload through the real adapter and assert a `FeedbackItem`
with non-empty content results.
*Why a seam test specifically:* both sides were already tested — the adapter against the
full envelope (`worker-service/tests/test_intercom_adapter.py:18+`, passing) and the
route against the stripped shape (passing) — and their mutual disagreement survived
because **nothing tested the join**. `DEV-TRACKING.md:441-446` already generalized this
family ("green tests over code that never executes in production"); this is the fourth
instance and the test must be shaped so either side drifting fails it.

**R2 — Token-paste connect.**
New per-org table (`IntercomIntegration`, one row per org) storing Fernet-encrypted
`access_token` and `client_secret`, a `token_hint`, the `workspace_id` resolved from
`GET https://api.intercom.io/me` at connect time, `last_synced_at` (pull cursor),
`last_sync_status`/`last_error`, `is_active`, `connected_by_user_id`, `connected_at`.
Routes `POST /connect`, `GET /status`, `DELETE /disconnect`, `POST /sync-now`, modelled
on `zendesk_integration.py` — **including `dependencies=[Depends(require_admin_or_owner)]`
on every one** (`zendesk_integration.py:367`). The token is validated against `/me`
before storage (422 on auth failure, 502 on transient upstream). Neither secret is ever
returned in a response or written to a log. One Alembic migration, chained off the
**live-verified** single head `12a1003fbfe0`.

**R3 — Tenancy: the discriminator must cover both credential paths, provably.**
`_find_matching_sources`' `intercom` branch (`source_events.py:150-171`) currently matches
only `Integration.config['workspace_id']` (OAuth). It must also match
`IntercomIntegration.workspace_id` → `organization_id`, mirroring the Zendesk branch's
shape (`source_events.py:193-207`).
**Hard constraints, each individually tested:** a missing/empty `workspace_id` returns
`[]` (never falls through); the union must never widen to another org's sources; and the
`workspace_id` written into `provider_context` is always the **trusted stored column**,
never a value derived from the payload — the constraint `zendesk_sync.py:17-20` states as
non-negotiable. This is the code path the P0 hardened, so characterization tests must
prove the existing guarantees are preserved byte-for-byte.

**R4 — Per-tenant webhook verification, failing closed.**
Verification uses the connecting org's stored `client_secret`, falling back to the global
`INTERCOM_CLIENT_SECRET` for OAuth-connected orgs.
*Resolving the ordering problem:* the route must know the org to choose a secret, but
`app_id` lives in the not-yet-verified body. It may parse `app_id` from the unverified
payload **solely to select candidate secrets**, then verify. A forged `app_id` selects a
secret whose HMAC will not validate, so the path still fails closed; this reasoning must
be a comment at the call site, not tribal knowledge. Requires a bounded body read before
parse. Intercom must **remain absent** from `SHADOW_ALLOWLIST`
(`tests/test_webhook_verifiers_fail_closed.py:47-50`) and the enumerating test must stay
green.

**R5 — Pull path (`intercom_sync.py` + `clients/intercom.py`).**
A dedicated worker module mirroring `zendesk_sync.py`, **not** the deleted
`BaseConnector`. It must:
- route every fetched conversation through the **shared** ingestion core
  (`_find_matching_sources` + `_process_event_for_source`) rather than creating
  `FeedbackItem`s ad hoc — this is what makes pull and webhook share one dedup path
  (`zendesk_sync.py:8-15`, and the card's explicit guardrail);
- synthesize a uniform `conversation.user.created` event and let `FeedbackSourceEvent`
  dedup enforce "one item per conversation, ever" instead of guessing new-vs-updated
  (`zendesk_sync.py:41-44`);
- advance the cursor from `last_synced_at ?? connected_at` (D5);
- treat a static auth failure as operator-recoverable — record
  `last_sync_status`/`last_error` **without** flipping `is_active` and without retrying
  (`zendesk_sync.py:45-48`);
- run in-process inside one DB session per org, not a Celery hop per conversation
  (`zendesk_sync.py:38-40`);
- never log the token (`zendesk_sync.py:50`); return
  `{"status": "error", "reason": "missing_encryption_key"}` without retrying when
  `LLM_ENCRYPTION_KEY` is unset (`zendesk_sync.py:51-52`).
15-minute interval beat, registered in `celery_app.py`.
**Cursor semantics must be adapted, not copied** — Zendesk's incremental endpoint returns
an `end_time` watermark; Intercom's conversation search is `updated_at`-filtered with
`starting_after` cursor pagination. The plan must verify the endpoint's contract
(filtering, pagination, rate-limit headers) before implementing against it.

**R6 — Auto-provision a *working* feedback source.**
`_ensure_default_feedback_source` must seed a truthy trigger. `adapters/intercom.py:42-57`
reports a trigger match **only** if one of `all_conversations` / `new_conversations` /
`replies` / `ratings` is truthy; a source provisioned without one silently drops every
delivery. This is the identical trap Zendesk documented and seeded around
(`zendesk_integration.py:346-352`). A test must assert the auto-provisioned source
ingests out of the box.

**R7 — `customer_email` from the conversation's contact (D2).**
Resolved client-side and merged as a flat field **before** the item reaches the shared
core, mirroring how `ZendeskClient.incremental_tickets` side-loads `users` into
`requester_email` (`zendesk_sync.py:22-34`). Applies to both pull and webhook paths.
Absent/unavailable contact email must degrade to today's behaviour (`source_metadata`
only) rather than failing ingestion.

**R8 — Delete the dead connector layer (D3).**
Remove `BaseConnector`, `IntercomConnector`, `ZendeskConnector` and the
`sync_all_integrations` beat entry. Confirm no other caller first. This removes a
scheduled daily no-op.

**R9 — Frontend: a dedicated Intercom page.**
`settings/integrations/intercom/page.tsx` + `__tests__`, following
`settings/integrations/zendesk/page.tsx` (the pattern with a shipped testing precedent)
rather than extending the OAuth wizard at `settings/integrations/new/page.tsx`, which
stays intact for D4. Token + secret paste, validation, connected state with
workspace/last-synced/last-error, "Sync now", disconnect, and the integrations-tile entry.
No secret is ever rendered after connect.

**R10 — Documentation must stop being false in the same commit that makes it so.**
Every one of these currently-true statements becomes false and must be updated:
`SELF_HOSTING.md:1581-1596` (webhook-only, no periodic pull, daily sync is a no-op, no
token-paste path), the known-limitation block at `SELF_HOSTING.md:1674`, the env table at
`SELF_HOSTING.md:1614`, `CHANGELOG.md:53-60`, `README.md`, plus a new `AI-TRACKING.md`
Intercom row and closure of `DEV-TRACKING.md:252` / `:293` / `:378`.

### Should-have

- **S1** — Operator-visible ingested-item count per source, so adoption is measurable
  rather than assumed (pre-mortem 1).
- **S2** — `429` / `Retry-After` throttle handling in the client, matching the
  Jira/Asana status-sync precedent (`AI-TRACKING.md:59`).
- **S3** — Correct the stale pre-pivot plan-tier copy at
  `frontend-web/app/signup/page.tsx:341` ("2,500 feedback/mo · Slack & Intercom ·
  Priority Support"), which contradicts `CLAUDE.md` § *Plans*. Trivial, adjacent, and
  exactly the drift class the repo has been burned by.

### Nice-to-have

- **N1** — Configurable trigger selection (topics/keywords) in the UI; the adapter
  already supports it (`adapters/intercom.py:42-67`).
- **N2** — Bounded, opt-in historical backfill (explicitly against D5's default).

---

## Technical Considerations

**Services touched:** `backend-api` (route fix, new integration module, model +
migration), `worker-service` (new sync task + client, discriminator branch, dead-layer
deletion, beat), `frontend-web` (new page + client + tile), docs. `analysis-engine` is
untouched — items enter the existing analysis pipeline unchanged.

**Multi-tenancy** is the dominant risk surface. R3 modifies the exact function the P0
cross-tenant fix hardened, and this branch *widens* it to a second credential source.
Characterization tests over the existing guarantees are mandatory before the widening
lands.

**Cross-process boundary.** worker-service cannot import backend-api (`CLAUDE.md` §
*Automations engine*): the worker image copies only `worker-service/src` and
`analysis-engine/src/analyzer`. Anything shared is mirrored, and **a bare `except` around
an import in worker-service is a defect on sight**. The new client lives at
`worker-service/src/clients/intercom.py` (joining `zendesk/jira/asana/hubspot/salesforce`).

**Migration.** One revision off the live-verified head `12a1003fbfe0`. Never determine
`down_revision` by grepping version files — that has caused a fabricated fork and an id
collision in this repo. Re-run `alembic heads` live before and after.

**Encryption.** `encrypt_api_key`/`decrypt_api_key` (Fernet) for both secrets, with the
`LLM_ENCRYPTION_KEY`-unset path returning 422 at connect and a non-retrying error in the
task — both mirrored from Zendesk (`zendesk_integration.py:414-424`, `zendesk_sync.py:51`).
Note this branch does **not** fix `oauth-tokens-stored-plaintext`
(`DEV-TRACKING.md:402`) for the legacy Slack/Intercom OAuth rows — that needs a backfill
migration and stays a separate card. The new table is encrypted from birth.

**SSRF.** Intercom's host is fixed (`api.intercom.io`), so unlike Zendesk there is no
per-org subdomain and therefore no DNS gate needed — the same reasoning Asana recorded
(`AI-TRACKING.md:61`).

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| K1 | **Widening the tenancy discriminator re-opens the P0.** | Characterization tests first; missing-`workspace_id` → `[]` tested per path; trusted-column-only rule tested. |
| ~~K2~~ | ~~Private apps may not be able to subscribe to webhooks~~ — **RESOLVED 2026-07-31, favourably.** Intercom's docs: webhook subscriptions are configured per-app under *Developer Hub → Configure → Webhooks*, and "for **private apps**, the Intercom data you access is your own, so you're already good to go". R4 stays in scope. | **New constraint carried into R4's plan:** "you can only subscribe to webhooks now via your Developer Hub — API-based subscription is not available." Rereflect **cannot auto-provision the subscription**; the operator configures the endpoint + topics manually. This is a docs requirement (mirroring Zendesk's manual webhook setup), not a code one. |
| K3 | Intercom's conversation-search pagination/rate-limit shape differs from Zendesk's incremental model. | R5 requires verifying the endpoint contract before implementing; S2 covers throttling. |
| K4 | **Nobody connects it** (pre-mortem 1) — adoption is unvalidated. | S1 measures rather than assumes. Stated as an honest limit, not hidden. |
| K5 | Conversation→contact resolution costs an extra API call per conversation. | Side-load/batch where the API allows; degrade gracefully per R7. |
| K6 | Deleting the `BaseConnector` layer touches Zendesk's registered-but-dead path. | Confirm no live caller; Zendesk's real pull (`zendesk_sync.py`) is provably independent of it. |

~~**Open question O1:** does an Intercom private app expose webhook topic subscription
(K2)?~~ **Closed 2026-07-31 — yes**, via Developer Hub → Configure → Webhooks; private
apps need no additional permission scopes. Subscription is Developer-Hub-only (no API),
so setup instructions are the deliverable, not provisioning code.
**Open question O2:** exact conversation-search filter/pagination contract (K3).

---

## Out of Scope

- **Write-back to Intercom** (notes, closing conversations). `intercom_service.py` remains
  orphaned — verified zero production callers on 2026-07-30. It is outbound; this card is
  inbound. The P2 call to wire-or-delete it (`DEV-TRACKING.md:433`) stands separately, and
  **no "Two-Way Sync" copy may return** until it is wired.
- ~~**Write-back to Intercom**~~ — **SHIPPED 2026-08-15**: the wire-or-delete P2
  landed as **wire it** — opt-in note + close on resolve, off by default,
  resolved-only; `intercom_service.py` is deleted. See
  `docs/planning/intercom-writeback/`.
- **Encrypting the legacy Slack/Intercom OAuth tokens** (`DEV-TRACKING.md:402`) — needs a
  backfill migration; separate card.
- **RBAC on `routes/integrations.py`** (`DEV-TRACKING.md:422`) — the new routes enforce it,
  but auditing/fixing that whole module is a separate card.
- **`jwt-secret-default`** (`DEV-TRACKING.md:399`) — flagged at interview as plausibly
  more urgent than this feature ("far larger blast radius"); the user chose this card with
  that on the table. Recorded here so the trade is visible, not forgotten.
- ~~Per-conversation-part ingestion~~ — **SHIPPED 2026-08-15**
  (`intercom-pull-replies-and-ratings`): the pull enriches replies + the rating via
  conversation-parts, one item per conversation. See
  `docs/planning/intercom-pull-replies-and-ratings/`.
- Intercom Articles/Tickets objects, status-sync back to Intercom, multiple Intercom
  workspaces per org, IdP-style app marketplace listing.
- Any claim of improved analysis or churn accuracy.

---

## Proposed Aspect Decomposition

Ordered by dependency. Each is independently testable and buildable.

| Aspect | Boundary |
|---|---|
| `envelope-seam-fix` | R1 only. The one-line route fix, the rewritten route assertion, and the new seam test. Unblocks everything and is independently shippable. |
| `token-paste-connect` | R2 + R6 + D6. Model, migration, routes, `/me` validation, auto-provisioned source with a seeded trigger. |
| `tenancy-discriminator` | R3. The union branch plus characterization tests over the P0 guarantees. |
| `webhook-per-org-secret` | R4 + K2. Per-tenant verification, fail-closed, allowlist test intact. Gated on O1. |
| `pull-sync` | R5 + R7 + S2 + K3. Client, sync task, cursor, contact side-loading, beat registration. |
| `frontend-intercom-page` | R9. Dedicated page, tests, API client, tile. |
| `cleanup-and-docs` | R8 + R10 + S1 + S3. Dead-layer deletion, docs/changelog/tracking truth-up. |
