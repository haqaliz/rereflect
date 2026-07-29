# Card — integration-auth-tenancy-hardening

**Type:** feat (security hardening)
**Branch:** `feat/integration-auth-tenancy-hardening`
**Source:** freeform — no GitHub issue. Brief derived from `DEV-TRACKING.md` triage entries,
selected by `rereflect-next` on 2026-07-29.

> ⚠️ **Do not publish a public write-up of the P0 below until the fix has merged.**
> The `chore/intercom-zendesk-docs` branch deliberately omitted it from `docs/SELF_HOSTING.md`
> because documenting it while unpatched publishes a working exploit.

---

## Brief

Close the unauthenticated cross-organization write path on the Intercom webhook, then close
the role-check gap on the integration routes.

`DEV-TRACKING.md` names this as the designated next branch:

> **Why P0:** unauthenticated cross-tenant write. Deliberately **not** documented in
> `docs/SELF_HOSTING.md` on the `chore/intercom-zendesk-docs` branch — writing it up publicly
> while unpatched would publish a working exploit. **This should be the next branch after the
> docs land**, ahead of any Intercom feature work.

The docs branch landed in `09efba08` (current `master` HEAD), so this is now unblocked.

---

## Defect 1 (P0) — `intercom-webhook-unauthenticated-cross-org-write`

Two defects that **compose** into one exploitable path. Fixing either alone leaves the hole
open. Both verified by reading the code on `master` @ `09efba08`, not inferred from the doc.

### (a) The Intercom webhook signature check fails open

`services/backend-api/src/api/routes/source_webhooks.py:268-270`

```python
if not secret:
    logger.warning("INTERCOM_CLIENT_SECRET not configured, skipping signature verification")
    return True
```

`INTERCOM_CLIENT_SECRET` is documented in **no** `.env.example`, **no** `.env.prod.example`,
**neither** docker-compose file, and **nowhere** in `docs/SELF_HOSTING.md`. Unset is therefore
the default state of every install, so `POST /api/v1/webhooks/intercom/events` accepts
arbitrary unsigned payloads out of the box.

**Reference implementation for the fix:** `_verify_zendesk_signature`
(`source_webhooks.py:383-403`) already fails closed, and its docstring explicitly calls out
the contrast — the correct pattern was known and simply not applied here.

### (b) A missing `app_id` unscopes the organization filter

`services/worker-service/src/tasks/source_events.py:142-161`

The entire Intercom integration-matching block sits behind `if workspace_id:` with **no
`else: return []`**. A payload without `app_id` therefore skips matching entirely and leaves the
query filtered only by `source_type="intercom"` and `is_active=True`, i.e. **matching every
active Intercom source in every organization on the instance.**

The base query (`source_events.py:112-115`) has **no `organization_id` predicate at all** — the
function does not even take an `organization_id` parameter. Tenancy exists *only* inside the
per-type branches, so a branch that falls through has no backstop.

> **CORRECTION (Phase 2 dig).** An earlier draft of this card said "the branch immediately above
> it *does* have one." **That was wrong.** Slack's `else: return []` hangs off the **inner**
> `if matching_integration_ids:`, not off `if team_id:`. **Slack has the identical unscoped
> fall-through**, and `handle_slack_webhook` has the identical fail-open
> (`source_webhooks.py:48-50`: unset `SLACK_SIGNING_SECRET` → `return True`). Verified directly.
> This answers open question 3: **Intercom is not the only one.** Zendesk is the *only* branch
> with a correct guard (`if not subdomain: return []` at `:180-182`, plus explicit
> `organization_id` scoping rather than indirect `integration_id` scoping).

### The signature check cannot establish tenancy even when configured

`INTERCOM_CLIENT_SECRET` is a **single global env var** (`source_webhooks.py:32`), used as the
OAuth client secret for one Intercom app that every org connects through. A valid HMAC therefore
proves only "signed by whoever holds this instance's client secret" — it identifies neither a
workspace nor an organization. Contrast Zendesk, where `webhook_secret` is **per-org** on the
`ZendeskIntegration` row and is looked up *by* the tenant discriminator before verification —
making authentication and tenant resolution the same operation.

**Consequence: fixing the fail-open check does NOT close the cross-tenant hole.** The two are
independent controls and both are load-bearing:
- fail-closed HMAC authenticates the *sender*,
- required-and-resolving `app_id` identifies the *tenant*.

There is no per-org secret available for Intercom today: the `integrations` table has no
webhook-secret column of any kind, and the webhook URL is a fixed path with no per-tenant
component (contrast the generic `/inbound/{webhook_id}` route, which has *both* a capability URL
and a per-source `secret_token`). Adding one would be a schema change and is out of scope.

