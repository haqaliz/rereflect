# Understanding — ingestion source visibility (Phase 2)

**Slug:** `ingestion-source-visibility` · **Branch:** `chore/intercom-zendesk-docs`
**Date:** 2026-07-29 · Source card: `docs/planning/_card/card.md`

---

## What the task turned out to be

It was scoped as "fix the README source list and write the missing Intercom setup docs."

The deep dig confirms the docs gap is real, but it is a **symptom**. The actual finding is
that **Rereflect's public-facing description of its own ingestion surface is wrong in four
different directions at once**, and that the Intercom integration is materially less
functional than every surface claims.

Nothing below is inferred. Every claim is cited to a file and line, verified 2026-07-29.

---

## Finding 1 — the landing FAQ tells prospects Zendesk does not exist

`services/landing-web/components/landing/FAQ.tsx:29`:

> "Slack (OAuth), Intercom (OAuth + webhooks), email forwarding, CSV import, webhooks for
> custom sources, and Linear. **Zendesk and HubSpot integrations are planned.**"

Zendesk shipped 2026-07-06 (M3.4), HubSpot before it. Jira, Asana and Salesforce are not
mentioned at all. The same file at line 49 correctly describes live HubSpot/Salesforce
churn-label behaviour — so the file **contradicts itself twenty lines apart**.

**This is the most likely direct cause of the user comment that opened this card.** A
prospect reads the FAQ, is told Zendesk is planned, and writes in asking for Zendesk.

## Finding 2 — README understates the ingestion surface

- `README.md:38` — "ingests customer feedback from CSV, email, webhooks and Slack"
- `README.md:61` — "CSV import, email, webhooks and Slack in; alerts and digests out"

Ground truth, `feedback_sources.py::list_source_types` (lines 157–221): `slack`, `intercom`,
`webhook`, `linear`, `jira`, `zendesk`, `asana`, `email` are all `available=True`. Only
`discord` is `available=False` ("coming soon"). Both README lines omit **five** shipped
inbound sources: Intercom, Linear, Jira, Zendesk, Asana. Neither mentions the outbound
work-item targets or the CRM pair.

## Finding 3 — the telemetry table is incomplete, which is a credibility problem

`docs/SELF_HOSTING.md:99` enumerates every outbound call a Rereflect instance makes:

> `| Integrations (Slack, Jira, Zendesk, Asana, HubSpot, Salesforce) | Only for integrations you explicitly connect and authorize. |`

It omits **Intercom and Linear**, both of which make outbound API calls. "Zero telemetry,
and here is the complete list of calls we make" is the project's central privacy claim; an
incomplete list undermines it independently of discoverability.

## Finding 4 — Intercom is substantially less functional than every surface claims

| Claim, and where it is made | Reality |
|---|---|
| Landing page: **"Two-Way Sync"** — add notes back, close resolved tickets (`lib/integrations.ts:153`) | **Fully orphaned.** `intercom_service.py`'s `add_note_to_conversation` / `close_conversation` / `get_admin_id` have **no production caller anywhere in the repo** — `grep` across `services/` returns only `tests/test_intercom.py`. Nothing in `workflow.py`, the automation engines, or any route imports the module. The functions are unit-tested against mocked httpx, which is why the gap survived. |
| Landing page: **"Authorize via OAuth in one click"** (`lib/integrations.ts:147`) | Requires three undocumented env vars first; without them the connect route returns **500**. |
| Source type registered `available=True`; daily `sync-integrations-daily` beat at 02:00 UTC selects `type.in_(["intercom","zendesk"])` | **The Intercom branch is a total no-op.** `IntercomConnector.fetch_new_items` (`worker-service/src/tasks/integrations.py:167`) logs "not implemented" and returns `[]`. Zendesk has two real dedicated pollers (`zendesk_sync.py`, `zendesk_status_sync.py`); Intercom has none. **Webhooks are the only path by which Intercom data can ever enter the system.** |
| Implied parity with other sources | `FeedbackItem.customer_email` is **always NULL** for Intercom. `source_events.py:291` reads `content.get("customer_email")`, but no `IntercomAdapter.extract_content` branch ever sets a top-level `customer_email` — the email lands only in `source_metadata.author_email`, and only when `include_author`/`include_context` mapping is on. Only `adapters/zendesk.py:96` sets the top-level key. |

The user's words were "so feedback **flows in automatically**". For Intercom that is precisely
the path that does not exist.

## Finding 5 — four defects found in passing, all out of scope, none previously recorded

These are **not** docs problems. They are recorded here so they are not lost, and belong in
`DEV-TRACKING.md` rather than this branch.

1. **OAuth tokens stored in plaintext.** `Integration.oauth_access_token` is a plain `Text`
   column. `integrations.py` never calls `encrypt_api_key`/`decrypt_api_key` for the Slack or
   Intercom OAuth paths, while every newer BYOK integration (Zendesk, Jira, Asana, HubSpot,
   Salesforce) does. Worse, `models/integration.py:19` carries the comment *"OAuth tokens
   (encrypted at application level before storage)"* — **the comment is false**, which is how
   a reader would be misled into believing this is handled.
