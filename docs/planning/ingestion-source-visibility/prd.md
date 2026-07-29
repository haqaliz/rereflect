# PRD — Ingestion source visibility

**Slug:** `ingestion-source-visibility` · **Branch:** `chore/intercom-zendesk-docs`
**Type:** chore (docs + marketing copy) · **Date:** 2026-07-29
**Traces to:** DEV-TRACKING P1, *Post-1.0.0 User Feedback Backlog*
**Inputs:** `docs/planning/_card/card.md`, `docs/planning/ingestion-source-visibility/understanding.md`

---

## 1. Problem

A post-1.0.0 user asked for "Intercom or Zendesk so feedback flows in automatically instead
of pasting tickets manually." Zendesk shipped 2026-07-06 and fully satisfies the ask.
Intercom is registered, marketed, and offered in the UI but is unreachable on a fresh
self-host.

The user did not find either. The dig established why: **every public surface that describes
Rereflect's ingestion is wrong**, and one of them tells prospects outright that Zendesk does
not exist yet.

## 2. Goals

- **G1.** No public surface understates or misstates which feedback sources ship.
- **G2.** A self-hoster can connect Intercom end-to-end using only committed documentation.
- **G3.** No public surface claims Intercom behaviour that does not happen.
- **G4.** The four security defects found in passing are recorded for a separate branch,
  without publishing an exploit path against unpatched instances.

## 3. Non-goals

- Implementing `IntercomConnector.fetch_new_items` (no pull path). → DEV-TRACKING P1 Part B.
- Adding a token-paste (non-OAuth) Intercom connect path. → DEV-TRACKING P1 Part B.
- Wiring `intercom_service.py` write-back into any status-change path. → new DEV-TRACKING item.
- **Fixing** any of the four security defects. → new DEV-TRACKING items, separate branch.
- The stale Stripe-tier promo banner at `signup/page.tsx:341`. → separate cleanup.

**No application code changes.** Markdown, example env files, and marketing copy strings only.

## 4. Decisions (settled at the Phase 2 gate — do not re-litigate)

| # | Decision | Rationale |
|---|---|---|
| D1 | Security defects → `DEV-TRACKING.md` only. `SELF_HOSTING.md` documents `INTERCOM_CLIENT_SECRET` as **required**, with a strong callout, but **does not describe the bypass**. | Documenting an unauthenticated cross-org write while it is unfixed publishes a working exploit. Making operators set the var removes the practical risk. |
| D2 | **Remove** the "Two-Way Sync" claim from `lib/integrations.ts`. | It describes behaviour that cannot happen — the module has no caller. Not a roadmap signal; a false statement. |
| D3 | Both `.env.example` (commented out) and `.env.prod.example` get the three vars. | Matches how `.env.example` already handles `JWT_SECRET` / `DATABASE_URL`. |
| D4 | `FAQ.tsx:29` is in scope. | Not in the original ask, but it is the single highest-value line — the probable cause of the user comment. |
| D5 | Security items are recorded in the **primary checkout's** `DEV-TRACKING.md`, not this branch. | The P1 entry is already uncommitted there; splitting tracking edits across two trees would conflict on merge. |

## 5. Aspects

### Aspect A — `source-copy-accuracy`

Correct every surface that enumerates ingestion sources.

| File:line | Current | Required |
|---|---|---|
| `services/landing-web/components/landing/FAQ.tsx:29` | "…and Linear. **Zendesk and HubSpot integrations are planned.**" | Zendesk/HubSpot listed as shipped; add Jira, Asana, Salesforce. Must not contradict `FAQ.tsx:49`. |
| `README.md:38` | "CSV, email, webhooks and Slack" | Add Intercom, Linear, Jira, Zendesk, Asana. |
| `README.md:61` | "CSV import, email, webhooks and Slack in; alerts and digests out" | Split inbound sources from outbound work-item targets and the CRM pair. |
| `docs/SELF_HOSTING.md:99` | "Integrations (Slack, Jira, Zendesk, Asana, HubSpot, Salesforce)" | Add **Intercom** and **Linear** — both make outbound calls. |
| `services/landing-web/lib/integrations.ts:153` | "Two-Way Sync — add notes back… close resolved tickets" | **Delete** (D2). |
| `services/landing-web/lib/integrations.ts:147` | "Authorize via OAuth in one click" | Reflect that operator setup is required first. |
| `services/landing-web/app/page.tsx:408` | "6+ integrations" | 9 are available. Low stakes; correct while adjacent. |

**Ground truth** — `feedback_sources.py::list_source_types` (157–221): `slack`, `intercom`,
`webhook`, `linear`, `jira`, `zendesk`, `asana`, `email` are `available=True`; `discord` is
`available=False`. Outbound/CRM: Jira, Linear, Asana, HubSpot, Salesforce.

**Acceptance:** every row above updated; no surface names a shipped integration as planned;
`discord` still the only "coming soon"; `pnpm lint` clean in `landing-web` and `frontend-web`.

### Aspect B — `intercom-setup-docs`

New `## Connecting Intercom` in `docs/SELF_HOSTING.md`, inserted between Zendesk (ends 1498)
and Asana (1499), with a TOC entry between lines 23 and 24.

Structure — Salesforce (978–1061) for the env-var half, Zendesk's shape for the rest:

