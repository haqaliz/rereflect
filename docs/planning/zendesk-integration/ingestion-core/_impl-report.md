# Implementation Report — ingestion-core (Zendesk)

**Feature:** `zendesk-integration` · **Aspect:** `ingestion-core` · **Date:** 2026-07-05
**Branch:** `feat/zendesk-integration` (worktree
`.claude/worktrees/feat-zendesk-integration`)
**Commit range:** `4b13c11..75dc48a` (8 commits, all on top of the already-merged
`backend-connection` aspect)

## Status: DONE

## Commits (in order)

| Commit | Message |
|---|---|
| `45465fa` | `feat(zendesk): ZendeskAdapter skeleton + get_external_ids + registry` |
| `6230236` | `feat(zendesk): extract_content (subject+description, HTML-stripped, requester_email)` |
| `7a9df37` | `feat(zendesk): check_triggers (new_ticket + keyword)` |
| `7194a2b` | `feat(zendesk): fetch_context (ticket + requester via stored token, graceful errors)` |
| `c55f969` | `feat(zendesk): worker-side ZendeskIntegration mirror model (no-FK, column-parity test)` |
| `26564d7` | `fix(zendesk): SSRF guard on fetch_context subdomain (client-side re-assertion)` — added mid-flight in response to a coordinator security callout, folded into the plan's Phase 4 scope |
| `8276b6f` | `feat(zendesk): source_events zendesk subdomain matching + customer_email plumbing` |
| `75dc48a` | `fix(worker): _log_event external_message_id dedup bug (Zendesk/Intercom/Email affected)` |

Each `feat(zendesk)` commit corresponds 1:1 to a plan phase (1–6), built strict
RED→GREEN (test written and confirmed failing before the production code was
written). Phase 7 (end-to-end verification) required no new production code —
its three integration tests are folded into the Phase 6 commit + the bug-fix
commit, per the plan's own note that Phase 7 "should already be GREEN if
Phases 1–6 are correct."

## Files touched

- `services/worker-service/src/adapters/zendesk.py` (new) — `ZendeskAdapter`
- `services/worker-service/src/adapters/__init__.py` — registry entry
- `services/worker-service/src/models/__init__.py` — `ZendeskIntegration` mirror model
- `services/worker-service/src/tasks/source_events.py` — `zendesk` matching branch,
  `customer_email` plumbing, `_log_event` dedup fix
- `services/worker-service/tests/test_zendesk_adapter.py` (new, 39 tests)

No changes to `requirements.txt` (httpx already a dependency, used by Intercom/Slack).

## Test results

**New file:** `pytest tests/test_zendesk_adapter.py -v` → **39 passed, 0 failed**

Breakdown by class:
- `TestGetExternalIds` — 1
- `TestExtractContent` — 6
- `TestCheckTriggers` — 8
- `TestFetchContext` — 5 functional + 9 parametrized SSRF-guard cases = 14
- `TestAdapterRegistry` — 1
- `TestModelsAndMigration` — 1 (column-parity vs. real backend-connection model, no xfail needed since that aspect is already merged on this branch)
- `TestFindMatchingSources` — 5
- `TestIngestionCoreIntegration` — 3 (create-once + customer_email, dedup-on-redelivery, no-op-on-unmatched-subdomain)

**Full worker suite:** `pytest tests/ -q`
- **Before this aspect (baseline, captured before any zendesk changes):** 567 passed, 23 failed
- **After this aspect:** 606 passed, 23 failed
- The 23 failing tests are **byte-for-byte identical** before and after (diffed the two `FAILED` line lists) — all pre-existing, unrelated to source_events/zendesk (anomaly-dispatch Slack/email tests hitting a `MagicMock.__format__` issue, churn-calibration-task tests, weekly-digest tests, sentry-flag tests). **Zero regressions introduced.**

## The `_log_event` bug — verified real, not invented

Confirmed by reading the code before touching anything:
`_process_event_for_source` computes the correct dedup key via
`adapter_event_id, message_id = adapter.get_external_ids(event_data)` and
checks for an existing `FeedbackSourceEvent` filtered on that `message_id`.
But `_log_event` (called to persist the row) **independently re-derived**
`external_message_id` via:

