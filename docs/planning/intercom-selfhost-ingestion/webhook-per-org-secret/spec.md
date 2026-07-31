# Aspect Spec — `webhook-per-org-secret`

**Feature:** `intercom-selfhost-ingestion` · **PRD:** `../prd.md` (R4, K2) · **Date:** 2026-08-01

## Problem slice

The 1.0.0 changelog recorded this as unfixable:

> "A valid signature cannot identify a tenant here. `INTERCOM_CLIENT_SECRET` is a single
> global env var, unlike Zendesk's per-org `webhook_secret` which is looked up *by* the
> discriminator."

True while OAuth was the only connect path. **Token-paste dissolves it:** obtaining an
Access Token requires creating a Developer Hub app, and that app's Client Secret is exactly
the key Intercom signs `X-Hub-Signature` with. Stored per-org (encrypted, by
`token-paste-connect`), verification becomes per-tenant.

Secondary effect: a self-hoster with no OAuth app has no `INTERCOM_CLIENT_SECRET` at all, so
the fail-closed verifier rejected **every** delivery. That path now works.

## The ordering problem, and why parsing first is still fail-closed

The route must know the org to choose a secret, but `app_id` is in the not-yet-verified body.
So the body is parsed first and `app_id` used for exactly one purpose: **choosing which
candidate keys to try**. A forged `app_id` selects a secret the attacker cannot sign with, so
the HMAC fails and the request is rejected exactly as before. Nothing else is trusted
pre-verification.

Two consequences handled explicitly: the body is **size-bounded** (1 MiB) because an
unauthenticated caller can now make us parse JSON, and a parse failure returns **400**, not
a 500.

## In scope

`_intercom_candidate_secrets(db, workspace_id)` → per-org secrets for active integrations
with a stored secret, plus the global env var when set. Route verifies against each. Empty
list ⇒ reject.

`verify_intercom_signature` itself is **unchanged** — it is already a pure function keyed by
secret, so `tests/test_webhook_verifiers_fail_closed.py` stays green and Intercom stays off
`SHADOW_ALLOWLIST`.

## Out of scope

Auto-provisioning the Intercom webhook subscription. Resolved as **impossible**, not
deferred: subscriptions are Developer-Hub-only and *"you can only subscribe to webhooks now
via your Developer Hub — API-based subscription is not available."* Setup instructions are
the deliverable (`cleanup-and-docs`).

## Acceptance criteria

| # | Criterion |
|---|---|
| W1 | A per-org secret verifies a delivery with **no** global env var set |
| W2 | The global env var still verifies for OAuth orgs (D4) |
| W3 | A wrong signature is rejected |
| W4 | No candidate secret ⇒ 401 (fail closed) |
| W5 | A forged `app_id` naming another org cannot borrow that org's trust |
| W6 | An inactive integration's secret is not a candidate |
| W7 | Malformed JSON ⇒ 400, not 500 |
| W8 | Oversized body ⇒ 413 |
| W9 | `test_webhook_verifiers_fail_closed.py` green and unmodified |

## Honest limits

A single undecryptable stored secret is skipped with a warning rather than failing the whole
request, so one broken row cannot deny service to other tenants sharing a workspace id.
Trying multiple candidate keys is safe — a wrong key simply fails the HMAC — but it does mean
verification cost scales with the number of orgs sharing a workspace id, which is expected to
be one.
