# Implementation Report — ingestion-webhook (Zendesk real-time entry point)

**Feature:** `zendesk-integration` · **Aspect:** `ingestion-webhook` · **Date:** 2026-07-05
**Branch:** `feat/zendesk-integration` (worktree `.claude/worktrees/feat-zendesk-integration`)
**Commit range:** `f39b0a8..819b381` (6 commits, all on top of the already-merged
`backend-connection`, `ingestion-core`, and `ingestion-pull` aspects)

## Status: DONE

## Commits (in order)

| Commit | Message |
|---|---|
| `f39b0a8` | `test(zendesk-webhook): subdomain resolution + HMAC signature helpers (RED)` |
| `3dda54d` | `feat(zendesk-webhook): implement _resolve_zendesk_subdomain + _verify_zendesk_signature (GREEN)` |
| `245bf6b` | `feat(zendesk-webhook): route skeleton — raw body, subdomain resolution, integration lookup (GREEN)` |
| `30df38e` | `feat(zendesk-webhook): enforce HMAC signature against per-org webhook_secret (GREEN)` |
| `c0ea7c7` | `feat(zendesk-webhook): active-source check + quick dedup + queue_source_event (GREEN)` |
| `819b381` | `test(zendesk-webhook): acceptance-criteria traceability + never-500 sweep (REFACTOR)` |

RED tests for all five plan phases were written up front in one file
(`tests/test_zendesk_webhook.py`) and confirmed failing (36 collected,
1 passed / 35 failed on import errors) before any production code was
added; each subsequent commit is the GREEN implementation for one plan
phase, verified against the corresponding test subset before moving on,
per the plan's phase-by-phase RED→GREEN→REFACTOR discipline.

## Files touched

- `services/backend-api/src/api/routes/source_webhooks.py` — new imports
  (`base64`, `Mapping`, `urlparse`, `ZendeskIntegration`, `decrypt_api_key`)
  + a new `# Zendesk Webhook` section appended after the existing Intercom
  section (no interleaving): `_resolve_zendesk_subdomain`,
  `_verify_zendesk_signature`, `_ignore`, and the
  `POST /zendesk/events` route (`handle_zendesk_webhook`).
- `services/backend-api/tests/test_zendesk_webhook.py` (new) — 36 tests.

No changes to `src/api/main.py` (route lives on the already-registered
`source_webhooks.router`), no migration, no worker-service or frontend-web
changes.

## Signature scheme implemented

```
X-Zendesk-Webhook-Signature = base64(
    HMAC-SHA256(webhook_secret, X-Zendesk-Webhook-Signature-Timestamp + raw_body)
)
```

- Verified over the **raw** request body (`await request.body()`, read
  before JSON parsing) — the same bytes object is both JSON-parsed and
  HMAC-verified; the parsed dict is never re-serialized for verification.
- Final comparison uses `hmac.compare_digest` (timing-attack resistant);
  a test (`test_uses_hmac_compare_digest`) wraps the real function and
  asserts it is invoked.
- The per-org `webhook_secret` is looked up **first** by resolving the
  `ZendeskIntegration` via `subdomain` (unlike Linear's brute-force-all-
  active-integrations pattern, which was intentionally *not* ported —
  Zendesk has an in-band org discriminator, Linear does not).

## Fail-closed decision (the one deliberate divergence from the Intercom template)

`verify_intercom_signature` returns `True` ("skip verification") when no
global env secret is configured — a dev-friendly bypass appropriate for an
optional global secret. Zendesk's `webhook_secret` is a **required
per-org** value once an operator opts into the real-time webhook (it is
nullable in the schema only because BYOK-only connections never generate
one). `_verify_zendesk_signature` therefore returns `False` on an
empty/`None` secret, and the route additionally short-circuits to **401**
*before* attempting decryption when `integration.webhook_secret` is falsy
— never falling through to the 200 "unknown_subdomain"/"no_active_source"
no-op shape. This was called out explicitly in the plan's Security Note
and is covered by `test_webhook_rejects_when_webhook_secret_not_set`,
which asserts the response is *not* either no-op shape.

