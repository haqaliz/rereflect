# Card — chore/backend-security-smalls (freeform, no GitHub issue)

Source: three recorded DEV-TRACKING items: P3 `oauth-state-in-process-dict`
(:654-661), the S1 generic-webhook follow-up recorded by #19 (:435), and
`events-emit-wire-up-or-delete` (:463). Branch `chore/backend-security-smalls`,
worktree `.claude/worktrees/backend-security-smalls`.

## Items (all small, all backend-api)

1. **P3 — `oauth-state-in-process-dict` (bug).** `oauth_states`
   (`services/backend-api/src/api/routes/integrations.py:39`) is a module-level
   Python dict with no TTL and no Redis/DB backing. OAuth callbacks fail
   intermittently on any multi-replica backend (the callback may land on a different
   process than the one that issued the authorize URL); also an unbounded in-memory
   store (entries never expire). Fix: move to a durable/consistent store with TTL
   (Redis with expiry, or a DB row) — follow the repo's existing Redis/cooldown
   conventions.
2. **S1 — generic-webhook per-source `secret_token` fail-open**
   (source_webhooks.py:270-274): `handle_generic_webhook` verifies the per-source
   `secret_token` only `if secret_token:` — a generic source with no secret
   configured is accepted unsigned. Decide the honest posture: (a) require
   secrets on new generic sources (default-deny at creation), (b) document the
   capability-URL model + warn, or (c) reject unsigned deliveries when the URL is
   not... — the dig resolves which; the capability-URL design may be intentional.
3. **`events-emit-wire-up-or-delete`.** `POST /api/internal/events/emit` has no
   production caller (the intercom work found it "needs no integration configured…
   no production caller, so failing it closed was migration-free"). Wire it up or
   delete it — the dig decides; likely delete (no caller since forever).

## Caveats (carried into the PRD)

- **P3 is a real correctness bug** on multi-replica; the fix must keep the OAuth
  flows (Slack + Intercom) working with state that survives process boundaries —
  Redis TTL is the house pattern (DB1 cooldowns), but OAuth state is short-lived
  (minutes) and high-churn; verify the Redis config helper (`get_redis_url(db)`).
- **S1 posture is a product decision, not just a code flip** — generic webhooks are
  a documented feature; "no secret" may be the intended capability-URL model. The
  dig must read the SELF_HOSTING/docs for generic webhooks before deciding.
- **events-emit deletion must be migration-free** (the intercom work already
  established that) and must not break the internal-events routing that webhook
  dispatchers use — verify no hidden caller (grep the whole repo incl. worker).

## Deliverables (proposed, refine in PRD)

1. P3: OAuth state in Redis with TTL (or an equivalent durable fix), tests for
   cross-process + expiry semantics.
2. S1: the honest posture (require-secret on new sources, or documented
   capability-URL model), tests.
3. events-emit: wire or delete, with the sweep proof.
4. DEV-TRACKING markers for all three.

## Out of scope (guardrails)

- No plan gates; no migration unless the fix requires one (prefer none).
- P7 (provider duplication) and intercom-oauth-path-retirement stay deferred.
