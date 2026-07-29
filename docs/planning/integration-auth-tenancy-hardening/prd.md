# PRD — Integration auth & tenancy hardening

**Slug:** `integration-auth-tenancy-hardening`
**Branch:** `feat/integration-auth-tenancy-hardening`
**Date:** 2026-07-29
**Source brief:** `docs/planning/_card/card.md`
**Status:** awaiting review gate

> ⚠️ **Embargo.** Do not publish a public write-up of the webhook defects until this merges.
> `chore/intercom-zendesk-docs` deliberately omitted them from `docs/SELF_HOSTING.md` to avoid
> publishing a working exploit. Operator-facing docs in this branch may say *"set
> `INTERCOM_CLIENT_SECRET`, here is how"* without narrating what happens if you don't.

---

## Problem Statement

Rereflect's inbound webhook path for **Intercom** and **Slack** accepts unauthenticated requests
on a default install and, on certain payloads, writes rows attributed to organizations the caller
has no relationship with.

Two independent defects per provider, each verified in code on `master` @ `09efba08`:

1. **The signature check fails open.** `verify_intercom_signature`
   (`backend-api/src/api/routes/source_webhooks.py:256-273`) and `verify_slack_signature`
   (`:40-56`) both `return True` when their secret is empty. Neither `INTERCOM_CLIENT_SECRET` nor
   `SLACK_SIGNING_SECRET` is set by any `.env.example`, `.env.prod.example`, or docker-compose
   file, so **unset is the default state of every install.**

2. **A missing discriminator unscopes the organization filter.**
   `worker-service/src/tasks/source_events.py::_find_matching_sources` guards its Intercom
   (`:142-161`) and Slack (`:118-139`) branches behind `if workspace_id:` / `if team_id:` with no
   `else: return []`. The base query (`:112-115`) carries **no `organization_id` predicate at
   all**. A payload omitting the discriminator therefore falls through to `return query.all()` —
   every active source of that type, in every organization on the instance.

Tenancy is decided entirely by that function's return value: `_process_event_for_source`
(`:216-217`, `:284-292`) copies `source.organization_id` straight onto the created rows, with **no
later org check anywhere**.

### Why the signature fix alone is insufficient

`INTERCOM_CLIENT_SECRET` is a **single global env var** (`source_webhooks.py:32`) — the OAuth
client secret for one Intercom app that every organization connects through. A valid HMAC proves
only *"signed by whoever holds this instance's client secret."* It identifies neither a workspace
nor an organization.

Contrast Zendesk, the one provider implemented correctly: `webhook_secret` is **per-org** on the
`ZendeskIntegration` row and is looked up *by* the tenant discriminator before verification —
authentication and tenant resolution are the same operation.

**Therefore authentication and tenancy are independent controls here and both are load-bearing.**
No per-org secret is available for Intercom or Slack today: the `integrations` table has no
webhook-secret column, and both webhook URLs are fixed paths with no per-tenant component.
(Contrast the generic `/inbound/{webhook_id}` route, which has *both* a capability URL and a
per-source `secret_token`.) Adding one is a schema change and is out of scope.

### Evidence and honest severity

**Reachability is real.** On a default install an unauthenticated POST to
`/api/v1/webhooks/intercom/events` is accepted, queued, and processed against every org's
Intercom sources.

**But `DEV-TRACKING.md`'s framing — "inject feedback into arbitrary organizations" — overstates
what lands today, and the reason matters.** A separate payload-shape bug blocks it: the route
queues the *unwrapped* `payload["data"]` (`source_webhooks.py:319`) while `IntercomAdapter`
expects the *full envelope*, re-deriving `data.item` and a top-level `topic`
(`worker-service/src/adapters/intercom.py:70,82-83,145-146`). `extract_content` therefore always
returns `text=""` and `_process_event_for_source` bails with `status="ignored"` / `empty_text`.
Verified empirically by running the adapter against exactly what the route queues.

What actually lands per foreign org today is a **`FeedbackSourceEvent` log row** carrying
attacker-controlled `event_data` JSON under another organization's `organization_id`. A silent
cross-tenant write — but a log row, not a feedback item.

> **This is an accident, not a control.** The shape bug is the *only* thing preventing full
> feedback injection. See *Sequencing constraint* below.

**Side effect:** the same shape bug means **Intercom ingestion has never worked in any release.**
`docs/SELF_HOSTING.md` claims conversations appear as feedback "within a minute or two"; they do
not. This is consistent with `IntercomConnector.fetch_new_items` being an unimplemented
placeholder — neither the pull path nor the webhook path produces feedback.