### Composed consequence — and an honest correction to the severity

The reachability is real: on a default install an unauthenticated caller who knows the URL is
processed, and `_find_matching_sources` returns every org's Intercom sources. There is **no
later org check anywhere** — whatever that function returns *is* the tenancy decision, written
verbatim as `organization_id` on the created rows (`source_events.py:216-217`, `:284-292`).

**However, `DEV-TRACKING.md`'s "inject feedback into arbitrary organizations" overstates what
lands *today*.** A separate payload-shape bug blocks it: the route queues the **unwrapped**
`payload["data"]` (`source_webhooks.py:319`) while `IntercomAdapter` expects the **full
envelope**, re-deriving `data.item` and a top-level `topic` (`worker-service/src/adapters/intercom.py:70,82-83,145-146`).
So `extract_content` always returns `text=""` and `_process_event_for_source` bails with
`status="ignored"` / `empty_text`. Verified empirically by running the adapter against exactly
what the route queues.

What actually lands per foreign org today is a **`FeedbackSourceEvent` log row** carrying
attacker-controlled `event_data` JSON under another org's `organization_id` — a silent
cross-tenant write, but a log row, not a feedback item.

> ⚠️ **SEQUENCING CONSTRAINT — this is the most important finding in the dig.**
> `FeedbackItem` injection is blocked **only** by the payload-shape bug, not by any security
> control. **Fixing the envelope shape without fixing tenancy first would upgrade this to
> exactly the arbitrary-feedback-injection the card originally described.** The signature
> fail-closed and the `else: return []` must land **before or together with** any adapter/
> envelope fix — never the shape fix first.

**Side effect worth noting:** that same shape bug means Intercom ingestion **has never worked**.
`docs/SELF_HOSTING.md` claims "New Intercom conversations appear as feedback items… within a
minute or two" — that does not occur. This is consistent with `IntercomConnector.fetch_new_items`
being an unimplemented placeholder: neither the pull path nor the webhook path produces feedback.

### Known trap — the existing test pins the vulnerability as the expected contract

Worse than "asserts nothing about tenancy". `test_intercom.py:294-325`
(`test_webhook_processes_conversation_created`) bakes the vulnerable value into
`assert_called_once_with` as the *expected* kwargs:

```python
provider_context={"conversation_id": "conv_100", "workspace_id": None},
```

The test payload deliberately omits `app_id`, `queue_source_event` is mocked, no DB is touched,
and no org fixture exists anywhere in `TestIntercomWebhook`. **Not one payload fixture in the
entire repo contains `app_id`** (`test_intercom.py:251-260, 300-309, 335-344, 366-376, 390-393`;
worker fixtures in `test_intercom_adapter.py` likewise). This test must be **rewritten**, not
extended — it will fail once tenancy is enforced, and that failure is correct.

### Ready-made templates (this class was already fixed once, for Zendesk)

- **Worker tenancy regression:** `worker-service/tests/test_zendesk_adapter.py:462-477`
  `test_missing_subdomain_returns_empty_not_cross_tenant_fanout` — seeds two orgs, calls
  `_find_matching_sources(db, "zendesk", {})`, asserts `== []`. Direct template; needs Intercom
  and Slack twins.
- **Route fail-closed:** `test_zendesk_webhook.py:409-430` (401 + `mock_queue.assert_not_called()`)
  and the pure-function `:250-268` (`test_empty_secret_returns_false_fail_closed`,
  `test_none_secret_returns_false_fail_closed`).
- **Tampered-body:** Zendesk has `test_webhook_rejects_tampered_body` (sign payload A, send
  payload B). Intercom's `test_webhook_rejects_invalid_signature` only sends the literal
  `"sha1=badsignature"` — weaker.
- **Cross-org fixtures:** `test_anomalies_auth.py:16-79` `org_a`/`org_b`/`user_a`/`headers_a`.
  This is the **only** true two-tenant isolation suite in the backend suite.
- **RBAC:** `test_jira_connection.py:547-566` `TestRBAC` with `member_headers` → 403.

### Coverage gaps found

- There is **no `test_source_events.py`** in worker-service. Every existing test of
  `_find_matching_sources` passes `source_type="zendesk"` — the intercom, slack, email and
  webhook branches have **zero** coverage.
- No test anywhere proves the webhook → worker → row path end-to-end for Intercom. The two
  halves are tested in isolation, which is exactly why the envelope-shape bug survived.

---

## Defect 2 (P1) — `integrations-routes-missing-rbac`

