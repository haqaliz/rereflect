# Card — `feat/intercom-selfhost-ingestion`

**Type:** feat (freeform — no GitHub issue)
**Branch:** `feat/intercom-selfhost-ingestion`
**Worktree:** `.claude/worktrees/feat-intercom-selfhost-ingestion`
**Opened:** 2026-07-30
**Source of the brief:** `rereflect-next` recommendation (2026-07-30), grounded in
`DEV-TRACKING.md` § *Post-1.0.0 User Feedback Backlog* — the queue that file names as
authoritative for `rereflect-next` (`DEV-TRACKING.md:36-41`).

---

## The ask, in the user's words

From the post-1.0.0 user feedback, batch 2 (recorded at `DEV-TRACKING.md:252-254`):

> "integrating directly with Intercom or Zendesk so feedback flows in automatically
> instead of pasting tickets manually. Would save a ton of time on weekly reviews."

Triaged 2026-07-29 as **P1**. The Zendesk half of the ask is fully real and shipped.
The Intercom half is the gap this card addresses.

## What is already done (do not redo)

**Part A — discoverability — LANDED** on `chore/intercom-zendesk-docs`:
- `README.md:38` now lists Intercom among the inbound sources (it previously omitted
  Zendesk, Intercom, Jira, Linear, Asana).
- `docs/SELF_HOSTING.md:1571` has a *Connecting Intercom* section, with the OAuth env
  vars documented and the webhook-driven nature stated plainly.
- The landing page's false "Two-Way Sync" claim was removed.

**The P0 security defect — FIXED** on `feat/integration-auth-tenancy-hardening`:
- `verify_intercom_signature` now **fails closed** when `INTERCOM_CLIENT_SECRET` is unset.
- The worker's source-matching now returns `[]` rather than falling through to every
  organization when the payload carries no `app_id`.
- This matters for ordering: `DEV-TRACKING.md:378-381` records that the envelope-shape
  fix below is **"Now safe to fix at any time — the tenancy guard removed the hazard
  that made ordering matter."**

## Part B — the gap (this card)

Three defects that compose into one integration a self-hoster cannot turn on.
**All three verified by direct code read on 2026-07-30, not inferred.**

### B1 — Intercom has never produced a feedback item, in any release

- `services/backend-api/src/api/routes/source_webhooks.py:333` queues
  `event_data=payload.get("data", {})` — the **unwrapped** `data` object.
- `services/worker-service/src/adapters/intercom.py:88-89` (`extract_content`) reads
  `event_data.get("topic", "")` and `event_data.get("data", {}).get("item", {})` — it
  expects the **full envelope**.
- Consequence: `topic` is always `""` and `item` is always `{}`, so `extract_content`
  returns empty text and no `FeedbackItem` is ever created. The same mismatch repeats at
  `intercom.py:73` (`_get_body_text`, keyword triggers), `intercom.py:148` (dedup key
  derivation) and `intercom.py:171` (the enrichment fetch).
- Tracked as the `intercom-envelope-shape` follow-up (`DEV-TRACKING.md:378-381`).
- Documented as a **known limitation** in `SELF_HOSTING.md` and the changelog until fixed.

### B2 — There is no pull path ("flows in automatically" is exactly what the user asked for)

- `services/worker-service/src/tasks/integrations.py:170-177` —
  `IntercomConnector.fetch_new_items` logs `"IntercomConnector.fetch_new_items called
  (not implemented)"`, returns `[]`, and carries a `TODO: Implement actual Intercom API
  integration in Month 2` comment.
- `services/worker-service/src/tasks/integrations.py:30` still selects
  `Integration.type.in_(["intercom", "zendesk"])` for polling, so the poller runs and
  does nothing for Intercom.
- So if the webhook is not wired, nothing arrives at all.

### B3 — Connect is OAuth-only, and Intercom is the last integration still requiring it

- `services/backend-api/src/api/routes/integrations.py:981-984` returns **403**
  `"Intercom OAuth is not configured. Set INTERCOM_CLIENT_ID environment variable"`.
- Every newer integration deliberately chose BYO-token over OAuth because OAuth was
  judged *"awkward for self-host"* — HubSpot (private-app token), Zendesk (agent email +
  API token), Jira (Atlassian API token), Asana (PAT). `DEV-TRACKING.md:293-297` names
  the follow-up: implement `fetch_new_items`, **or** add a token-paste connect path
  following that precedent. Intercom is the only holdout.

## Known caveat to resolve during the dig — the webhook secret cannot identify a tenant

From the 1.0.0 changelog (Unreleased § *Security*), stated during the tenancy fix:

> "A valid signature cannot identify a tenant here. `INTERCOM_CLIENT_SECRET` is a single
> global env var, unlike Zendesk's per-org `webhook_secret` which is looked up *by* the
> discriminator."

Compounding it: the verifier now **fails closed**, so on any install without that env var
the Intercom webhook path rejects every delivery outright. A token-paste connect has no
OAuth client secret at all.

**Therefore the dig must decide explicitly, not inherit:**
- (a) give the token-paste path its own **per-org `webhook_secret`** column, mirroring
  Zendesk (needs an Alembic migration), **or**
- (b) make this slice **pull-only** and leave the webhook path to the OAuth install.

Whichever is chosen must be stated in the PRD as a decision with its reason.

## Guardrails

- Open-source, self-hosted, BYOK. No hosted-SaaS assumption, no plan gate (see
  `CLAUDE.md` § *Plans & Feature Gating* — every feature is unlocked; `SELF_HOSTED`
  defaults to `true`).
- Reuse the shared dedup core that Zendesk's dual pull+webhook ingestion already uses —
  do not fork a second dedup path.
- Worker-service **cannot import backend-api**. Anything shared crosses that boundary by
  mirroring, and a bare `except` around a cross-process import is a defect on sight
  (`CLAUDE.md` § *Automations engine*).
- Do not restore any marketing claim (pull sync, two-way sync) ahead of the code that
  makes it true.

## Stale tracking markers noticed while triaging (not this card's work)

- `DEV-TRACKING.md:83` marks P0b `worker-resolution-time-scoring-dead` **NOT STARTED**,
  but it merged as `26818cf8` (`bug/worker-resolution-time-scoring`).
- `docs/planning/status-sync-realtime-mapping/` has a full PRD + aspect specs and
  `jira_webhook.py` / `asana_webhook.py` exist in the tree, yet the `AI-TRACKING.md`
  integration rows still list real-time inbound status-sync as deferred v2.