### Secondary problem — RBAC

`backend-api/src/api/routes/integrations.py` (Slack/Discord/Intercom, 14 endpoints) contains
**zero** occurrences of `require_admin_or_owner`, `require_owner` or `403`. `get_current_org`
validates the JWT but never inspects `current_user.role`. A **`member` can drive the OAuth connect
flow via the API**, contradicting the RBAC matrix in `CLAUDE.md`. Six sibling modules (Jira,
Asana, Zendesk, HubSpot, Salesforce) gate every endpoint including read-only GETs.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| No unauthenticated write reaches any org's data | Route returns `401` for unsigned/invalid Intercom requests; regression test asserts `queue_source_event` not called |
| A payload without a tenant discriminator writes nothing, anywhere | `_find_matching_sources(db, "intercom", {})` returns `[]` with ≥2 orgs seeded; same for `"slack"` |
| No live Slack ingestion is broken without warning | Shadow release logs every would-be rejection; affected operators see an unconfigured-signature flag in Settings → Integrations |
| Integration management is role-enforced server-side | `member` receives `403` on all 12 gated `integrations.py` endpoints |
| OAuth callbacks keep working | Explicit tests assert `/slack/oauth/callback` and `/intercom/oauth/callback` remain reachable with **no** `Authorization` header |
| No regression | Backend 4562 → ≥4562 passing; worker 1417 → ≥1417 passing (baselines measured on this branch) |

**Non-metric:** this PRD makes **no claim** that Intercom ingestion works after this branch. It
does not. That is the follow-up.

---

## Users & Scenarios

- **Self-hosting operator (primary).** Runs a single- or multi-org instance. Has not set
  `INTERCOM_CLIENT_SECRET`/`SLACK_SIGNING_SECRET` because nothing ever told them to. Needs the
  hole closed without their working Slack ingestion silently dying.
- **Multi-org instance operator.** Runs several organizations on one deployment — an agency, or a
  company with separate business units. Cross-tenant isolation is the guarantee they cannot
  compromise on, and the one they cannot verify themselves.
- **Member-role user.** Should not be able to connect or disconnect integrations. Today they can,
  via the API.
- **Security auditor / evaluator.** Reads `models/integration.py` and is told OAuth tokens are
  encrypted. They are not.

---

## Requirements

### Must-have

**M1 — Intercom signature fails closed.** `verify_intercom_signature` returns `False` on an empty
or `None` secret, mirroring `_verify_zendesk_signature` (`:383-403`). Unsigned/invalid → `401`,
no queue. **No shadow period** — Intercom ingestion has never worked, so there is no live traffic
to break.

**M2 — Intercom tenancy guard.** A falsy `workspace_id` returns `[]` immediately. Must treat `""`
as falsy, not only `None`: the OAuth callback stores `workspace_id` with a `""` default
(`integrations.py:1051`) when `/me` lacks `app.id_code`.

**M3 — Slack tenancy guard.** Identical `else: return []` for a falsy `team_id`. **Applied
immediately, not shadowed** — a missing `team_id` is never legitimate traffic.

**M4 — Slack signature shadow mode.** `verify_slack_signature` keeps accepting when
`SLACK_SIGNING_SECRET` is unset, but logs a distinct, greppable warning per request recording
that it *would* be rejected. A follow-up release flips it to fail closed. Rationale: Slack
ingestion demonstrably works today; a hard flip stops real traffic.

**M5 — Operator visibility for M4.** An operator must discover they are running unsigned
somewhere they actually look:
- a warning log per shadow-rejection, plus a startup warning when `SLACK_SIGNING_SECRET` is unset
  while an active Slack integration exists; **and**
- a flag on the Slack integration in **Settings → Integrations** stating signature verification is
  unconfigured, with a pointer to the docs.

This requires a field on the integration status response and a small frontend change. *This is the
one piece of frontend work in an otherwise backend-only branch — it is deliberate, and it is what
makes the shadow period honest rather than silent.*

**M6 — RBAC on `integrations.py`.** Apply `dependencies=[Depends(require_admin_or_owner)]` to all
endpoints **except** `GET /slack/oauth/callback` and `GET /intercom/oauth/callback`. Follow the
decorator style used by all six correctly-gated sibling modules.

**M7 — OAuth callbacks stay reachable.** Explicit regression tests asserting both callbacks work
with no `Authorization` header. Their identity comes from the validated `state` param.