1. **Intro** — Intercom is inbound. **"Shipped scope for this release"** bullets stating
   plainly: webhook-only, **no periodic pull unlike Zendesk**; three handled topics;
   `customer_email` not populated at top level; no write-back.
2. `### 1. Create an Intercom app` — Developer Hub; note Client ID/Secret; register the
   redirect URI. **No OAuth scopes may be named** — the authorize URL sends only
   `client_id`, `state`, `redirect_uri` (`integrations.py:772-778`). Say permissions are
   declared on the app in the Developer Hub.
3. `### 2. Configure environment variables` — `| Variable | Purpose |` table:
   `INTERCOM_CLIENT_ID`, `INTERCOM_CLIENT_SECRET` (note: **also** the webhook HMAC secret —
   required, not optional), `INTERCOM_REDIRECT_URI` (**default is `http://localhost:8000/...`
   and must be overridden**), `FRONTEND_URL`. Close with the "Restart the backend…" line.
4. `### 3. Connect from the app` — Settings → Integrations → New → Intercom. State that
   the connect route returns **500** if `INTERCOM_CLIENT_ID` is unset (not a permissions error).
5. `### 4. Create the Intercom feedback source` — **must follow step 3**; requires
   `integration_id`, else 400 "Intercom sources require an integration_id".
6. `### 5. Subscribe the webhook` — `POST <your-api-base>/api/v1/webhooks/intercom/events`;
   topics `conversation.user.created`, `conversation.user.replied`,
   `conversation.rating.added`; `X-Hub-Signature`, HMAC-SHA1.
7. `### Verify`
8. Cross-origin blockquote callout, copied from Salesforce (1027).
9. `### All features unlocked` boilerplate.

Plus `.env.example` (commented) and `.env.prod.example` (D3).

**Acceptance:** a reader following the section top-to-bottom connects Intercom with no
source-diving; every env var, endpoint, topic and error code matches the traced code;
`INTERCOM_CLIENT_SECRET` is stated as required with a strong callout; **no scope strings**;
**no description of the fail-open** (D1); webhook-only limitation stated in the intro.

### Aspect C — `security-findings-recorded`

Four new `DEV-TRACKING.md` entries in the **primary checkout** (D5), each with file:line
evidence and a suggested priority:

1. **P0** — Intercom webhook fails open (`source_webhooks.py:268-270`) **+** cross-tenant
   match on missing `app_id` (`source_events.py:142-161`). Composed: unauthenticated
   cross-org feedback injection on a default install. Fix both together.
2. **P1** — OAuth tokens stored plaintext (`integrations.py`, Slack + Intercom paths);
   `models/integration.py:19` comment falsely claims encryption. Delete or fix the comment
   *and* migrate to `encrypt_api_key`.
3. **P1** — No RBAC on `integrations.py` (zero `403`/`require_admin_or_owner`); a `member`
   can drive OAuth connect, contradicting CLAUDE.md's RBAC table.
4. **P2** — `intercom_service.py` write-back fully orphaned; wire it or delete it.
   Note the detection lesson: it was unit-tested against mocks, which masked having no caller.
5. **P3** — `oauth_states` is an in-process dict with no TTL (`integrations.py:39`); OAuth
   breaks on multi-replica backends.

**Acceptance:** all five recorded with evidence; none fixed on this branch.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Docs describe an unfixed hole | D1 — record, don't publish |
| Inventing OAuth scopes | Explicitly forbidden; code sends none |
| Over-correcting copy into a new overclaim | Every claim checked against `list_source_types` |
| Tracking edits conflict across two trees | D5 — all in primary |

## 7. Self-critique

🔴 **The user's actual ask is only half-satisfiable, and this PRD does not fix that.** They
want Intercom feedback to "flow in automatically". After all of this, Intercom still requires
a webhook and still has no pull. This work makes the product *honest*, not *capable*. If the
goal is to satisfy that user, Part B (the connector) is the real work and this is a
prerequisite. **Stated so nobody mistakes shipping this for closing the request.**

🔴 **Aspect C is bookkeeping for defects this branch deliberately leaves live.** The
composed vulnerability stays exploitable on default installs until a separate branch lands.
D1 is the right call for a *docs* PR, but the security fix should be scheduled immediately
after, not queued behind feature work. Recommend it as the next task.

🟡 **`README.md:61` risks becoming a wall of nouns.** Nine integrations plus five sources in
a table cell. Prefer grouping ("support desks", "issue trackers", "CRMs") over enumeration.

🟡 **No automated test prevents this drift recurring.** `list_source_types` is the ground
truth and nothing asserts the docs agree with it. A test that fails when a new
`available=True` type is absent from README/FAQ would prevent a third round. Out of scope,
worth recording.

🟡 **"9 integrations" is itself ambiguous** — `lib/integrations.ts` has 9 slugs but omits
`webhook`, while `list_source_types` has 9 types including `webhook` and `discord`. The two
counts coincide by accident. Avoid a bare number; enumerate.

## 8. Out of scope, recorded

- Intercom pull connector; token-paste connect path (P1 Part B).
- All four security fixes (Aspect C).
- `signup/page.tsx:341` stale Stripe-tier promo copy.
- A drift test asserting docs match `list_source_types`.