Corrupt/rotated `LLM_ENCRYPTION_KEY` (`decrypt_api_key` raising) is caught
and mapped to 401, never a 500 (`test_webhook_never_500s_on_corrupt_encrypted_secret`).

## `event_data` shape — followed the ingestion-core locked contract, not the plan's terser Phase-4 prose

The plan's own "Interface contract" section (and its Phase 4 steps)
describe `event_data=payload.get("ticket", {})` — the bare ticket
sub-object. This **conflicts** with the ingestion-core aspect's
authoritative, already-merged, already-consumed locked contract
(`ingestion-core/_impl-report.md` §"Locked contracts" §1), which requires
the **nested** shape:

```python
{"ticket": {...}, "subdomain": "acmeco"}
```

`ZendeskAdapter.extract_content` / `check_triggers` / `get_external_ids`
(already merged, unchangeable from this aspect) all read
`event_data.get("ticket", {})` — passing the bare ticket dict as
`event_data` directly would make every one of those calls silently no-op
(`event_data.get("ticket", {})` on a dict that *is* the ticket returns
`{}`). I resolved this in favor of the locked contract:

```python
queue_source_event(
    source_type="zendesk",
    external_event_id=str(ticket_id),
    event_type="ticket.created",
    event_data={"ticket": ticket, "subdomain": subdomain},
    provider_context={"subdomain": subdomain},
)
```

This exactly mirrors how the already-merged `ingestion-pull` aspect
resolved the identical plan-vs-locked-contract ambiguity (its own impl
report documents the same deviation, same resolution).

`subdomain` placed into `event_data`/`provider_context` is always the
value that matched the trusted `ZendeskIntegration.subdomain` column, not
a raw/attacker-influenced value: `_resolve_zendesk_subdomain` is used only
to *find* the integration row (`ZendeskIntegration.subdomain == subdomain`),
and by construction the local `subdomain` variable equals
`integration.subdomain` at the point it is used downstream (the DB lookup
requires an exact match). This satisfies the ingestion-core report's
concern #1 ("both entry points must build `event_data["subdomain"]` from
the trusted `ZendeskIntegration.subdomain` column") without needing an
extra reassignment to `integration.subdomain` explicitly.

## Access-token / `fetch_context` branch: **not added** (deliberately)