**M8 — Rewrite the test that pins the vulnerability.**
`test_intercom.py:294-325::test_webhook_processes_conversation_created` bakes
`provider_context={"conversation_id": "conv_100", "workspace_id": None}` into
`assert_called_once_with` as the *expected* contract, with `app_id` deliberately absent from the
payload. It must be **rewritten**, not extended. **Not one payload fixture in the repo contains
`app_id`** — several will need it added.

**M9 — Correct the false comment.** `models/integration.py:19` claims *"OAuth tokens (encrypted at
application level before storage)"*. This is false — `integrations.py` never calls
`encrypt_api_key`/`decrypt_api_key` on the Slack or Intercom OAuth paths. The code fix needs a
backfill migration and is out of scope; `DEV-TRACKING.md` requires the comment be corrected
either way.

**M10 — Document the env vars.** `INTERCOM_CLIENT_SECRET` and `SLACK_SIGNING_SECRET` in
`.env.example`, `.env.prod.example`, and `docs/SELF_HOSTING.md`, framed as setup instructions
(see embargo note).

### Should-have

**S1 — `hmac.compare_digest` TypeError.** A non-ASCII signature header raises `TypeError` → **500,
not 401**. Same lines being edited; handle it.

**S2 — Intercom replay window.** Slack's verifier has a 300-second timestamp window
(`source_webhooks.py:52-56`); **Intercom's has none**, so a captured valid payload replays
indefinitely. Add one if Intercom's delivery headers support it — *verify before committing to
this; do not invent a header that does not exist.*

**S3 — Tampered-body test.** Intercom's `test_webhook_rejects_invalid_signature` only sends the
literal `"sha1=badsignature"`. Mirror Zendesk's `test_webhook_rejects_tampered_body` (sign payload
A, send payload B).

### Nice-to-have

**N1 — Guard `email`/`webhook` branches.** Both fall through unscoped on a missing `source_id`,
but their `source_id` is resolved **by the caller** from a trusted server-side lookup rather than
an attacker payload, so they are not currently exploitable. Adding the guard is defence in depth.

---

## Technical Considerations

### Services changed

| Service | Change |
|---|---|
| `backend-api` | `source_webhooks.py` (both verifiers), `integrations.py` (RBAC + status field), `models/integration.py` (comment), tests |
| `worker-service` | `source_events.py` (two tenancy guards), tests |
| `frontend-web` | Slack unconfigured-signature flag in Settings → Integrations (M5) |
| — | No database migration. No schema change. |

### Sequencing constraint (the most important finding in the dig)

> `FeedbackItem` injection is blocked **only** by the payload-shape bug, not by any security
> control. **Fixing the envelope shape before the tenancy guard would upgrade this defect to full
> arbitrary-feedback injection.** M1–M3 must land before any adapter/envelope work.

Once M2/M3 land, that hazard is gone permanently and the envelope fix becomes safe at any time.

### Blast radius of `_find_matching_sources`

Shared infrastructure with two callers: `process_source_event` (all five source types — Intercom,
Slack, generic webhook, and the Resend inbound-email route) and `zendesk_sync.py:176` (scheduled
pull, subdomain read from a trusted column, never payload-derived). Changes must not disturb
either.

### Existing correct patterns to follow

- **Fail-closed verifier:** `_verify_zendesk_signature` (`source_webhooks.py:383-403`).
- **Tenancy guard:** the Zendesk branch (`source_events.py:180-193`) — note it scopes by
  `FeedbackSource.organization_id` directly, where Intercom/Slack scope indirectly via
  `integration_id`.
- **Tenancy regression test:** `worker-service/tests/test_zendesk_adapter.py:462-477`
  `test_missing_subdomain_returns_empty_not_cross_tenant_fanout` — seeds two orgs, asserts `[]`.
  Direct template; needs Intercom and Slack twins.
- **Fail-closed route + unit tests:** `test_zendesk_webhook.py:409-430` and `:250-268`.
- **Cross-org fixtures:** `test_anomalies_auth.py:16-79` — the **only** two-tenant isolation suite
  in the backend today.
- **RBAC tests:** `test_jira_connection.py:547-566` `TestRBAC`, `member_headers` → 403.

### Test-harness notes

- Backend and worker are **separate pytest runs with separate venvs** (both Python 3.12.13 in this
  worktree). In-memory SQLite, function-scoped `db` fixture, fresh schema per test.
- There is **no shared org/user factory fixture** — files define local `org_a`/`org_b` fixtures.
  Follow that pattern.
