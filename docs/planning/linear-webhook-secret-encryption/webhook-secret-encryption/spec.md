# Spec — Webhook-secret encryption (Linear)

**Aspect:** `webhook-secret-encryption`
**PRD:** `docs/planning/linear-webhook-secret-encryption/prd.md`
**Branch:** `bug/linear-webhook-secret-plaintext`

## Problem slice and user outcome

Linear's `webhook_secret` (the HMAC key for inbound webhook auth) is the last plaintext
credential in the system. After this aspect: it is Fernet-encrypted at rest on every path
(write, verify, existing rows via backfill), exactly like Zendesk/Jira/Asana webhook
secrets and Slack/Intercom OAuth tokens. Operator outcome: nothing visible changes; an
upgrading install keeps verifying webhooks with zero reconnection.

## In-scope requirements (from PRD must-haves)

1. **Encrypt on write** — `routes/linear_integration.py` OAuth-callback upsert stores
   `encrypt_api_key(webhook_secret)` at both write sites (:423 update, :435 create);
   encryption happens after the plaintext was handed to Linear's `create_webhook` API
   (:402); missing `LLM_ENCRYPTION_KEY` → HTTP 422 with a clear message (mirror
   `integrations.py:909-915`).
2. **Decrypt on read, exactly once** — `routes/linear_webhook.py::_find_integration_by_secret`
   decrypts each candidate inside try/except (`InvalidToken`/`ValueError` → log + continue,
   no-match → 401), mirroring `jira_webhook.py:84-107`; the undecryptable case logs a
   **warning** naming the integration id so a changed-key failure is diagnosable; **no
   plaintext fallback** — the DB contract is "always ciphertext".
3. **Backfill migration** — new Alembic migration chained to sole head `c7d8e9f0a1b2`:
   encrypts existing plaintext `linear_integrations.webhook_secret` rows in place;
   fail-closed `RuntimeError` (generate-a-key instructions) when `LLM_ENCRYPTION_KEY`
   unset; skips `gAAAAA`-prefixed rows (idempotent); best-effort downgrade; online-only,
   no schema change (`String(255)` fits Fernet, ~140 chars).
4. **Tests (RED-first)** — ciphertext-at-rest + round-trip on callback; verify accepts
   ciphertext-stored secrets; missing key at callback → 422; corrupt/undecryptable secret
   at verify → 401 (and the warning log); migration contract tests mirroring
   `tests/test_oauth_token_backfill_migration.py`; fixtures updated to the ciphertext
   contract; sweep-guard test.
5. **Docs/tracking** — DEV-TRACKING.md `linear-webhook-secret-plaintext` entry marked
   FIXED in the shipping commit; model comment on `linear_integration.py:19` stating
   Fernet-at-rest.

## Out-of-scope boundaries

- No UI changes; no rotate-secret endpoint; no disconnect-clears-secret behavior change.
- Not `slack-email-signature-enforcement`; not `oauth-state-in-process-dict`.
- No worker-service changes (worker has zero Linear code); no schema change.
- No plaintext-tolerant fallback at the verify boundary (deliberately).

## Acceptance criteria

- `POST /api/v1/integrations/linear/callback` stores a `gAAAAA…`-prefixed value in
  `webhook_secret` (never the raw secret); decrypt round-trips; missing key → 422.
- `POST /api/v1/webhooks/linear/inbound` verifies correctly when the DB holds ciphertext;
  corrupt ciphertext or wrong key → 401 with a warning log naming the integration.
- Migration: plaintext rows encrypted + round-trip; already-Fernet rows unchanged;
  NULL/empty untouched; missing key raises and leaves rows untouched; downgrade
  best-effort; `alembic heads` prints exactly one head.
- Every Linear test fixture that represents stored DB state holds ciphertext.
- Sweep-guard test fails if a future integration route writes a credential column
  (`webhook_secret` / `oauth_access_token` / `signing_secret`) without the encrypt helper.
- Backend suite green: `pytest tests/ -v` in `services/backend-api`.

## Dependencies and sequencing

1. Decrypt-on-verify + fixture contract (read path — establishes the DB contract at the
   boundary tests exercise).
2. Encrypt-on-write + callback tests (write path).
3. Backfill migration + contract tests (data path; runs at startup via
   `main.py::run_migrations`, closing the plaintext window before traffic).
4. Sweep-guard + model comment + DEV-TRACKING marker.

Sequencing note: merged code must deploy with the migration running before any Linear
webhook traffic — `main.py:188-206` runs `alembic upgrade head` at startup, so this holds
by construction; the fail-closed migration aborts startup loudly if the key is missing.

## Open questions or risks

- **Fixture granularity:** `test_linear_oauth.py:67,:460` and
  `test_linear_integration_rbac.py:57` fixtures feed `/status`/plan-gating tests that
  never hit verification — updated to ciphertext anyway for the uniform invariant (cheap;
  requires the key only at fixture time via `patch.dict`).
- **Verify tests need the key in env:** decrypt reads `os.environ` lazily — the
  verification tests must run with `LLM_ENCRYPTION_KEY` set (module-level autouse fixture
  with `patch.dict` in `test_linear_webhook.py`; the repo's per-test `patch.dict` pattern
  in the other files).
- **Startup break window:** between merge and migration run, legacy plaintext rows are
  undecryptable → 401. Migration runs at startup before traffic, so the window is
  milliseconds; acceptable, no fallback (per PRD).