Per the plan's own "Webhook payload contract" (pinned in Phase 0/1) and
the PRD's example body, the operator-configured Zendesk trigger payload
already includes `ticket.requester_email` directly in the webhook body —
this aspect's payload is **not thin**; it does not need
`fetch_context`/`access_token` enrichment to obtain the requester email.
This mirrors exactly how `ingestion-pull` resolved the same question (its
impl report: "requests `include=users` side-loading and merges the
matching user's email onto each ticket... before the ticket ever reaches
the shared core"). Both entry points now feed `ZendeskAdapter.extract_content`
a `ticket` dict that already carries `requester_email`, so `customer_email`
plumbing (ingestion-core's `content.get("customer_email")` →
`FeedbackItem.customer_email`) works without either entry point needing
`_process_event_for_source`'s `access_token`/`source.source_type ==
"zendesk"` branch that the ingestion-core report flagged as an open
follow-up (concern #2). I did not build that branch here — building it
would be scope creep for an aspect whose payload contract never triggers
`fetch_context`, and per the task instructions I was told to avoid
half-building it if not called for. This remains an explicit open item
for a future aspect **only if** a later change makes the webhook payload
thin (e.g. a minimal trigger body with just `ticket.id`).

## Response-class table (implemented)

| Condition | Response | `queue_source_event` called? |
|---|---|---|
| Malformed JSON body | 400 | No |
| No subdomain resolvable (payload + `ticket.url` + header) | 200 `ignored/missing_subdomain` | No |
| Subdomain resolved, no matching active `ZendeskIntegration` | 200 `ignored/unknown_subdomain` | No |
| Integration found, `webhook_secret` is `None`/empty | **401** | No |
| Integration found, secret set, signature/timestamp header missing | 401 | No |
| Integration found, secret set, signature present but wrong | 401 | No |
| Integration found, secret set, signature valid but body tampered post-sign | 401 | No |
| Integration found, `decrypt_api_key` raises (corrupt key) | 401 | No |
| Signature valid, no active `zendesk` `FeedbackSource` for the org | 200 `ignored/no_active_source` | No |
| Signature valid, active source, missing `ticket.id` | 200 `ignored/missing_ticket_id` | No |
| Signature valid, active source, ticket already has a `FeedbackSourceEvent` for that `source_id`+ticket id | 200 `duplicate` | No |
| Signature valid, active source, new ticket | 200 `queued` | **Yes** |
| `queue_source_event` raises (broker down) | 500 | Attempted, failed |

Every code path other than the deliberate broker-failure 500 returns
200/400/401, confirmed by a parametrized property-style sweep
(`TestZendeskWebhookNever500s.test_malformed_inputs_never_500`, 7 cases:
empty body, `{}`, non-JSON, raw garbage bytes, subdomain-only payload with
no signature headers, bogus signature only, timestamp-only). A second test
(`test_response_never_leaks_secret_or_signature`) asserts the plaintext
`webhook_secret` and the computed signature never appear in the response
body.

## Known limitation carried over from the plan (R4, not a bug)

The route's own quick synchronous dedup pre-check queries
`FeedbackSourceEvent.filter(source_id=source.id, external_event_id=str(ticket_id))`
— i.e. it assumes `external_event_id` *is* the ticket id. This holds for
this aspect's own webhook-queued events (`external_event_id=str(ticket_id)`)
and for this aspect's tests (which seed the "already ingested via pull"
fixture row with `external_event_id=str(ticket_id)` directly, per the
plan). However, the **already-merged** `ingestion-pull` aspect's real
`external_event_id` is a synthetic per-page value
(`f"zendesk-pull-{integ.id}-{ticket_id}-{end_time}"`, confirmed by reading
`worker-service/src/tasks/zendesk_sync.py:203`), not the bare ticket id —
so in production, a ticket already ingested via pull would **not** be
caught by this route's fast pre-check (it would fall through to
`queue_source_event` and re-queue). This is explicitly acknowledged by the
plan itself (R4: "Double-dedup redundancy is intentional... the route-level
check exists so this aspect's own tests can prove the no-duplicate-creation
guarantee... without depending on worker-service being importable from
backend-api's test suite"). The **authoritative** dedup still fires
correctly regardless: `_process_event_for_source` in worker-service
dedupes on `FeedbackSourceEvent.external_message_id == str(ticket_id)`
(via `ZendeskAdapter.get_external_ids`), which both pull and webhook feed
identically — so no duplicate `FeedbackItem` is ever created even when
this route's fast pre-check misses. Flagging this precisely rather than
silently "fixing" it, since fixing it (e.g. having the pre-check query
`external_message_id` instead, which worker-service sets but backend-api's
own writes never touch) is out of this aspect's scope and the plan does
not ask for it.

## Test results

**New file:** `pytest tests/test_zendesk_webhook.py -v` → **36 passed, 0 failed**

Breakdown by class:
- `TestResolveZendeskSubdomain` — 8
- `TestVerifyZendeskSignature` — 6
- `TestZendeskRouteSkeleton` — 3
- `TestZendeskSignatureEnforcement` — 6
- `TestZendeskWebhookQueueing` — 5
- `TestZendeskWebhookNever500s` — 8 (7 parametrized malformed-input cases + 1 no-leak test)

**Targeted regression sweep** (run after every phase; final run below),
covering every test file that imports/exercises `source_webhooks.py`
(`test_intercom.py`) plus all zendesk-scoped test files plus the sibling
webhook-route test files in the same module family:

```
pytest tests/test_zendesk_webhook.py tests/test_intercom.py \
       tests/test_zendesk_connection.py tests/test_zendesk_client.py \
       tests/test_zendesk_models.py tests/test_zendesk_sync_endpoint.py \
       tests/test_feedback_sources_zendesk.py tests/test_webhooks.py \
       tests/test_linear_webhook.py -q
```
→ **207 passed, 0 failed**

Per the task's explicit instruction, the full 2810-test backend-api suite
was **not** run (documented pre-existing segfault risk in
`test_report_ws.py`); the targeted sweep above is a superset of every file
this change could plausibly affect (the only production file touched,
`source_webhooks.py`, is shared with Slack/Intercom/generic-webhook routes
— all covered above — and Zendesk's own model/client/connection/sync/
feedback-source tests, also covered above). No regressions found; no
pre-existing-failure baseline was disturbed (all 207 targeted tests were
green both before Phase 1 and after Phase 5).

## Agent execution notes followed

- `source_webhooks.py`'s new Zendesk section was appended after the
  existing Intercom section (L328 onward at the time of first edit), not
  interleaved.
- No `main.py` edit; the route reuses the already-registered
  `source_webhooks.router`.
- No Alembic migration; no worker-service or frontend-web files touched.
- `ZendeskIntegration` import path was exactly `src.models.zendesk_integration`
  as the plan assumed (R1 — no fix needed).
- `event_type="ticket.created"` literal confirmed unchanged against
  `ZendeskAdapter.check_triggers` — no adjustment needed (R2).

## Fix — 500 on valid-but-non-dict JSON body (2026-07-05)

**Defect:** `payload = json.loads(body)` (route L421) never checked that
the parsed result was a dict. Valid-but-non-object JSON bodies — `[]`,
`123`, `"x"`, `true`, `null` — pass `json.loads` cleanly, then
`_resolve_zendesk_subdomain(payload, ...)` calls `payload.get("subdomain")`
(L349) on a `list`/`int`/`str`/`bool`/`NoneType`, raising an unhandled
`AttributeError` → HTTP 500. This violated the route's own "never 500 on
hostile input" invariant (documented above in the response-class table and
the `TestZendeskWebhookNever500s` sweep), which had only exercised
malformed/non-JSON bodies, not valid-but-wrong-shape JSON.

**TDD:**
- RED: added `TestZendeskWebhookNever500s.test_valid_non_dict_json_returns_400_not_500`,
  parametrized over `b"[]"`, `b"123"`, `b'"x"'`, `b"true"`, `b"null"`, each
  asserting `response.status_code == 400`. Confirmed failing first:
  `pytest tests/test_zendesk_webhook.py -v -k valid_non_dict_json` →
  **5 failed** (`AttributeError: 'list'/'int'/'str'/'bool'/'NoneType' object
  has no attribute 'get'`), matching the reported defect exactly.
- GREEN: added, immediately after the existing `JSONDecodeError` handler in
  `handle_zendesk_webhook`:
  ```python
  if not isinstance(payload, dict):
      raise HTTPException(status_code=400, detail="Invalid JSON")
  ```
  placed before `_resolve_zendesk_subdomain(payload, request.headers)` is
  ever called, reusing the same 400 status/detail shape as the existing
  `JSONDecodeError` branch.

**Validation:**
```
cd services/backend-api && source venv/bin/activate
LLM_ENCRYPTION_KEY=<test key> pytest tests/test_zendesk_webhook.py -v
```
→ **41 passed, 0 failed** (36 pre-existing + 5 new). No regressions to the
existing 401 signature paths, 200 no-op/dedup paths, or the 500
broker-failure path (`queue_source_event` raising is unaffected — that
occurs after this new dict check, on a different call path).

Full 2810-test backend-api suite intentionally **not** run per task
instructions (pre-existing segfault in `test_report_ws.py`).