- **There is no `test_source_events.py`.** Every existing test of `_find_matching_sources` passes
  `source_type="zendesk"`; the intercom, slack, email and webhook branches have **zero** coverage.
  This branch should create that file.
- Missing `Authorization` header yields **403** from FastAPI's `HTTPBearer`, not 401 — baseline
  behaviour, not a bug. Assertions must expect it.

### Multi-tenancy

The entire point. Every new test must seed **two** organizations and assert the second is
untouched — a single-org test cannot detect this defect class.

---

## Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| Fail-closed silently kills a working ingestion path | **High** for Slack, **nil** for Intercom (never worked) | Shadow mode + M5 operator visibility; Intercom flips immediately |
| Operator never notices the shadow warning | Medium | M5 puts it in the UI, not only logs |
| Envelope fix later reintroduces the hazard | Medium | Neutralised once M2/M3 land; documented in the follow-up item |
| Orgs with `workspace_id == ""` stored | Low | They never matched before either — no regression, but M2 must treat `""` as falsy |
| Blanket RBAC breaks a member flow | **Nil** for `integrations.py` — settings page redirects non-admins before fetching | Verified in the dig; Linear (which *does* have member consumers) is explicitly excluded |
| S2 invents a replay header Intercom doesn't send | Low | Verify against Intercom's actual delivery headers before implementing; drop S2 if unsupported |

### Open questions

1. **Unresolved:** does Intercom send a timestamp header suitable for a replay window (S2)? Needs
   checking against Intercom's webhook docs, not guessed.
2. **Unresolved:** how long is the Slack shadow period — one release, or gated on a specific
   version? Needs a stated policy so the flip actually happens rather than becoming permanent.
3. **Partially answered:** a fourth dig agent (broad sweep of all JWT-less endpoints) had not
   reported at time of writing. The Intercom/Slack/Zendesk/email/webhook family is fully mapped;
   endpoints *outside* that family (share links, invite acceptance, password reset, public API
   key routes) are **not** confirmed clean. Not a blocker for this branch, but should not be
   assumed safe.

### 🔴 Gaps found by the self-critique pass (added after drafting)

**G1 — There is no disclosure or release plan, and for self-hosted OSS the rollout *is* the fix.**
A merged patch protects nobody until operators upgrade. Unaddressed: does this warrant a security
advisory (GitHub Security Advisory / CVE) once merged? What release does it ship in? How does an
operator running an older tag learn they need to move? The embargo section says what *not* to
publish before merge and is silent on what *must* be published after. **This is the largest gap in
the PRD** — every other requirement is verifiable by a test; this one is not, and it determines
whether the fix reaches anyone.

**G2 — No position on existing contamination.** A security fix normally asks "were we already
exploited, and what do we do about the data?" Cross-tenant `FeedbackSourceEvent` rows may already
exist on multi-org instances — written silently, since `last_event_at`/`events_processed` are not
touched on that path. Open: is a detection query offered to operators? A cleanup script? Or is the
documented position "we cannot distinguish malicious from benign, so we leave them"? Any of the
three is defensible; saying nothing is not.

**G3 — The severity rests on an unvalidated assumption: that real installs are multi-org.** A
single-org self-host has no tenant to cross — the defect degrades to "an unauthenticated party can
write log rows into the only org that exists," which is still real but is not a P0 cross-tenant
breach. Nothing in the repo establishes how many installs run multiple organizations. This does not
change whether we fix it (we should), but it does change how it is *described* — and the honest
framing rules in this project mean the advisory in G1 must not overstate it.

### 🟡 Weaker points, non-blocking

- **Success metrics are mostly binary test-passes, not outcomes.** Notably M5 has no measure of
  whether operators actually *notice* the shadow warning and set the secret — which is the entire
  point of M5. No time-bound on any metric.
- **No effort estimate** anywhere, and no rollback plan if the fail-closed flip causes an
  unforeseen break.
- **In-flight Celery tasks during deploy** are unaddressed. Assessed as safe — a task queued
  pre-fix with `workspace_id=None` that runs post-fix returns `[]`, which is the desired outcome —
  but this should be stated rather than left to inference.

### Resolved during discovery

- ~~Is `app_id` present on legitimate Intercom events?~~ **Yes** — the notification envelope
  carries it at top level for all topics, including the three handled ones. Returning `[]` on a
  missing `app_id` will not drop real traffic.
- ~~Does the fail-open pattern exist elsewhere?~~ **Yes — Slack**, identically. Zendesk is the only
  correct implementation.
