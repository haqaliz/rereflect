# Understanding — `linear-webhook-secret-plaintext`

**Opened:** 2026-08-09 · **Branch:** `bug/linear-webhook-secret-plaintext`

## What the issue is really asking

Store Linear's `webhook_secret` encrypted at rest, like every other integration's
credential already is, and migrate existing plaintext rows. Nothing else: no UI, no
behavior change to the webhook flow.

## Verified facts (code, 2026-08-09)

- **Only Linear stores a credential in plaintext.** `models/linear_integration.py:19`
  `webhook_secret = Column(String(255), nullable=False)` — no encryption comment (unlike
  `access_token` at :13, "Fernet-encrypted OAuth token"). Zendesk/Jira/Asana webhook
  secrets and Slack/Intercom OAuth tokens all round-trip `encrypt_api_key`/`decrypt_api_key`.
- **Write sites (all backend, `routes/linear_integration.py`):** generate at :394
  (`secrets.token_urlsafe(32)`), sent plaintext to Linear's API at :402 (must stay
  plaintext there), stored raw at :423 (reconnect/update) and :435 (create).
- **Read site — exactly one, backend-only:** `routes/linear_webhook.py:68-69`
  (`_find_integration_by_secret` feeds `integration.webhook_secret` straight into
  `_verify_linear_signature` :33-54, HMAC-SHA256 hexdigest + `hmac.compare_digest`,
  fail-closed on empty/None). **Worker-service has zero Linear code** — no worker decrypt
  mirror needed (confirmed by grep).
- **No rotate-secret endpoint;** re-running OAuth connect overwrites the secret. Disconnect
  leaves the stale secret in the row (backfill will encrypt it too; harmless).
- **Current alembic head is exactly `c7d8e9f0a1b2`** (the OAuth-token encryption backfill,
  PR #10) — the new migration must chain from it; CI asserts single head.

## The pattern to copy (established, not invented)

- **Encrypt-on-write:** `jira_integration.py:651` — `encrypt_api_key` after the secret has
  been handed to the provider; `ValueError` (missing `LLM_ENCRYPTION_KEY`) → HTTP **422**
  with a clear message (mirror `integrations.py:909-915`).
- **Decrypt-on-read:** `jira_webhook.py:84-106` — `_find_integration_by_secret` filters
  `webhook_secret.isnot(None)`, decrypts **exactly once per candidate** inside try/except
  (`InvalidToken`/`ValueError` → log + continue, never 500). Corrupt/undecryptable secret
  is a no-match → 401.
- **Backfill migration:** `c7d8e9f0a1b2` — fail-closed `RuntimeError` with
  generate-a-key instructions when `LLM_ENCRYPTION_KEY` is missing; skips rows already
  prefixed `gAAAAA` (idempotent, never double-encrypts); online-only raw SQL;
  downgrade best-effort. Tested against in-memory SQLite via
  `MigrationContext`/`Operations` (`tests/test_oauth_token_backfill_migration.py`).
- **Sweep-guard:** `test_worker_import_sweep.py` already bans `src.utils` in the worker
  (not needed here — backend-only); a new sweep-guard for "no integration stores
  plaintext credentials" is in scope per the card.

## Decisions / open questions to settle in the PRD

1. **Column width:** Fernet ciphertext for a 32-char secret ≈ 140 chars — fits
   `String(255)`; Zendesk/Jira/Asana use `Text`. Recommend **no schema change** (keep
   `String(255)`): the data migration stays purely a row update. Alternative is widening
   for consistency — flagged, not required.
2. **Fixtures:** `test_linear_webhook.py:140`, `test_linear_oauth.py:67,460`,
   `test_linear_integration_rbac.py:57` insert raw secrets. After the fix the DB always
   holds ciphertext, so fixtures must store `encrypt_api_key(secret)` (golden contract:
   what's in the DB is what verification reads). Verify whether the backend test conftest
   already sets `LLM_ENCRYPTION_KEY` (the OAuth-token tests decrypt real Fernet, so
   likely yes).
3. **Missing key at verify time:** decrypt failure at `_find_integration_by_secret` = no
   match (401), matching Jira. **Missing key at callback time:** 422 (matching
   Slack/Intercom). Both already established; just applied here.
4. **Disconnect path:** does not null `webhook_secret` today; keep that behavior
   (out of scope to change), the backfill encrypts the stale value.

## Contradictions flagged

- None between the tracking entry and the code — DEV-TRACKING.md:427-429 describes exactly
  what the code does. The only "paper-over" trap: fixtures asserting raw-secret behavior
  would silently pass a plaintext-only verify path; the fix must make the **stored-value
  contract** explicit (ciphertext in DB) rather than tolerant of both.

## Affected areas

- `services/backend-api/src/api/routes/linear_integration.py` (write, 422 handling)
- `services/backend-api/src/api/routes/linear_webhook.py` (verify, decrypt-once)
- `services/backend-api/alembic/versions/*.py` (new backfill, chain from `c7d8e9f0a1b2`)
- `services/backend-api/tests/test_linear_webhook.py`, `test_linear_oauth.py`,
  `test_linear_integration_rbac.py` (fixtures), new migration tests, new sweep-guard test
- `DEV-TRACKING.md` (mark follow-up entry FIXED in the shipping commit)
- No worker-service, no frontend changes.