```python
message_id = (
    event_data.get("ts") or
    event_data.get("item", {}).get("ts") or
    event_data.get("content_hash")
)
```

This is a Slack/webhook-shaped heuristic. For Zendesk (`{"ticket": {...},
"subdomain": ...}`), Intercom (nested under `data.item`, not top-level
`item`), and Email, this always evaluates to `None`, so the stored
`external_message_id` never matches what the dedup query filters on next
time — dedup silently never fires.

**RED reproduction** (`test_duplicate_event_is_deduped_via_feedback_source_event`,
written and run *before* any fix): fed the same Zendesk ticket (id `555`)
through `process_source_event` twice with different `external_event_id`s
(`evt-555-a`, `evt-555-b`, simulating a webhook redelivery / pull-cursor
overlap). Confirmed failing:
```
assert len(items) == 1
E   assert 2 == 1
```
Two `FeedbackItem` rows were created instead of one — dedup was silently
broken, exactly as the plan predicted.

**Fix (strict superset, verified no regression for Slack/Webhook):**
`_log_event` gained an optional `message_id: Optional[str] = None` parameter.
The three call sites in `_process_event_for_source` where
`adapter.get_external_ids()` has already run (`empty_text`, `processed`,
`pending_created`) now pass `message_id=message_id`. The one call site that
fires *before* `get_external_ids` runs (`no_trigger_match`) is unchanged —
still uses the legacy derivation, which is fine since "ignored" rows without
a trigger match were never in the dedup filter anyway.

Verified by code inspection this changes nothing for the two adapters whose
legacy heuristic happened to work:
- **Slack**: `get_external_ids` returns `message_id = event_data.get("ts")`
  (or `item.get("ts")` for `reaction_added`) — identical to what the legacy
  heuristic derived.
- **Webhook**: `get_external_ids` returns `message_id =
  event_data.get("content_hash")` — identical to the legacy heuristic's third
  fallback.

So the fix silently *repairs* dedup for Intercom, Email, and Zendesk without
altering Slack/Webhook behavior at all — no dedicated "keep Slack/webhook
dedup working" test was needed beyond the full-suite regression check (no
pre-existing test exercised `_log_event`/`external_message_id`/dedup at all —
confirmed via repo-wide grep before writing anything).

Also removed dead code inside `_log_event`: a no-op `try/except` block that
queried `FeedbackSourceEvent.source_id` and discarded the result, plus an
unused `from src.adapters import get_adapter` import — both were vestigial
and did nothing.

## Security fix (added mid-implementation per coordinator instruction)

**Issue:** `fetch_context` built `https://{subdomain}.zendesk.com/...` and
passed `auth=(f"{email}/token", api_token)` to `httpx.Client` using an
**unvalidated** `subdomain` taken directly from `event_data` (provider-
controlled, not the validated `ZendeskIntegration.subdomain` column). A
crafted `subdomain` (e.g. containing `@`, `#`, `/`, `.`, or an oversized
label) could redirect the request host and exfiltrate the org's Zendesk API
token to an attacker-controlled server via the `auth=` header.

**RED:** `test_rejects_malicious_subdomain_without_sending_request`,
parametrized over 9 cases — `"evil.com#"`, `"evil.com/"`, `"a.b"`,
`"foo@bar"`, `""`, `"foo_bar"`, `"-lead"`, `"trail-"`, and a 64-char label —
asserting `fetch_context` returns `{}` and `httpx.Client` is **never
constructed**. Confirmed failing against the pre-fix code (all 9 cases built
a URL and made requests).

**GREEN:**
- Added `_is_safe_subdomain()` — validates the subdomain against a strict
  single-DNS-label regex (`^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$`,
  plus a stripped-whitespace check), mirroring
  `ZendeskClient._assert_safe_subdomain` in
  `services/backend-api/src/services/zendesk_client.py`. Called at the top of
  `fetch_context`, before any URL construction or `httpx.Client` call —
  returns `{}` immediately on failure.
- Added `_assert_url_host()` as defense-in-depth: after constructing each
  request URL, parses it with `urllib.parse.urlparse` and asserts the
  hostname is exactly `{subdomain}.zendesk.com` immediately before the
  request is sent (belt-and-suspenders on top of the regex gate).