- ~~Fail closed unconditionally, or offer an escape hatch?~~ **Unconditionally**, matching the
  Zendesk precedent. An operator behind a trusted boundary sets the secret.
- ~~`401` or `202`-and-drop?~~ **`401`**, matching Zendesk.

---

---

## ⚠️ ADDENDUM — full unauthenticated-surface sweep (arrived after drafting)

The fourth dig agent reported after this PRD was written. **The surface is not clean, and the
scope above is too narrow.** Every claim below was independently re-verified against the code
before being recorded here.

### A1 — `POST /api/internal/events/emit` is worse than the Intercom chain — [CRITICAL]

`services/backend-api/src/api/routes/events_ws.py:52,157,160-165`

```python
INTERNAL_SECRET = os.getenv("INTERNAL_EVENTS_SECRET", "dev-secret")   # :52
...
if x_internal_secret != INTERNAL_SECRET:                              # :157  plain !=
    raise HTTPException(status_code=403, ...)
await emit_event(org_id=request.org_id, ...)                          # :160  org_id from BODY
```

Three compounding defects: a **hardcoded default secret that is public knowledge** (this is an
open-source repo), a **non-constant-time comparison**, and **`org_id` taken verbatim from the
request body**. Nothing enforces or logs the absence of `INTERNAL_EVENTS_SECRET`.

**Why this outranks the Intercom chain:** it requires **no integration to be configured at all**.
Intercom needs an org to have connected Intercom; this needs nothing. The effect is arbitrary
attacker-controlled content pushed to every WebSocket client of any named org — forged
notifications, and a stored-XSS delivery path wherever the frontend renders event `data`
unescaped. Fix is a two-line change: no default (refuse to start or hard-fail when unset) plus
`hmac.compare_digest`.

### A2 — The Resend inbound-email webhook fails open *and* resolves org from the payload — [HIGH]

`email_webhooks.py:45-47` (fail-open, verified) and `:175-190` (loads **every** `source_type ==
"email"` row across all orgs — `is_active` not even in the SQL — then matches the attacker-supplied
`to` address in Python). Knowing or guessing a tenant's inbound address is sufficient to inject
feedback into it. Rate limiting at `:205` is keyed on the **resolved** org, so it throttles the
victim, not the attacker.

**Blocker:** `tests/test_email_webhooks.py:367-378` `test_missing_secret_skips_verification`
**asserts the fail-open behaviour** — docstring *"Should skip verification and continue when
webhook secret is not configured"*, `assert result is True`. Verified verbatim. This is the second
test in the repo that pins a vulnerability as the expected contract (the first being M8). It must
be **inverted**, not worked around.

### A3 — The tenancy guard is needed on FOUR branches, not two

| Branch | `source_events.py` | Guard? | Reachable today |
|---|---|---|---|
| slack | `:118-139` | **missing** | latent — handler pre-checks `team_id` at `source_webhooks.py:140-142` |
| intercom | `:142-161` | **missing** | **YES** |
| email | `:164-167` | **missing** | latent — handler always sets `source_id` |
| webhook | `:170-173` | **missing** | latent — handler always sets `source_id` |
| zendesk | `:179-193` | **present** | fixed |

The two "latent" ones are latent only because their current caller pre-checks. Each is one new call
site away from live. The Zendesk fix was applied as a **point fix, never swept** — the same drift
pattern this branch exists to correct.

### A4 — Other findings, ranked

- **[MEDIUM] Linear stores `webhook_secret` in plaintext** (`linear_integration.py:389,418,430`) —
  the only integration that doesn't encrypt it; Zendesk, Jira and Asana all round-trip through
  `encrypt_api_key`. Any DB read yields a working forgery key. **Needs a migration.**
- **[MEDIUM] Linear's verifier has the same fail-open branch** (`linear_webhook.py:35-37`), defused
  only by the caller's `and` guard at `:53`. One new call site re-arms it. Note
  `jira_webhook.py:8-10` calls this pattern out by name as an anti-pattern it deliberately did not
  copy — so it was known.
- **[MEDIUM] No replay window on Zendesk, Jira, Asana, Linear or Intercom.** Slack is the only one
  with a real 300s window. Zendesk is one line away — it already *receives*
  `X-Zendesk-Webhook-Signature-Timestamp` and feeds it into the HMAC but never checks freshness.
  Content-dedup blocks duplicate *content* replay but **not** status-transition replay:
  `_handle_zendesk_status_change`, `reconcile_issue` and `reconcile_task` all run before any dedup
  check, so a captured "ticket closed" delivery can re-drive that transition indefinitely, undoing
  manual triage.