`services/backend-api/src/api/routes/integrations.py` contains **zero** occurrences of `403`,
`require_admin_or_owner` or `require_owner` (verified: `grep -c` → 0). `get_current_org`
validates the JWT but never checks `current_user.role`.

So a **`member` can drive the OAuth connect flow via the API**, contradicting the RBAC table in
`CLAUDE.md` ("Manage integrations: Owner ✅ / Admin ✅ / Member ❌"). The frontend hides the UI;
the backend does not enforce it — the classic shape of an access-control gap that looks fine in
manual testing.

**Audit result (Phase 2 dig) — the gap is NOT confined to this file.**
`linear_integration.py` has the identical problem: **17 endpoints, zero real role gates**,
carrying only `require_feature("linear_integration")` which is inert under `SELF_HOSTED`.

Six other integration modules gate **every** endpoint — including read-only GETs — via
`dependencies=[Depends(require_admin_or_owner)]`:

| Module | Endpoints | Gated? |
|---|---|---|
| `integrations.py` (Slack/Discord/Intercom) | 14 | **none** |
| `linear_integration.py` | 17 | **none** (only inert `require_feature`) |
| `jira_integration.py` | 12 | all 12 |
| `asana_integration.py` | 12 | all 12 |
| `salesforce_integration.py` | 12 | all |
| `hubspot_integration.py` | 11 | all |
| `zendesk_integration.py` | 7 | all |

So the house convention is unambiguous: **decorator style, whole surface, reads included.**

### MUST NOT be gated (would break real flows)

- `GET /slack/oauth/callback`, `GET /intercom/oauth/callback`, Linear's `GET /callback` — hit by
  a **browser redirect** with no `Authorization` header; identity comes from the validated
  `state` param, not a JWT.
- The HMAC-authenticated inbound receivers (`asana_webhook.py`, `jira_webhook.py`,
  `linear_webhook.py`) — authenticated by signature, not JWT.

These need explicit *"still reachable unauthenticated"* regression tests, not gates.

### ⚠️ Open product decision — gating Linear removes a live member capability

Two frontend components call Linear endpoints from **member-visible** pages and neither checks
role:

- `components/feedback/LinkedIssuesCard.tsx` — rendered unconditionally on the feedback detail
  page (`feedbacks/[id]/page.tsx:613`); calls `GET /integrations/linear/issues`. It swallows
  errors in a bare `catch {}` (`:36`), so a gate makes the card **silently vanish** for members.
- `components/integrations/CreateIssueDialog.tsx` — used on the member-visible pain-points and
  feature-requests pages; calls Linear's create-issue plus the teams/projects/labels proxy GETs.

**A member can create a Linear issue from feedback today**, and that works because Linear's
backend was never gated. Jira's identical flow is already fully gated, so **Jira and Linear
already disagree with each other**. Applying the house convention to Linear is a real behaviour
change for members, not a tidy-up.

*Decision needed:* is "view/create a tracker issue from feedback" a **member** action (like
"Import feedback (CSV)" in the RBAC matrix) or an **integration-management** action? If gated,
both components must be updated to hide themselves for members (the `isAdminOrOwner` pattern
already used at `settings/integrations/page.tsx:90`) rather than fail silently.

*Note:* `settings/integrations/page.tsx:93-97` already redirects non-admins **before**
`fetchData()` runs, so gating `integrations.py` itself has **no known member-facing consumer**
and is safe with no caveat.

---

## Defect 3 (P1, comment-only in this branch) — `oauth-tokens-stored-plaintext`

`Integration.oauth_access_token` is a plain `Text` column and `integrations.py` never calls
`encrypt_api_key`/`decrypt_api_key` on the **Slack or Intercom** OAuth paths (verified:
`grep -c` → 0), while every newer BYOK integration (Zendesk, Jira, Asana, HubSpot, Salesforce)
does encrypt.

`services/backend-api/src/models/integration.py:19` carries the comment *"OAuth tokens
(encrypted at application level before storage)"* — **which is false** and actively misleads an
auditor.

**Scope decision:** the code fix needs a backfill migration to encrypt existing rows in place,
so it gets its **own branch**. In *this* branch, correct the false comment only.
`DEV-TRACKING.md` states this explicitly: *"if the fix is deferred, the comment must be
corrected immediately either way."*

---

## Out of scope for this branch

- Encrypting the OAuth token columns + the backfill migration (own branch — see above).
- `oauth-state-in-process-dict` (P3) — `oauth_states` module-level dict, no TTL/Redis backing.
- Intercom operability Part B (P1) — token-paste connect path, implementing
  `IntercomConnector.fetch_new_items` (still `# Placeholder - returns empty list` at
  `services/worker-service/src/tasks/integrations.py:167`). Must follow the security fix.