All 9 malicious-subdomain cases now return `{}` with zero `httpx.Client`
calls; the existing valid-subdomain success-path tests (fetch ticket +
requester, skip-requester-when-absent, API-error-swallowed) still pass
unchanged.

**Scope note:** this is a *client-side re-assertion* inside the worker
adapter. The primary SSRF gate (subdomain normalization + DNS/private-IP
rejection) lives in the backend `connect` route
(`services/backend-api/src/api/routes/...`), which is out of scope for this
aspect. This fix protects the adapter against a subdomain arriving via
`event_data` from a path that bypasses that route-level gate (e.g. a
webhook/pull payload where the `subdomain` field is attacker-influenced
rather than sourced strictly from the stored `ZendeskIntegration` row) —
exactly the scenario `ingestion-pull`/`ingestion-webhook` must guard against
when they build `event_data`.

## Locked contracts for `ingestion-pull` / `ingestion-webhook`

These are the exact shapes both future entry points must produce. Anything
that deviates from this will not match what `ZendeskAdapter` /
`_find_matching_sources` expect.

### 1. Normalized `event_data` shape

```python
{
    "ticket": {
        "id": 4521,                                   # required, int
        "subject": "Billing issue",                   # str; HTML is stripped by the adapter, raw is fine
        "description": "<p>My invoice is wrong</p>",   # optional/None/"" all handled -> subject-only text
        "status": "open",                              # optional, passed through to metadata verbatim
        "tags": ["billing", "urgent"],                  # optional, defaults to [] in metadata
        "requester_email": "jane@example.com",          # optional/None -> customer_email is None, item still ingested
    },
    "subdomain": "acmeco",   # bare label, NOT a URL — required for fetch_context + metadata
}
```

- `event_type` passed to `process_source_event(...)` / `check_triggers(...)`
  must be the literal string `"ticket.created"` for new-ticket events (the
  only granularity currently handled — `check_triggers` returns `None` for
  any other `event_type` unless a `keywords` trigger also matches the
  subject/description text, in which case it fires regardless of
  `event_type`).
- `provider_context` passed to `process_source_event(...)` must be
  `{"subdomain": "acmeco"}` — this is what `_find_matching_sources` reads to
  look up the matching `ZendeskIntegration`/`FeedbackSource` pair. If
  `subdomain` is missing/falsy, `_find_matching_sources` returns `[]` (a
  `no_sources` no-op, never a crash) for `source_type="zendesk"`.
- **Dedup key = ticket id.** `get_external_ids(event_data)` returns
  `(str(ticket_id), str(ticket_id))` — both event_id and message_id are the
  *same* stringified ticket id. A webhook redelivery (new delivery id, same
  ticket) and a pull-cursor overlap (new synthetic `external_event_id`, same
  ticket) both dedup correctly as long as `event_data["ticket"]["id"]` is
  identical across calls — pass a distinct `external_event_id` per call
  (that field is NOT part of the dedup key) but the same `ticket.id`.

### 2. `access_token` packing for `fetch_context`

Zendesk uses HTTP Basic auth with the token-access convention
`("{email}/token", api_token)`, not a bearer token. The single
`access_token: Optional[str]` parameter on `BaseSourceAdapter.fetch_context`
is repurposed to carry **`"{email}:{api_token}"`** (colon-delimited, split
once via `access_token.split(":", 1)`).

- Whoever wires `fetch_context` (`ingestion-pull`/`ingestion-webhook`, or
  whichever aspect owns building the `access_token` argument passed into
  `_process_event_for_source`) must build this string from the stored
  `ZendeskIntegration.email` / **decrypted** `ZendeskIntegration.api_token`.
- Malformed/missing separator (no `":"` in the string) → treated as no
  token, `fetch_context` returns `{}` immediately.
- **This is layered on top of the subdomain SSRF guard** (see Security fix
  above) — even with a well-formed `access_token`, `fetch_context` will
  refuse to make any request if `event_data["subdomain"]` isn't a bare,
  valid DNS label. Both `ingestion-pull` and `ingestion-webhook` should
  ensure the `subdomain` they place into `event_data` is sourced from the
  validated `ZendeskIntegration.subdomain` column (not re-derived from
  arbitrary request/webhook input) — the adapter's guard is a second gate,
  not a substitute for building `event_data` from a trusted source.
