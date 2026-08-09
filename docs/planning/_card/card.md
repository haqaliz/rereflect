# Card — `linear-webhook-secret-plaintext`

**Type:** bug (freeform — no GitHub issue)
**Branch:** `bug/linear-webhook-secret-plaintext`
**Worktree:** `.claude/worktrees/bug-linear-webhook-secret-plaintext`
**Opened:** 2026-08-09
**Traces to:** DEV-TRACKING.md:427-429 (follow-ups opened by `feat/integration-auth-tenancy-hardening`, all NOT STARTED)
**Picked by:** `rereflect-next` — the designated follow-up of the just-merged
`oauth-tokens-stored-plaintext` (PR #10, commit `737bbd5`): the last plaintext
credential in the system.

## The problem

`services/backend-api/src/models/linear_integration.py:19` stores `webhook_secret`
as a plain `String(255)` column. `services/backend-api/src/api/routes/linear_integration.py`
generates it with `secrets.token_urlsafe(32)` on webhook enable (lines ~394-435) and never
round-trips it through `encrypt_api_key`/`decrypt_api_key` — zero call sites (verified by
grep, 2026-08-09). Every other integration encrypts at rest: Zendesk, Jira, Asana, HubSpot,
Salesforce (API tokens) and now Slack + Intercom (OAuth tokens, PR #10). **Linear is the
only integration storing a credential in plaintext** (DEV-TRACKING.md:427-429).

The secret is an operator-pasted value that Linear's dashboard uses to HMAC-sign inbound
webhooks; whoever can read the `linear_integrations.webhook_secret` column can forge Linear
webhook deliveries (issue events, feedback ingestion, status changes).

## The fix (minimal slice)

- Encrypt on write: route the webhook-enable / connect-rotation paths in
  `linear_integration.py` through the existing Fernet `encrypt_api_key` helper (same
  pattern as Zendesk/Jira/Asana/HubSpot/Salesforce).
- Decrypt on read: exactly once, at the signature-verification call site. Verify whether the
  verifier lives in backend-api only, or also in worker-service (worker cannot import
  backend-api — needs a mirror like the OAuth-token decrypt mirrors from PR #10).
- Alembic backfill migration encrypting existing plaintext rows in place; must fail loudly
  (never silently leave rows plaintext) when the Fernet key is absent — follow the
  `c7d8e9f0a1b2` precedent (`oauth-tokens-encryption-at-rest`), chained to current head,
  single alembic head.
- Sweep-guard test asserting no integration stores a plaintext credential (mirror of
  `test_webhook_verifiers_fail_closed.py` / `test_worker_import_sweep.py` shape).
- Pin with tests: stored value is ciphertext (not the raw secret), decrypt-on-verify
  round-trips, existing plaintext rows migrate, single alembic head preserved.

## Scope guards (from DEV-TRACKING + the card, do not expand)

- **This is a security bug fix — no UI changes, no behavior changes** to the Linear
  webhook flow itself (HMAC verification semantics unchanged; the operator still pastes/
  copies the same secret from Linear's dashboard).
- **Do not** bundle `slack-email-signature-enforcement` (DEV-TRACKING.md:423-426) into this
  card; note it, keep the branch scoped.
- **Do not** bundle `oauth-state-in-process-dict` (DEV-TRACKING.md:571-576) into this card;
  note it, keep the branch scoped.
- The migration must not depend on application code at upgrade time beyond what Alembic can
  import safely (follow the repo's existing migration conventions — see the `c7d8e9f0a1b2`
  backfill precedent).
- Secret read sites must be audited so decrypting happens exactly once, at the call site,
  with no double-decrypt and no plaintext left in the DB after migration.
- Roadmap hygiene rule (DEV-TRACKING.md:497): "When closing work, correct the marker in the
  same commit" — the DEV-TRACKING follow-up entry must be marked FIXED on the branch that
  ships the fix.

## Related context

- Prior art — the encryption helpers: `encrypt_api_key`/`decrypt_api_key` (Fernet, key from
  env `LLM_ENCRYPTION_KEY`) in the Zendesk/Jira/Asana/HubSpot/Salesforce routes.
- Prior art — backfill migrations in this repo: `oauth-tokens-encryption-at-rest`
  migration `c7d8e9f0a1b2` (encrypts existing plaintext OAuth rows in place, fail-closed on
  missing key) and its tests; the `public_id` backfill (`n3o4p5q6r7s8`).
- Prior art — worker decrypt mirrors: PR #10 (`bug/oauth-tokens-stored-plaintext`, commits
  `2b94bc41`, `eafd308c`) — worker-local `_decrypt` mirrors because worker-service cannot
  import backend-api; pinned by `test_worker_import_sweep.py`.
- False-comment class: same as `models/integration.py:19` (corrected on PR #10) — if any
  Linear model comment claims encryption, correct it in the same commit.