- **[MEDIUM] The generic webhook persists all request headers into the DB**
  (`source_webhooks.py:229-233`, `dict(request.headers)`) — including its own `X-Webhook-Secret`,
  plus any `Authorization`/`Cookie` a caller sends. Written to `FeedbackSourceEvent.event_data` in
  cleartext. Anyone with read access to that table can forge the webhook.
- **[LOW] `JWT_SECRET` defaults to `"dev-secret-key"`** (`src/api/auth.py:11`) — verified. Same
  class as A1, far larger blast radius (forge any user's token). Presumably accepted for local dev,
  but a self-hoster following the quickstart is never told it is unset.
- **[LOW] In-memory OAuth state never expires and breaks under >1 uvicorn worker**
  (`integrations.py:39,786-790`) — `created_at` is stored next to a comment saying it expires after
  10 minutes; **nothing ever reads it**. Salesforce and OIDC already solved this with stateless
  signed state + TTL; that pattern can be ported.

### A5 — Confirmed correct, do not touch

Zendesk (the reference implementation), `jira_webhook.py` in full, `asana_webhook.py` in full,
`usage_webhooks.py` (the cleanest example in the repo — `org_id = auth.organization_id`, body
explicitly not trusted), `public/auth.py`, `_oidc_state.py` + Salesforce state signing,
`shared_links.py`, `invites.py`. All HMAC comparisons repo-wide use `compare_digest` **except**
`events_ws.py:157`. Intercom's HMAC-SHA1 **is** correct per vendor spec and is unaffected by SHA-1
collision attacks — **do not "fix" it.**

Three things that turned out not to exist: no password-reset route (the
`RESEND_TEMPLATE_PASSWORD_RESET` template in `CLAUDE.md` is unwired), no unsubscribe route, and
`/health/detailed` is **not** unauthenticated (it carries `require_system_admin`).

### A6 — Recommended scope revision

The sweep's ordering, which I endorse:

1. **`events_ws.py`** — kill the default + `compare_digest`. Smallest change, largest exposure.
2. **Fail-open → `return False`** on Slack, Intercom **and email** (3 lines, 3 files), plus
   inverting `test_email_webhooks.py:367-378`.
3. **`source_events.py`** — `if not X: return []` on all four branches, with a
   `test_missing_*_returns_empty_not_cross_tenant_fanout` twin for each.
4. Linear fail-closed + encrypt `webhook_secret` (migration).
5. Zendesk timestamp freshness (one line, reuses Slack's logic).
6. Drop `dict(request.headers)` from the generic webhook's `event_data`.

**Items 2 and 3 must ship together** — either alone leaves the Intercom chain exploitable from the
other end.

**This supersedes G3.** The multi-org-prevalence caveat still applies to the *cross-tenant* framing,
but A1 does not depend on it: a single-org install with `INTERNAL_EVENTS_SECRET` unset is publicly
writable by anyone who has read this repo.

---

## Out of Scope

- **Encrypting `oauth_access_token`/`oauth_refresh_token`.** Needs a backfill migration; own
  branch. Only the false comment is corrected here (M9).
- **The Intercom envelope-shape fix** and `IntercomConnector.fetch_new_items`. Own branch, safe to
  do once M2 lands. **Intercom ingestion remains non-functional after this branch.**
- **RBAC on `linear_integration.py`** (17 ungated endpoints). Excluded deliberately: gating it
  removes a capability members have today (`LinkedIssuesCard`, `CreateIssueDialog` on
  member-visible pages), so it is a product decision requiring frontend work. Filed separately.
- **A per-org webhook secret for Intercom/Slack.** Schema change; would properly fix the
  "signature can't identify a tenant" problem, but is a redesign.
- `oauth-state-in-process-dict` (P3), `intercom-writeback-orphaned` (P2).
- Any public write-up of the defects until merge (embargo).

---

## Proposed aspects

1. **`intercom-webhook-hardening`** — M1, M2, M8, S1, S3. Fail-closed verifier + tenancy guard +
   rewritten tests.
2. **`slack-webhook-hardening`** — M3, M4, M5. Tenancy guard immediately, signature in shadow,
   operator visibility (incl. the frontend flag).
3. **`integrations-rbac`** — M6, M7. Role gates plus callback-reachability regression tests.
4. **`docs-and-comment-correctness`** — M9, M10. Env-var documentation and the false-comment fix.