- This does **not** change the `BaseSourceAdapter.fetch_context` signature —
  purely a Zendesk-adapter-local interpretation of the existing
  `access_token: Optional[str]` parameter.

### 3. `customer_email` plumbing (generic, not Zendesk-only)

`extract_content()` may return an optional top-level `customer_email` key
(sibling to `text`/`metadata`). `ZendeskAdapter.extract_content` always
includes this key, set to `ticket.requester_email` (or `None` if absent —
the item is still ingested, never dropped for lack of an email, per PRD 9b).

`_process_event_for_source` now reads `content.get("customer_email")`
(defaults to `None`) and sets it directly on the created `FeedbackItem`:

```python
feedback = FeedbackItem(
    ...,
    customer_email=content.get("customer_email"),
)
```

This is purely additive — Intercom/Slack/Email/Webhook don't return this
key, so their created `FeedbackItem`s are unaffected (`customer_email` stays
`None` as before).

**Known gap (documented, not a regression):** the `auto_import=False` /
`PendingFeedback` path has no `customer_email` column — Zendesk feedback
routed there loses the requester mapping until manually approved into a
`FeedbackItem`. Out of scope for this aspect (PRD's default recommendation
is auto-provision + `auto_import=True`).

### 4. `process_source_event` / `queue_source_event` call shape

`process_source_event` is a `@shared_task(bind=True, max_retries=3,
default_retry_delay=30)` Celery task. In production it's invoked via
`celery_app.send_task("src.tasks.source_events.process_source_event", ...)`
(see `services/backend-api/src/api/routes/source_webhooks.py` and
`email_webhooks.py` for that pattern — out of scope here, shown for
reference only).

For a **synthesized event** (tests, or a future pull/webhook aspect calling
the task function directly rather than via Celery), call it as a plain
function — Celery's `Task.__call__` handles the implicit `self` injection
for `bind=True` tasks, so no `.delay()`/`.run()`/broker is needed:

```python
process_source_event(
    source_type="zendesk",
    external_event_id="evt-<unique-per-delivery-or-pull-page>",
    event_type="ticket.created",
    event_data={
        "ticket": {
            "id": 4521,
            "subject": "...",
            "description": "...",
            "status": "open",
            "tags": [...],
            "requester_email": "...",
        },
        "subdomain": "acmeco",
    },
    provider_context={"subdomain": "acmeco"},
)
```

This is the exact convention used by
`TestIngestionCoreIntegration` in `test_zendesk_adapter.py` and mirrors how
`test_run_playbook_task.py` calls `run_playbook(exe.id)` directly (another
`bind=True` task) without a broker.

Return shape on success:
```python
{"status": "processed", "results": [{"source_id": ..., "status": "feedback_created" | "duplicate" | "pending_created" | "no_trigger_match" | "empty_text" | "channel_mismatch", ...}]}
```
or `{"status": "no_sources", "event_id": external_event_id}` when no
`FeedbackSource`/`ZendeskIntegration` pair matches `provider_context["subdomain"]`
(never raises).

## Edge cases verified

- Missing/empty `description` → subject-only `text`, no dangling `"\n\n"` (2 tests).
- Missing `requester_email` → `customer_email=None`, item still created (not dropped).
- Missing `tags` → `[]` in metadata.
- Unmatched subdomain (no `ZendeskIntegration` row, or row exists but
  `is_active=False`) → `_find_matching_sources` returns `[]` →
  `{"status": "no_sources", ...}`, never a crash.
- `fetch_context` with missing/malformed `access_token`, unsafe `subdomain`,
  or any `httpx` exception → `{}`, never raises.
- Two orgs with different subdomains → only the matching org's source is
  returned (no cross-org leakage).

## Concerns / follow-ups for `ingestion-pull` / `ingestion-webhook`

1. Both entry points must build `event_data["subdomain"]` from the trusted
   `ZendeskIntegration.subdomain` column, not from arbitrary
   webhook/pull-response input, even though the adapter now has its own
   SSRF re-assertion as a second gate.
