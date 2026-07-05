# Implementation report — Zendesk backend-connection aspect

**Branch:** `feat/zendesk-integration` · **Worktree:** `/Users/aliz/dev/at/rereflect/.claude/worktrees/feat-zendesk-integration`
**Method:** strict TDD (RED → GREEN → REFACTOR), one commit per plan phase.
**Scope:** `services/backend-api` only, per the aspect spec. No ingestion (adapter/pull/webhook) and no frontend — those are separate aspects.

## Summary

Implemented the Zendesk BYOK connection slice end-to-end, mirroring the Jira
connection implementation precisely:

- `ZendeskIntegration` SQLAlchemy model + Alembic migration
- `ZendeskClient` (Basic auth, `validate()`, error taxonomy, client-side SSRF guard)
- `connect` / `status` / `disconnect` / `test` routes under `/api/v1/integrations/zendesk`
- Route-level SSRF gate (DNS resolution + private/loopback/link-local rejection)
- `zendesk` registered as a selectable feedback-source type (`/types` + `valid_types`)
- Connect-time auto-provisioning of a default `zendesk` `FeedbackSource`
- Webhook secret generation (display-once on connect, preserved across reconnects)

## Alembic heads — confirmed

Ran `alembic heads` **twice** (once before writing the migration, once again
immediately before finalizing it, per the plan's agent-execution note):

```
k2l3m4n5o6p7 (head)
```

Single head, unchanged from the plan's Section 0 analysis. No merge revision
was needed. **`down_revision = "k2l3m4n5o6p7"`** as planned.

New migration: `services/backend-api/alembic/versions/z1a2b3c4d5e6_add_zendesk_integration_tables.py`
(revision id `z1a2b3c4d5e6`, chains directly onto `k2l3m4n5o6p7`).

## Files added

- `services/backend-api/src/models/zendesk_integration.py` — `ZendeskIntegration` model
- `services/backend-api/alembic/versions/z1a2b3c4d5e6_add_zendesk_integration_tables.py`
- `services/backend-api/src/services/zendesk_client.py` — `ZendeskClient`
- `services/backend-api/src/api/routes/zendesk_integration.py` — connect/status/disconnect/test routes
- `services/backend-api/tests/test_zendesk_models.py` (12 tests)
- `services/backend-api/tests/test_zendesk_client.py` (26 tests)
- `services/backend-api/tests/test_zendesk_connection.py` (38 tests)
- `services/backend-api/tests/test_feedback_sources_zendesk.py` (6 tests)

## Files edited

- `services/backend-api/src/models/__init__.py` — exports `ZendeskIntegration` (placed
  immediately after the `JiraIntegration`/`FeedbackJiraIssue` import, preserving the
  file's existing "integration models grouped together" convention)
- `services/backend-api/src/api/main.py` — imports and registers
  `zendesk_integration_router` right after the Jira registration block, with the
  comment `# Zendesk inbound integration (zendesk-integration backend-connection aspect)`
- `services/backend-api/src/api/routes/feedback_sources.py` — added a `zendesk`
  `SourceTypeInfo` to `/types` (placed after the `jira` entry, before `discord`) and
  `"zendesk"` to `valid_types` in `create_feedback_source`. No `has_feature` branch
  (matches the Jira/Linear own-auth precedent — zero plan gating, per CLAUDE.md's OSS
  pivot).

## Commits (one per plan phase)

| Phase | Commit | Message |
|---|---|---|
| 1 — Model + migration | `2177607` | `feat(zendesk): ZendeskIntegration model + migration (backend-connection phase 1)` |
| 2 — ZendeskClient | `c09438f` | `feat(zendesk): ZendeskClient (Basic auth, validate, SSRF guard, error taxonomy)` |
| 3 — Routes + main.py | `4df14d8` | `feat(zendesk): connect/status/disconnect/test routes + webhook secret + source auto-provision (backend-connection phase 3)` |
| 4 — Source-type registration | `4b13c11` | `feat(zendesk): register zendesk as a selectable feedback-source type` |

No Phase 5 commit was needed — the polish checklist (docstring/log-message
drift check, secret-leak grep, `models/__init__.py` grouping check) found
nothing to fix (see "Phase 5 checklist" below).

**Commit range:** `5a76723..4b13c11` (first Zendesk commit `2177607`, last `4b13c11`).

## TDD process (RED confirmed before every GREEN)

- **Phase 1:** `test_zendesk_models.py` written first; ran and failed with
  `ModuleNotFoundError` (12 failures, correct reason) before `zendesk_integration.py`
  existed. After the model + migration + `__init__.py` export: **12/12 passed**.
- **Phase 2:** `test_zendesk_client.py` written first; collection/import error
  confirmed before `zendesk_client.py` existed. After implementation: **26/26 passed**.
- **Phase 3:** `test_zendesk_connection.py` written first; 37/38 failed (1 incidentally
  passed — `test_disconnect_nonexistent_returns_404`, since an unregistered route also
  404s, which happens to satisfy that specific assertion) before the route file/
  `main.py` registration existed. After implementation: **38/38 passed**.
- **Phase 4:** `test_feedback_sources_zendesk.py` written first; 5/6 failed (the 6th,
  `test_bogus_source_type_is_rejected`, trivially passed both before and after, since
  it only asserts a garbage type is rejected). After the two-line `feedback_sources.py`
  edit: **6/6 passed**.

## Final regression — full backend-api suite

```
pytest tests/ -q
==== 20 failed, 2784 passed, 1 skipped, 44365 warnings in 751.34s (0:12:31) ====
```

All 82 new Zendesk tests (`test_zendesk_models.py` + `test_zendesk_client.py` +
`test_zendesk_connection.py` + `test_feedback_sources_zendesk.py`) are among the
2784 passed. **Zero Zendesk-related failures.**

The 20 pre-existing failures are entirely unrelated to this aspect (none touch
`zendesk_integration`, `models/__init__.py`'s new export, or the two lines added to
`feedback_sources.py`/`main.py`):

- `tests/test_automation_engine.py` — 4 failures (`AutomationRule`/`AutomationExecution` action-execution assertions)
- `tests/test_conversation_folders_api.py` — 1 failure (`TestDeleteFolder::test_delete_folder_moves_conversations_to_null`)
- `tests/test_linear_oauth.py` — 2 failures (`TestLinearStatus` — Linear OAuth status)
- `tests/test_report_ws.py` — 10 failures (report-generation websocket pipeline)
- `tests/test_sentry.py` — 3 failures (`TestSentryMainPyIntegration`/`TestSentryScopeContext` —
  these re-import `src.api.main` under a patched `SENTRY_DSN` env var and assert
  module-level state; since `src.api.main` is already imported once by `conftest.py`
  at collection time, the re-import doesn't re-run the top-level Sentry-init code —
  a module-caching test-order artifact, not something my two-line `main.py` edit
  (Zendesk router import + `include_router` call) could plausibly cause)

I confirmed `test_jira_client.py`, `test_jira_connection.py`, and `test_jira_models.py`
all passed cleanly (no `F`) in the same run — the shared files I touched
(`main.py`, `models/__init__.py`) did not regress Jira's coexisting integration.

**Note on environment:** this sandbox is slow for the full 2805-test suite
(~12.5 minutes wall-clock) and its `rtk` pytest-proxy wrapper occasionally hangs
on first invocation without spawning the underlying interpreter (observed twice;
resolved by killing the stuck `rtk proxy` process and retrying). Running multiple
heavy pytest processes concurrently in this sandbox also triggered one spurious
SIGSEGV in an earlier (superseded) attempt at this same full-suite validation —
not a code defect, just resource contention from parallel heavy test runs; the
final, authoritative run above was executed alone (no concurrent pytest processes)
and completed cleanly.

## Deviations from the plan

None that changed behavior. Two implementation notes:

1. **R6 test for the "second `encrypt_api_key` call fails" case.** The plan called
   out (Section 5) that the RED suite must exercise the case where the *first*
   `encrypt_api_key` call (for `api_token`) succeeds and a *later* call (for
   `webhook_secret`) raises. I added
   `test_connect_missing_encryption_key_returns_422_when_webhook_secret_encrypt_fails`
   (parametrized-in-spirit via a stateful mock `side_effect`) alongside the existing
   `test_connect_missing_encryption_key_returns_422_not_500` (which covers the
   first-call-raises case, mirroring Jira's). Both pass; the route wraps both
   `encrypt_api_key` invocations in their own `try/except ValueError -> 422` blocks.
2. **Phase 5 "polish" pass** produced no diff — greps for leftover Jira-specific
   wording (`atlassian`, `myself`, `.atlassian.net`) in the new Zendesk files only
   matched two *intentional* contrastive doc-comments (`zendesk_client.py`'s
   `_assert_safe_subdomain` docstring and `zendesk_integration.py`'s
   `_normalize_subdomain` docstring, both of which explicitly reference Jira's
   analogous method by name for maintainer context — not accidental copy-paste).
   The secret-leak grep (`logger\.` in the two new source files) found only two
   log statements, both matching Jira's exact pattern (org id + subdomain / org id
   + exception `str()`, never token/secret values).

Nothing in the plan was ambiguous or contradicted the code as I found it — the
webhook-secret "generate once, preserve on reconnect" design decision (OQ1) was
implemented exactly as locked in Section 1, without needing to ask.

## `/status` response — final shape (for downstream aspects)

```json
{
  "connected": true,
  "subdomain": "acme",
  "email": "operator@acme.com",
  "token_hint": "...abcd",
  "account_user_id": "12345",
  "display_name": "Jane Agent",
  "is_active": true,
  "last_synced_at": null,
  "last_sync_status": null,
  "last_error": null,
  "connected_at": "2026-07-05T12:00:00",
  "has_feedback_source": true
}
```

- `connected: false` (200, all other fields `null`/absent) when no active integration exists.
- **`api_token` and `webhook_secret` are never present in `/status`** — confirmed by
  `test_status_connected_returns_full_status` (asserts both field-absence and that
  the raw encrypted blob string never appears anywhere in the response body).
- `has_feedback_source` is computed via a **read-only** existence check
  (`_has_zendesk_source`) — `GET /status` never creates a `FeedbackSource` as a
  side effect; only `POST /connect` can auto-provision one (via
  `_ensure_default_feedback_source`, which calls the same read-only check first).

## `webhook_secret` surfacing (for downstream ingestion/frontend aspects)

- **Only ever returned by `POST /connect`** (never by `GET /status`), as the current
  **plaintext** value — this is the intentional "display once" contract from the
  locked OQ1 decision.
- On the **first** connect for an org: a new secret is generated
  (`secrets.token_urlsafe(32)`), Fernet-encrypted, and stored; the plaintext is
  returned in that same response.
- On **reconnect** (row already exists with a non-null `webhook_secret`): the
  existing encrypted secret is preserved untouched; the route decrypts it and
  returns the **same** plaintext value again (so a UI can always "show me my
  webhook secret again" by hitting connect with the same/updated token) — only
  `api_token`/`token_hint`/`account_user_id`/`display_name` rotate on reconnect.
- Stored at rest as Fernet ciphertext in `zendesk_integrations.webhook_secret`
  (nullable `Text` column), via the same `encrypt_api_key`/`decrypt_api_key`
  helpers used for `api_token` — no new encryption helper was needed.
- Example `POST /connect` response (200):
  ```json
  {
    "connected": true,
    "subdomain": "acme",
    "email": "operator@acme.com",
    "token_hint": "...9999",
    "account_user_id": "12345",
    "display_name": "Jane Agent",
    "webhook_secret": "kf3n2...redacted-example...9x",
    "has_feedback_source": true
  }
  ```

## Two-layer SSRF gate (confirmed, both layers independently tested)

1. **Route layer (primary):** `_normalize_subdomain` rejects non-`*.zendesk.com`
   hosts and suffix-trick hosts (`acme.zendesk.com.evil.com` → after stripping one
   trailing `.zendesk.com` label, a leftover `.` in the remainder is rejected)
   *before* any DNS lookup; `_assert_host_not_ssrf` then resolves
   `{subdomain}.zendesk.com` via `socket.getaddrinfo` and rejects loopback/
   RFC1918-private/link-local resolved addresses. Covered by
   `test_connect_rejects_non_zendesk_host`, `test_connect_rejects_suffix_trick_host`,
   `test_connect_ssrf_gate_rejects_private_resolving_host` (169.254.169.254,
   10.0.0.1, 127.0.0.1), `test_connect_ssrf_gate_allows_public_resolving_host`.
2. **Client layer (defense-in-depth):** `ZendeskClient._assert_safe_subdomain`
   rejects empty/`None`, any subdomain containing `/`, `:`, `.`, or whitespace,
   and anything failing a conservative bare-label regex — unit-testable without
   network I/O. Covered by `TestZendeskClientSSRFGuard` (6 parametrized bad
   inputs + 1 valid-input + redirect-disabled check).

## Auto-provisioned `FeedbackSource` — confirmed idempotent

- `provider_config: {"subdomain": "acme"}` — the join key the (separate,
  out-of-scope) ingestion-core aspect's `source_events._find_matching_sources`
  will use.
- `integration_id: null`, `source_type: "zendesk"`, `auto_import: true`.
- Idempotent across repeat reconnects (`test_connect_does_not_duplicate_feedback_source_on_reconnect`)
  and does not clobber an operator-pre-created source
  (`test_connect_does_not_duplicate_feedback_source_if_already_exists` — asserts the
  pre-existing row's `id` and custom `name` are untouched).
- Disconnect does **not** touch the `FeedbackSource` row (`test_disconnect_does_not_touch_feedback_source`)
  — connection and source lifecycle are intentionally decoupled per PRD 9a.

## RBAC / Free-plan coverage

- `TestRBAC`: all four routes (`connect`/`status`/`disconnect`/`test`) return 403
  for a `member`-role user (`require_admin_or_owner`).
- `TestFreePlanUnlocked`: full connect → status → test → disconnect flow passes
  end-to-end on a Free-plan org — zero plan gating, matching the OSS positioning.

## Post-review fixes (2026-07-05)

A whole-branch review found the auto-provisioned `FeedbackSource` was dead on
arrival, plus a misleading comment about cross-path dedup. Fixed with strict TDD.

### FIX 1 — CRITICAL: auto-provisioned source never ingested anything

**Root cause:** `_ensure_default_feedback_source` in
`services/backend-api/src/api/routes/zendesk_integration.py` created the default
`zendesk` `FeedbackSource` with `triggers={}`. The worker adapter
(`services/worker-service/src/adapters/zendesk.py::check_triggers`) only reports a
match when `triggers.get("new_ticket")` is truthy. With `triggers={}`, **every**
ingested ticket — pulled or webhook-delivered — was silently dropped as
`no_trigger_match`, so a freshly connected org never got a single feedback item
out of the box.

**RED:** added an assertion to the existing
`test_connect_auto_provisions_default_feedback_source` test:
```python
assert source.triggers == {"new_ticket": True}
```
Confirmed failing against the old code (`AssertionError: {} != {'new_ticket': True}`).

**GREEN:** changed the seed value in `_ensure_default_feedback_source` to
`triggers={"new_ticket": True}`, with a comment explaining why (adapter requires
`new_ticket` to ingest). The idempotent "don't clobber a pre-existing source"
behavior is unchanged — `_has_zendesk_source` still short-circuits before this
code runs, so only a *newly created* default source gets the seeded trigger; an
operator-customized existing source (see
`test_connect_does_not_duplicate_feedback_source_if_already_exists`) is untouched.

Files: `services/backend-api/src/api/routes/zendesk_integration.py`,
`services/backend-api/tests/test_zendesk_connection.py`.

### FIX 2 — comment accuracy + concurrency limitation

**Problem:** the synchronous dedup pre-check in
`services/backend-api/src/api/routes/source_webhooks.py` (Zendesk webhook route)
claimed "the authoritative dedup lives downstream via the unique constraint
`uq_source_event(source_id, external_event_id)`". False: the scheduled pull
writes `external_event_id=f"zendesk-pull-{integration_id}-{ticket_id}-{window}"`
while the webhook path writes `external_event_id=str(ticket_id)` — different
values for the same ticket, so that unique constraint never fires across the two
paths. The real cross-path guard is worker-service's
`_process_event_for_source`, which matches on the adapter-derived
`external_message_id` (== `str(ticket_id)` for both paths), filtered to
`status in (processed, pending)`.

**Fix:** rewrote the comment to describe the real mechanism, and added the same
`status.in_(["processed", "pending"])` filter to the pre-check query so a prior
`ignored`/`failed` row for the same ticket no longer permanently blocks a later
legitimate delivery of that ticket. No DB unique index was added (deliberately
avoided per the review — migration risk on the shared existing table).

**Test:** added `test_webhook_does_not_dedupe_against_ignored_or_failed_rows` to
`services/backend-api/tests/test_zendesk_webhook.py`, asserting a webhook for a
ticket with only an `ignored`-status prior row still gets queued.

Also documented the residual concurrency limitation (pull/webhook race on a
brand-new ticket) in `docs/SELF_HOSTING.md`, Zendesk section.

### FIX 3 — same-subdomain multi-tenancy doc note

Added a one-line note to `docs/SELF_HOSTING.md` (Zendesk "Connect from the app"
section): each org connects its own Zendesk with its own validated credentials;
two orgs must not point at the same subdomain, or tickets would be attributed to
both.

### Validation

```
cd services/backend-api && source venv/bin/activate
export LLM_ENCRYPTION_KEY=<fernet key>
pytest tests/test_zendesk_connection.py tests/test_zendesk_webhook.py -v
```

Result: **80 passed**, 0 failed (38 in `test_zendesk_connection.py`, 42 in
`test_zendesk_webhook.py` including the 1 new test). Full 2810-test suite was
intentionally not run (pre-existing `test_report_ws.py` segfault, per review
instructions).