2. **Intercom webhook signature verification fails open.** `verify_intercom_signature`
   (`source_webhooks.py:268-270`) returns `True` unconditionally when `INTERCOM_CLIENT_SECRET`
   is unset, logging only a warning. Since that var is documented nowhere, **unset is the
   default state**, so `POST /api/v1/webhooks/intercom/events` accepts arbitrary unsigned
   payloads on a default install. Zendesk's equivalent deliberately fails **closed** and its
   docstring calls out the contrast — so the asymmetry is known and was not applied here.
3. **Latent cross-tenant match.** If an inbound payload lacks `app_id`, `workspace_id` is
   `None`, the `if workspace_id:` guard in `_find_matching_sources`
   (`source_events.py:142-161`) is skipped, and the query is left **unfiltered by
   integration** — matching every active Intercom source across **every organization** on the
   instance. `tests/test_intercom.py` already exercises the `workspace_id=None` case without
   asserting anything about this implication. Combined with (2), an unauthenticated caller
   could inject feedback into arbitrary orgs on a default install.
4. **No RBAC on the integrations routes.** `integrations.py` contains zero occurrences of
   `403` / `require_admin_or_owner` / `require_owner`. `get_current_org` checks only for a
   valid JWT. So a `member` can drive the OAuth connect flow via the API, contradicting
   CLAUDE.md's RBAC table ("Manage integrations: Owner/Admin ✅, Member ❌"). The frontend
   hides the UI; the backend does not enforce it.

Also noted, lower severity: `oauth_states` (`integrations.py:39`) is a module-level in-process
dict with no TTL and no Redis backing, so OAuth callbacks fail intermittently on any
multi-replica backend deployment — relevant to self-hosters running more than one API pod.

---

## What this means for scope

The original five scope items still hold, with two corrections and one addition:

- **Correction A.** The initial triage said the missing-client-id error was a 403. It is a
  **500** (`integrations.py:754`). Docs must not describe a permissions error.
- **Correction B.** The initial triage assumed documenting setup would make the landing
  page's "one click" claim true. It would not — **"Two-Way Sync" is separately false**, and
  no amount of setup documentation fixes an orphaned module. The landing copy needs an
  actual correction, not a softening.
- **Addition.** `FAQ.tsx:29` was not in the original scope and is the highest-value single
  line in the whole task.

**No OAuth scopes may be documented.** The authorize URL (`integrations.py:772-778`) sends
only `client_id`, `state`, `redirect_uri` — **no `scope` parameter at all**. Intercom apps
declare permissions in the Developer Hub, not per-request. Any scope string in the docs would
be invented.

**Mandatory order of operations** for the setup docs (each step 400s/500s if skipped):
1. Register an Intercom app; note Client ID + Secret; register the redirect URI.
2. Set `INTERCOM_CLIENT_ID`, `INTERCOM_CLIENT_SECRET`, `INTERCOM_REDIRECT_URI`, `FRONTEND_URL`; restart backend.
3. Complete OAuth → creates the `Integration` row with `config.workspace_id`.
4. **Only then** create the feedback source with `source_type=intercom` + `integration_id`
   (400 "Intercom sources require an integration_id" otherwise).
5. Subscribe the Intercom app's webhook to `conversation.user.created`,
   `conversation.user.replied`, `conversation.rating.added` → `POST {backend}/api/v1/webhooks/intercom/events`.

## Documentation pattern to follow

`docs/SELF_HOSTING.md` "Connecting Salesforce" (lines 978–1061) is the only existing
env-var OAuth section and is the closest precedent — copy its `### 2. Configure environment
variables` table shape and its "Restart the backend…" line, plus its cross-origin blockquote
callout (line 1027), which applies verbatim to Intercom. Wrap that in Zendesk's overall
section shape (numbered steps → `### Verify` → `### All features unlocked`).

Placement: new `## Connecting Intercom` between Zendesk (ends 1498) and Asana (1499); TOC
entry between lines 23 and 24; add Intercom to the telemetry table at line 99.

House style: `| Variable | Purpose |` tables, blockquote callouts with a **bold lead-in**, no
emoji, no GitHub alert syntax, second person, and an explicit honesty register
("Known limitation", "Shipped scope for this release").

## Open questions for the review gate

1. **Scope of the security findings.** Document-only (a "Known limitation" callout), or
   split into `DEV-TRACKING.md` items? The fail-open webhook plus the cross-tenant match
   compose into an unauthenticated cross-org write on a default install — writing that into
   public docs without a fix is publishing an exploit.
2. **The "Two-Way Sync" landing claim.** Delete it, or mark it as not-yet-wired?
3. **Does `.env.example`** (minimal local-dev) get the vars, or only `.env.prod.example`?
4. **`app/page.tsx:408` "6+ integrations"** — undercounts (9 available). In or out?
5. **`signup/page.tsx:341`** stale Stripe-tier copy ("2,500 feedback/mo · Slack & Intercom")
   behind the dead `?promo=EARLYPRO3` gate. Separate cleanup, or fold in?
