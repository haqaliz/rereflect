# Phase 2 — Understanding: `feat/intercom-selfhost-ingestion`

**Dug:** 2026-07-30, against the worktree at `feat/intercom-selfhost-ingestion`
(base `dc596f96`). Every claim below is a direct code read with a `file:line`.
Live-verified: single alembic head `12a1003fbfe0`; backend + worker venvs on
Python 3.12.13.

> **Process note.** This dig was run in the main thread. Four parallel dig agents
> were dispatched first (backend / worker / frontend / tests-docs) but all four
> went idle without delivering reports, and nothing was retrievable from them, so
> the mapping was redone directly rather than burning further budget on retries.

---

## What the issue is really asking

A user asked for Intercom/Zendesk feedback to "flow in automatically instead of
pasting tickets manually". Zendesk delivers this today. Intercom is registered,
marketed, documented, and **structurally incapable of it** — for three
independent reasons that have to be fixed together or not at all.

The honest one-line framing: **Intercom is a source that looks connected and
produces nothing.**

---

## F1 — The envelope defect: the route is wrong, the adapter is right

- `services/backend-api/src/api/routes/source_webhooks.py:333` passes
  `event_data=payload.get("data", {})` — the unwrapped `data` object.
- `services/worker-service/src/adapters/intercom.py:88-89` reads
  `event_data.get("topic", "")` and `event_data.get("data", {}).get("item", {})`.
  Same full-envelope assumption at `intercom.py:73` (`_get_body_text`, keyword
  triggers), `intercom.py:148` (`get_external_ids`, the dedup key) and
  `intercom.py:171` (`fetch_context` enrichment) — **four sites, not one.**
- So `topic` is `""` and `item` is `{}` on every delivery: no text, no dedup key,
  no feedback item, ever.

**Which side is the bug is not a judgement call — the tests settle it:**

- `services/worker-service/tests/test_intercom_adapter.py:18,26,34,91-92,109-110`
  feeds the adapter the **full envelope** (`{"topic": ..., "data": {"item": ...}}`)
  and passes. The adapter's contract is the envelope.
- `services/backend-api/tests/test_intercom.py:438` asserts
  `event_data=payload["data"]` — it **pins the defect as correct**.

So the production fix is in the route (pass the whole `payload`), and the RED
step is inverting that one assertion. Note the route already reads the envelope
correctly two lines earlier to derive `conversation_id`
(`source_webhooks.py:319`) — this is a pure handoff slip, not a misunderstanding
of Intercom's shape.

