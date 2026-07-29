# Aspect spec — `webhook-auth-tenancy`

**Feature:** `integration-auth-tenancy-hardening`
**Covers:** FINAL SCOPE items **F1–F9** from `../prd.md`
**Excludes:** F10 (the GitHub Security Advisory — a release action, not code)

---

## Problem slice

Every unauthenticated write path into Rereflect either accepts unsigned requests by default, or
resolves the owning organization from an attacker-supplied field with no fallback, or both. This
aspect closes all of them in one change.

Three distinct defect shapes, each verified in code:

1. **Fail-open verifiers** — `return True` when the configuring secret is unset, which is the
   default state of every install: Slack (`source_webhooks.py:48-50`), Intercom (`:268-270`),
   Resend/email (`email_webhooks.py:45-47`).
2. **Unscoped tenancy fall-through** — `_find_matching_sources` narrows the query only when a
   payload-supplied discriminator is truthy; the base query has no `organization_id` predicate.
   Four branches affected (slack, intercom, email, webhook); only zendesk is guarded.
3. **A public default secret + body-supplied org** — `/api/internal/events/emit` compares a secret
   defaulting to the literal `"dev-secret"` with `!=`, then emits to `org_id` taken from the body.

## User outcome

A self-hosting operator's instance cannot be written to by an unauthenticated party, and no
request can cause a write attributed to an organization it does not belong to — regardless of
which environment variables the operator has or has not set.

An operator running Slack or email ingestion without a configured secret is **told**, in the UI
and in the logs, before that traffic is rejected in a later release.

---

## In scope

| Ref | Requirement | Fail-closed now? |
|---|---|---|
| F1 | `events_ws.py`: drop the `"dev-secret"` default, use `hmac.compare_digest`, reject when unset | **Yes** — zero production callers (PRD A7) |
| F2 | Intercom signature fails closed on empty/`None` secret | **Yes** — ingestion has never worked |
| F3 | Slack signature: shadow mode + operator visibility | No — live traffic |
| F4 | Resend/email signature: shadow mode + operator visibility | No — live traffic |
| F5 | `if not X: return []` on all four unguarded branches of `_find_matching_sources` | **Yes** — never legitimate |
| F6 | Invert `test_email_webhooks.py:367-378`; rewrite `test_intercom.py:294-325`; update `test_event_emitter.py` | — |
| F7 | `test_missing_*_returns_empty_not_cross_tenant_fanout` per branch, two orgs seeded | — |
| F8 | Create `worker-service/tests/test_source_events.py` | — |
| F9 | Document all four secrets in `.env.example`, `.env.prod.example`, `docs/SELF_HOSTING.md` | — |

### The shadow principle

Applied by evidence, not per-provider preference:

- **Ingestion demonstrably works today** (Slack, email) → shadow the *signature* flip: keep
  accepting, log a distinct greppable marker, surface an unconfigured badge in the UI. A later
  release flips it.
- **Ingestion has never worked** (Intercom) → fail closed immediately. No traffic to break.
- **No production caller** (`events/emit`) → fail closed immediately. Nothing to break.
- **Tenancy guards are never shadowed** for any provider. A missing discriminator is not
  legitimate traffic, and unlike a missing secret it cannot be an operator's configuration choice.

---

## Out of scope

- RBAC on `integrations.py` / `linear_integration.py`; the false comment at
  `models/integration.py:19`.
- Linear fail-closed helper + encrypting `webhook_secret` (needs a migration).
- Zendesk replay window; Jira/Asana/Linear replay caches.
- The generic webhook persisting `dict(request.headers)` into `event_data`.
- `JWT_SECRET`'s `"dev-secret-key"` default; OAuth-state TTL.
- The Intercom envelope-shape fix — **must not** precede F5 (see sequencing below).
- Deciding whether to wire up or delete `/api/internal/events/emit`.

---

## Acceptance criteria

**A. Tenancy (the core)**
1. `_find_matching_sources(db, "intercom", {})` returns `[]` with ≥2 orgs seeded, each having an
   active Intercom source. Same for `{"workspace_id": None}` and `{"workspace_id": ""}`.
2. Identical tests pass for `"slack"` (`team_id`), `"email"` and `"webhook"` (`source_id`).
3. Zendesk's existing behaviour is unchanged — its two regression tests still pass untouched.
4. A *correct* discriminator still resolves to exactly the owning org's sources (positive case,
   two orgs seeded, assert the other org's sources are absent).

**B. Authentication**
5. `POST /api/v1/webhooks/intercom/events` with no or an invalid `X-Hub-Signature` returns `401`
   and `queue_source_event` is not called — including when `INTERCOM_CLIENT_SECRET` is unset.
6. `verify_intercom_signature(body, sig, "")` and `(..., None)` both return `False`.
7. A signature valid for payload A, sent with payload B, is rejected (tampered-body test).
8. A non-ASCII `X-Hub-Signature` yields `401`, not a `TypeError`/500.
9. `POST /api/internal/events/emit` returns `403` when `INTERNAL_EVENTS_SECRET` is unset,
   regardless of the header sent; and when set, only a `compare_digest`-equal header is accepted.

**C. Shadow mode**
10. With `SLACK_SIGNING_SECRET` unset, a Slack event is still accepted (200) **and** a log record
    containing the agreed marker string is emitted. Same for email with
    `RESEND_INBOUND_WEBHOOK_SECRET` unset.
11. With the secret set, an invalid signature is rejected `401` for both.
12. The integrations list response reports signature-verification state per integration, and the
    Settings → Integrations UI renders an "unverified" badge for an affected integration.

**D. Non-regression**
13. Backend suite ≥ 4562 passing; worker suite ≥ 1417 passing (baselines measured on this branch,
    both venvs Python 3.12.13).
14. `alembic heads` prints exactly one head (no migration is added by this aspect).

---

## Dependencies & sequencing

**Hard constraint (from PRD §Sequencing):** the Intercom envelope-shape bug is the only thing
currently preventing full `FeedbackItem` injection. F5 must land **before** any adapter/envelope
work, in this branch or any other. Once F5 is in, that hazard is permanently neutralised.

**Internal ordering:** F1 is independent and can land first. F5 (tenancy) and F2 (Intercom
fail-closed) are the pair that must both be present before merge — either alone leaves the Intercom
chain exploitable from the other end. F3/F4 shadow work is independent of both. F9 last.

**Known test-suite collisions** — these tests assert current behaviour and will fail; each must be
updated deliberately, never worked around:
- `backend-api/tests/test_email_webhooks.py:367-378` — asserts `result is True` on missing secret.
- `backend-api/tests/test_intercom.py:294-325` — pins `workspace_id: None` as expected kwargs; and
  no payload fixture in the repo contains `app_id`.
- `backend-api/tests/test_event_emitter.py:148,166` — reads
  `os.getenv("INTERNAL_EVENTS_SECRET", "dev-secret")`, i.e. depends on the default being removed.

---

## Risks specific to this aspect

| Risk | Mitigation |
|---|---|
| Shadow mode never gets flipped and becomes permanent | The marker string is greppable and the follow-up is filed with the advisory (F10) |
| Removing the `events/emit` default breaks an undiscovered caller | Verified none exist across worker-service and analysis-engine; the endpoint is orphaned |
| Guarding `email`/`webhook` branches breaks their working callers | Both callers always set `source_id`; positive-case tests (criterion 4) prove resolution still works |
| Frontend badge work expands the branch | Kept to one boolean on an existing response plus one badge; no new endpoint |