2. Both must build the `access_token` string as `f"{integration.email}:{decrypted_api_token}"`
   before it reaches `_process_event_for_source`'s `access_token` variable
   (currently that variable is only populated from the generic
   `integrations` table via `source.integration_id` — Zendesk's
   `ZendeskIntegration` is a separate table with no `integration_id` FK on
   `FeedbackSource`, so whichever aspect wires this up will need to extend
   `_process_event_for_source`'s access-token lookup with a
   `source.source_type == "zendesk"` branch, analogous to the
   `_find_matching_sources` branch added here. **This aspect does not do
   that wiring** — `fetch_context` is only exercised directly in this
   aspect's tests, not through the full `_process_event_for_source` →
   `fetch_context` path, since no `FeedbackSource.field_mapping` in the
   integration tests sets `include_context`/`include_author`. Flagging this
   explicitly since it's the one piece of "obvious next step" wiring the
   plan didn't call out as in-scope here and I didn't want to silently
   half-build it.
3. `PendingFeedback` has no `customer_email` column — a future
   review-flow aspect would need a schema change if the manual-review path
   needs the requester mapping preserved.

## Fix: review follow-up (multi-tenancy guard + cleanups)

A task review of the initial `zendesk` branch found a multi-tenancy defect
plus two trivial cleanups. Fixed via strict TDD, worker-service only.

### FIX 1 — cross-tenant fan-out on missing `subdomain` (Important)

`_find_matching_sources`'s `zendesk` branch only entered its
`ZendeskIntegration` lookup `if subdomain:`. When `provider_context.get("subdomain")`
was missing or falsy, control skipped straight to `return query.all()`,
returning **every** org's active zendesk `FeedbackSource` rows — a
cross-tenant leak.

**RED**: added `test_missing_subdomain_returns_empty_not_cross_tenant_fanout`
and `test_empty_string_subdomain_returns_empty_not_cross_tenant_fanout` to
`TestFindMatchingSources` in `tests/test_zendesk_adapter.py`, seeding two orgs
each with an active `ZendeskIntegration` + active zendesk `FeedbackSource`,
then calling `_find_matching_sources(db, "zendesk", {})` /
`{"subdomain": ""}`. Both failed before the fix (`result` contained both
orgs' sources instead of `[]`).

**GREEN**: added an early `if not subdomain: return []` guard at the top of
the `zendesk` branch in `src/tasks/source_events.py`, then removed the now-
redundant `if subdomain:` wrapper (dedented the existing lookup). The
present-but-unknown-subdomain behavior (`return []` when no
`ZendeskIntegration` row matches) is unchanged. Slack/Intercom branches were
not touched.

### FIX 2 — dead guard in SSRF subdomain check (Minor)

`_is_safe_subdomain` in `src/adapters/zendesk.py` had a
`if subdomain != subdomain.strip(): return False` guard before the regex
check. Removed it: `_SUBDOMAIN_LABEL_RE` (`^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$`)
is fully anchored and only permits alphanumerics/hyphens, so no string that
differs from its own `.strip()` (i.e. contains leading/trailing whitespace)
could ever match it — the guard was unreachable as a distinct code path.
Confirmed the existing `TestSubdomainValidation`/`fetch_context` SSRF
parametrized tests (including whitespace-adjacent malicious subdomains)
still pass after removal.

### FIX 3 — loose assertion in `test_handles_api_error_gracefully` (Minor)

Tightened `assert isinstance(result, dict)` to `assert result == {}` in
`tests/test_zendesk_adapter.py` (`test_handles_api_error_gracefully`,
`TestFetchContext`), matching `fetch_context`'s documented contract of
returning an empty dict (not just "some dict") on any `httpx` exception.

### Tests run

```
cd services/worker-service && source venv/bin/activate
pytest tests/test_zendesk_adapter.py -v
```
Result: `41 passed` (39 pre-existing + 2 new RED→GREEN tests for FIX 1).

```
pytest tests/ -q
```
Result: `608 passed, 23 failed` — the 23 failures are the pre-existing
baseline (anomaly-dispatch `MagicMock.__format__` and churn-calibration-task
failures, unrelated to zendesk/source_events). No new failures introduced.

### Files touched
- `services/worker-service/src/tasks/source_events.py` (FIX 1)
- `services/worker-service/src/adapters/zendesk.py` (FIX 2)
- `services/worker-service/tests/test_zendesk_adapter.py` (FIX 1 tests + FIX 3)