**The generalizable finding:** both sides were tested, both green, in mutual
disagreement, because **nothing tested the seam**. `DEV-TRACKING.md:441-446`
already generalized this exact family ("green tests over code that never
executes in production… a 'is this reachable from an entrypoint?' sweep would
have caught all three"). This is the fourth instance. The missing artifact is a
**contract test on the queue→adapter seam**, and it should be written so that it
fails if either side drifts again — not a test of the route and a test of the
adapter, which is what already exists and what already failed to catch this.

## F2 — The tenancy discriminator silently blocks any token-paste connect

`services/worker-service/src/tasks/source_events.py:150-171` — the Intercom
branch of `_find_matching_sources` requires a non-empty
`provider_context["workspace_id"]` and matches it against
`Integration.config["workspace_id"]`, returning `[]` otherwise (correctly — this
is the P0 tenancy fix).

**Only the OAuth callback populates that config key.** A token-paste connect that
wrote to a different row or a dedicated table would match nothing, and ingestion
would silently produce zero items — the same failure mode as F1, arrived at from
the other direction. Any token-paste design must therefore *also* land a
matching branch here, and that must be a named, tested requirement rather than
an implementation detail.

Zendesk solved the identical problem differently and better
(`source_events.py:193-207`): a dedicated `ZendeskIntegration` table matched by
`subdomain → organization_id`, with the comment explaining exactly why it does
not use `Integration.config`.

**Feasibility, and it is good news:** the existing OAuth callback already calls
`https://api.intercom.io/me` (`integrations.py:1066`) to obtain workspace
identity from a bearer token. That endpoint needs only an access token, so a
token-paste connect can validate the token *and* derive the workspace id in the
same call — exactly the shape of `ZendeskClient.validate()`
(`zendesk_integration.py:397-400`). Token-paste is genuinely reachable.

## F3 — The webhook signature question, and why it may force pull-only

- `verify_intercom_signature` uses the single global `INTERCOM_CLIENT_SECRET` and
  now **fails closed** (`source_webhooks.py:303-304`).
- `tests/test_webhook_verifiers_fail_closed.py:47-50` — `SHADOW_ALLOWLIST` holds
  only `verify_slack_signature` and `email_webhooks._verify_webhook_signature`.
  Intercom is **not** allowlisted, so any new verifier must fail closed to keep
  that test green. Good: the guard rail is already in place.
- Consequence: an install with no `INTERCOM_CLIENT_SECRET` rejects every Intercom
  delivery. A token-paste org has no client secret.

**Unlike Zendesk, a per-org webhook secret may not be available at all.** Zendesk
webhooks are configured *in Zendesk* by the operator, who pastes a secret
Rereflect generated (`zendesk_integration.py:441-453`, display-once). Intercom
signs webhooks with **its app's own client secret**, which Rereflect does not
choose. So the Zendesk pattern likely does not transfer.

> ⚠️ **Marked unverified — the PRD must confirm against current Intercom docs.**
> I have not verified against Intercom's live documentation whether (a) an access
> token can be obtained without a Developer Hub app, and (b) whether an operator
> who *does* create an app to get a token therefore also has a client secret that
> could be stored per-org. Both bear directly on scope. **Do not let this be
> settled by assumption.** The low-risk reading, and my recommendation: the
> token-paste path is **pull-only**, and the webhook path stays app/OAuth-only.
> That resolves the card's open question in favour of option (b), for a stated
> technical reason rather than convenience — and it is also what the user asked
> for, since "flows in automatically" is the pull path.

## F4 — ⚠️ The tracking doc's proposed fix would build on dead scaffolding

`DEV-TRACKING.md:293-297` proposes "implement `IntercomConnector.fetch_new_items`
against the Conversations API". **That is the wrong seam, and following it would
produce a third dead-code instance.** Evidence:

- `ZendeskConnector.fetch_new_items` (`worker-service/src/tasks/integrations.py:180-190`)
  is **also** a `"not implemented"` stub returning `[]`.
- Zendesk's real, shipped incremental pull is a **separate module**,
  `worker-service/src/tasks/zendesk_sync.py`, which does not touch
  `BaseConnector` at all.
- `sync_all_integrations` (`tasks/integrations.py:17`) is nonetheless registered
  on the beat schedule (`celery_app.py:121`) and selects
  `type.in_(["intercom", "zendesk"])` (`tasks/integrations.py:30`) — so a
  scheduled job runs and calls two stubs. The whole `BaseConnector` layer is dead
  scaffolding from "Month 2".

**Recommendation:** build `intercom_sync.py` mirroring `zendesk_sync.py`, and
delete (or explicitly neutralize) the dead `BaseConnector` layer rather than
extending it. Deleting it is in scope precisely because leaving it invites the
next person to make this same mistake.

`zendesk_sync.py:1-57` is an unusually complete template and its documented
decisions should be inherited deliberately:
- cursor = `last_synced_at` falling back to `connected_at`, **never epoch/None**,
  so a missing cursor can never trigger a historical backfill (D1);
- route every fetched item through the **shared** core
  (`_find_matching_sources` + `_process_event_for_source`) rather than creating
  `FeedbackItem`s ad hoc — this is what makes pull and webhook share one dedup
  path (D2, and the card's explicit guardrail);
- synthesize a uniform `*.created` event and let `FeedbackSourceEvent` dedup
  enforce "one item per conversation, ever", instead of guessing new-vs-updated (D3);
- a static auth failure is operator-recoverable: record `last_sync_status` /
  `last_error` **without** flipping `is_active` (D7).

A new `worker-service/src/clients/intercom.py` is needed — `src/clients/` holds
`zendesk/jira/asana/hubspot/salesforce` and no Intercom client.

## F5 — Intercom feedback does not reach Customer 360 (scope question)

`docs/SELF_HOSTING.md:1589-1592`: Intercom items **do not populate
`customer_email`** — it appears only in `source_metadata`, and only when field
mapping enables enrichment. Zendesk populates it by side-loading `users` and
merging a flat `requester_email` client-side before the item reaches the shared
core (`zendesk_sync.py:22-34`).

So Intercom feedback today cannot feed health scores, churn, or Customer 360.
Ingesting items that are invisible to the product's main value loop is a thin
win; the pull path should side-load contacts the same way Zendesk does. **This
is a scope decision for the PRD, not a given.**

## F6 — RBAC: the precedent is clear, the gap is elsewhere

`zendesk_integration.py:367,509,529` all carry
`dependencies=[Depends(require_admin_or_owner)]`. Any new Intercom token-paste
route must too. `DEV-TRACKING.md:422`'s claim is about the OAuth module
(`integrations.py`) specifically, and fixing that module wholesale is a
**separate card** — but a new route here must not inherit its omission.

## F7 — Frontend: two competing patterns, pick the shipped one

- Intercom connect lives in a **shared wizard**,
  `frontend-web/app/(dashboard)/settings/integrations/new/page.tsx` — a
  `slack | intercom | discord` type union (`:37`) with a `connectionMethod`
  concept already present (`:263` sets `'oauth'`), calling
  `integrationsAPI.getIntercomOAuthUrl` (`:116`) and surfacing
  `"Failed to start Intercom OAuth"` (`:119`) on the 403.
- The token-paste providers instead have **dedicated pages** with their own test
  files: `settings/integrations/zendesk/page.tsx` (+ `__tests__/ZendeskPage.test.tsx`),
  and the same for `jira/` and `asana/`.

**Recommendation:** a dedicated `settings/integrations/intercom/page.tsx`
following the Zendesk page, because that is the pattern with a shipped testing
precedent. Leave the OAuth wizard entry intact for operators who use it.

## F8 — Docs and copy are currently honest; keep them that way

- `SELF_HOSTING.md:1581-1596` states plainly: webhook-only, no periodic pull,
  daily sync is a no-op, no write-back, no token-paste path.
  `SELF_HOSTING.md:1674` carries the "does not currently produce feedback items"
  warning. `CHANGELOG.md:53-60` says the same. `INTERCOM_CLIENT_ID` is documented
  in `.env.example:22`, `.env.prod.example:115`, `SELF_HOSTING.md:1614`.
- **Every one of those statements becomes false when this lands** and must be
  updated in the same branch — that list is the docs checklist.

## F9 — Verified: the write-back module is still orphaned

`grep` across `services/backend-api/src` + `services/worker-service/src` for
`intercom_service` / `add_note_to_conversation` / `close_conversation` returns
**only the definitions** in
`services/backend-api/src/services/intercom_service.py:27,67`. Zero production
callers, confirming `DEV-TRACKING.md:433-446`. Out of scope here (it is
outbound, this card is inbound) — but it is the fourth "registered code that
never runs" instance and the P2 call stands: wire it or delete it.

---

## Ambiguities and open questions for the interview

1. **Webhook under token-paste** (F3) — pull-only, or a per-org secret? Needs an
   Intercom-docs check, not an assumption. My recommendation: pull-only.
2. **Customer email side-loading** (F5) — in scope, or a follow-up? Excluding it
   ships ingestion that cannot reach Customer 360.
3. **Delete the dead `BaseConnector` layer** (F4) — in this branch, or a separate
   cleanup? It currently runs on a schedule and does nothing for two providers.
4. **Backfill on connect.** Zendesk deliberately never backfills (cursor from
   `connected_at`). Same for Intercom, or an opt-in bounded backfill? Precedent
   says no backfill by default.
5. **One Intercom connection per org?** Zendesk enforces one row per org; the CRM
   integrations enforce one CRM per org. Presumably the same, worth stating.
6. **Does the OAuth path stay?** Both paths coexisting means two credential
   sources and two tenancy discriminators. Cheaper to support one — but removing
   OAuth is a breaking change for anyone using it.

## Contradictions found (code vs docs)

| Claim | Where | Reality |
|---|---|---|
| "implement `IntercomConnector.fetch_new_items`" is the fix | `DEV-TRACKING.md:293` | That abstraction is dead for **both** providers; Zendesk's real pull is `zendesk_sync.py` (F4) |
| Intercom polling is wired | `tasks/integrations.py:30` + `celery_app.py:121` | Beat runs daily and calls two stubs returning `[]` |
| `intercom_service.py` might now be wired | — | Still zero production callers (F9) |
| "2,500 feedback/mo · Slack & Intercom · Priority Support" | `frontend-web/app/signup/page.tsx:341` | Pre-pivot plan-tier copy; everything is unlocked (`CLAUDE.md` § Plans). Stale drift, **out of scope**, flagged |

## Affected surface (for decomposition)

| Service | Files |
|---|---|
| backend-api | `routes/source_webhooks.py` (envelope fix), a new `routes/intercom_integration.py` (token-paste connect/status/disconnect, modelled on `zendesk_integration.py`), a new `models/` row + migration, `tests/test_intercom.py` |
| worker-service | new `tasks/intercom_sync.py`, new `clients/intercom.py`, `tasks/source_events.py` (match branch), `adapters/intercom.py` (unchanged if the route is fixed), `tasks/integrations.py` (delete dead layer), `celery_app.py` (beat), `tests/test_intercom_adapter.py` + a new seam test |
| frontend-web | new `settings/integrations/intercom/page.tsx` + `__tests__`, the integrations API client, the tile registry |
| docs | `SELF_HOSTING.md` (§ Connecting Intercom, the known-limitation block at :1674, the env table at :1614), `CHANGELOG.md:53-60`, `README.md`, `AI-TRACKING.md` (new/updated Intercom row), `DEV-TRACKING.md:252,378,293` |