- `intercom-writeback-orphaned` (P2).

---

## Migration / rollout caveat

Failing the signature closed will **silently stop ingestion** for any operator currently
relying on the unset-secret path. That is a real behaviour change on an ingestion path and
needs a loud signal (startup and/or per-rejection log) plus a `docs/SELF_HOSTING.md` note
documenting `INTERCOM_CLIENT_SECRET` — not just a flipped boolean.

## Open questions for the PRD

**Answered by the Phase 2 dig:**

3. ~~Does the same fail-open pattern exist on other source webhooks?~~ **Yes — Slack.** Same
   fail-open (`source_webhooks.py:48-50`) *and* same unscoped fall-through. Zendesk is the only
   correct one. `email`/`webhook` branches also fall through, but their `source_id` is resolved
   **by the caller** from a trusted lookup rather than taken from an attacker payload, so they
   are lower risk — to be confirmed, not assumed.
4. ~~Is `app_id` reliably present on legitimate Intercom events?~~ **Yes.** Intercom's
   notification envelope carries `app_id` at the top level for all topics, including the three
   handled ones. Returning `[]` on a missing `app_id` **would not drop real traffic.**

**DECIDED by the user, 2026-07-29:**

6. **Scope = Intercom + Slack.** Both carry the same two defects; fixing only one knowingly
   leaves an identical hole. **But the two are not treated identically on the fail-closed flip:**
   - **Intercom** → fail closed immediately. Ingestion has never worked (envelope-shape bug), so
     there is no live traffic to break. Zero migration risk.
   - **Slack** → **shadow first.** Slack ingestion demonstrably *does* work today, so a hard flip
     stops real traffic for any install running without `SLACK_SIGNING_SECRET`. Log loudly on
     every unsigned/unverifiable request for one release, then reject in the next.
   - The **tenancy guard** (`else: return []`) applies to **both immediately** — it is not
     shadowed. A missing `team_id`/`app_id` is never legitimate.

5. **RBAC scope = `integrations.py` only.** It has no member-facing consumer (the settings page
   redirects non-admins before fetching), so the full house-convention gate is safe with no
   caveat. **`linear_integration.py` is filed separately** as its own item: it is a product
   decision about whether members may view/create tracker issues from feedback, and it requires
   frontend work (hiding `LinkedIssuesCard` / `CreateIssueDialog` for members) that does not
   belong in a security branch.

**Still open — need a decision:**

1. Fail closed **unconditionally**, or allow an explicit opt-out escape hatch for an operator
   who knowingly runs the webhook behind a trusted network boundary? (Zendesk precedent:
   unconditional.)
2. Should an unsigned/unverifiable request return `401`, or `202`-and-drop to avoid giving an
   attacker a probe oracle? (Zendesk precedent: `401`.)
5. RBAC scope — see the Linear member-capability decision under Defect 2.
6. **Scope of this branch:** Intercom only, or Intercom + Slack? Slack is the *same two defects*
   in the same two files. Fixing only Intercom knowingly leaves an identical hole. Against that:
   a larger blast radius, and Slack ingestion demonstrably *does* work today (unlike Intercom),
   so a fail-closed flip there will stop real traffic for anyone running without
   `SLACK_SIGNING_SECRET` set.
7. Does the `IntercomConnector`/adapter envelope-shape fix belong in this branch? It is the
   difference between "log-row injection" and "feedback injection", so it **must not** ship
   before the tenancy fix — but shipping it *after*, in a later branch, means Intercom ingestion
   stays broken meanwhile (it already is, and has always been).

## Notes for the implementer

- `hmac.compare_digest` on a raw header string raises `TypeError` on non-ASCII input → **500,
  not 401**. Same line being edited; worth handling.
- Slack's verifier has a **300-second replay window** (`source_webhooks.py:52-56`).
  **Intercom's has none** — a captured valid payload replays indefinitely.
- Intercom's OAuth callback stores `workspace_id` with a `""` default
  (`integrations.py:1051`) — a `/me` response missing `app.id_code` silently stores an empty
  string that can never match. Guard against `""` as well as `None`.
- `feedback_sources.py:404-406` copies `workspace_id` into the source's `provider_config`, but
  the matcher **never reads that copy** — it goes through `Integration.config` only. Don't be
  misled into "fixing" the unused copy.
- `_find_matching_sources` is shared infrastructure with two callers: `process_source_event`
  (all five source types) and `zendesk_sync.py:176` (scheduled pull, trusted subdomain from a
  column). Changes affect both.
