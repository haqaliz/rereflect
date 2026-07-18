# Aspect spec — `asana-webhook`

Part of PRD `status-sync-realtime-mapping`. Depends on `status-writer-race-guard`.

## Problem slice & user outcome
An Asana task completion change is reflected on the linked feedback item's
`workflow_status` in **seconds** instead of ≤15 min. The 15-min poller is
retained as fallback.

## Asana-specific mechanics (differs from Jira/Zendesk)
Asana webhooks require a **handshake**: the first POST to our receiver carries an
`X-Hook-Secret` header; we must **echo it back** in the response `X-Hook-Secret`
header AND persist it. Subsequent event deliveries are signed
`X-Hook-Signature` = hex HMAC-SHA256(stored_secret, raw_body). Webhooks are
created per-resource (project/task) via the Asana API and identified by a webhook
**gid**. Events are compact change records (`resource.gid`, `action`, `field`)
and usually require a follow-up `GET /tasks/{gid}` to read `completed` (mirrors
the poller's per-task fetch).

## In scope
- **Model + migration:** add to `AsanaIntegration` a `webhook_secret` (Text,
  Fernet-encrypted, nullable), a `webhook_gid` (String, nullable — the Asana
  webhook gid) to track the active webhook, and a `webhook_url_token`
  (String(128), nullable, UNIQUE-indexed) — an unguessable
  `secrets.token_urlsafe(32)` value used as the inbound receiver's
  org-resolution key (see "Org resolution & security invariants" below).
  Alembic migration — confirm single-head with live `alembic heads`.
- **Create/enable route:** admin/owner endpoint that mints a fresh
  `webhook_url_token`, registers an Asana webhook for the operator's chosen
  resource (reuse the existing `getProjects`/workspace wiring) targeting
  `{BACKEND_URL}/api/v1/webhooks/asana/inbound/{webhook_url_token}`, and
  stores the returned webhook gid + the minted token; the handshake secret
  is captured on first delivery. Re-enabling always mints a NEW token and
  resets `webhook_secret` to `None` (a fresh handshake is required — the old
  URL stops resolving).
- **Receiver:** new `api/routes/asana_webhook.py`, prefix
  `/api/v1/webhooks/asana`, registered in `api/main.py`. Flow:
  1. **Org resolution:** resolve the integration by the unguessable
     `webhook_url_token` path segment (`{token}`, NOT the integration's
     guessable integer id — see security invariants below); no match (or a
     NULL/never-enabled token) → 401.
  2. **Handshake branch:** if `X-Hook-Secret` is present AND
     `integration.webhook_secret is None` → store it (encrypted) and echo
     it in the response header, 200. If a secret is ALREADY stored, this is
     rejected outright (401, secret untouched) — see the no-overwrite
     invariant below. (Fail-closed elsewhere: LLM_ENCRYPTION_KEY unset →
     401, not persisted.)
  3. **Event branch:** verify `X-Hook-Signature` HMAC-SHA256 over raw bytes
     against the resolved integration's stored secret; fail-closed 401 on
     mismatch or missing secret.
  4. Parse events; for each changed task resource, fetch `completed` via the
     Asana client (or read from payload if present) → `asana_category(completed)`
     (`done`/`new`).
  5. Look up `FeedbackAsanaTask` links; reconcile via the backend-api port:
     most-advanced category → `resolve_target_status(category,
     integ.status_mapping)` → race-safe apply with
     `metadata={"source":"asana","asana_completed":...,"asana_task_gid":...}`;
     upsert last-observed category.
  6. Return 200.
- Keep the Asana poll task unchanged (fallback).

### Org resolution & security invariants (sec review, CRITICAL fix)
A prior revision resolved the integration by the **guessable integer path id**
(`/inbound/{integration_id}`) and its handshake branch **unconditionally
overwrote** `integration.webhook_secret` on every request carrying an
`X-Hook-Secret` header. Together these let an unauthenticated attacker POST a
forged handshake to a small integer id, set a known secret for any active
org, and forge signed events afterward (cross-tenant status tampering + DoS
of the real webhook). Both are now closed, independently (defense in depth):

1. **Unguessable URL token.** The receiver resolves the integration by
   `webhook_url_token` (unique-indexed, `secrets.token_urlsafe(32)`), minted
   by `POST /webhook/enable` and embedded in the URL registered with Asana —
   never the integer `id`.
2. **No-overwrite gate.** The handshake branch may ONLY persist a secret when
   `integration.webhook_secret is None`. An org that already completed its
   handshake rejects ANY further `X-Hook-Secret` request with 401 and the
   stored secret is left untouched. The only legitimate way to re-handshake
   is `POST /webhook/enable`, which explicitly resets `webhook_secret` to
   `None` (and mints a new token) before registering a brand-new webhook.

## Out of scope
- Outbound webhooks. OAuth 2.0. Section-name / custom-field → `indeterminate`
  granularity (stays `completed`-based, category-level). Multiple workspaces.

## Acceptance criteria (testable)
- **Handshake:** first request with `X-Hook-Secret` and no stored secret →
  secret persisted (encrypted) + echoed in response header, 200, no reconcile.
- **No-overwrite gate (sec review):** a request with `X-Hook-Secret` against an
  org that already has a stored secret → 401, secret unchanged. Only a prior
  `POST /webhook/enable` call (which resets `webhook_secret` to `None`) makes
  a subsequent handshake succeed again.
- **Unguessable resolution (sec review):** the receiver resolves the org by
  `webhook_url_token`, never the integer `id`; an unknown token, or an
  integration with `webhook_url_token IS NULL` (never enabled), always 401s.
- Signature verify: valid `X-Hook-Signature` → processed; bad/missing → 401;
  missing stored secret (post-handshake) → 401 (fail-closed).
- A completion change on a linked task updates `workflow_status` per the merged
  mapping and writes exactly one `FeedbackWorkflowEvent` (race-safe).
- Stale/duplicate delivery → zero events (race guard).
- Migration test (mirror `test_asana_status_sync_migration.py`) + model test.
- New `tests/test_asana_webhook.py` covering handshake (including the
  no-overwrite gate and attacker re-handshake attempts), signature, reconcile,
  and the stale-delivery no-op (mirror `test_zendesk_webhook.py`).

## Dependencies & sequencing
- **Depends on** `status-writer-race-guard`.
- Independent of `jira-webhook`; can run in parallel.
- Reconcile port must stay consistent with the worker poller (shared
  `status_sync_core.py`).

## Open questions / risks
- **R2:** which resource to subscribe to (project vs workspace). v1: subscribe to
  the same project(s) already used for task creation; document the limitation.
- Asana requires the handshake response within ~10s — keep the handshake branch
  I/O-free (just persist + echo).
- Asana may re-send the handshake if it re-establishes the webhook; handle an
  idempotent secret update.
