# Understanding — `oauth-tokens-stored-plaintext`

**Phase 2 dig output** · branch `bug/oauth-tokens-stored-plaintext` · 2026-08-09

## What the bug really is

Slack and Intercom OAuth flows in `services/backend-api/src/api/routes/integrations.py`
store the provider access token **in plaintext** in the generic `integrations` table
(`Integration.oauth_access_token`, a plain `Text` column). Every newer BYOK integration
(Zendesk, Jira, Asana, HubSpot, Salesforce) encrypts with Fernet (`encrypt_api_key`/
`decrypt_api_key` in `src/utils/encryption.py`, key from `LLM_ENCRYPTION_KEY`). The OAuth
paths were never migrated onto that pattern.

**Real-world consequence:** on any self-hosted install, a live Slack/Intercom token —
write access to the workspace/helpdesk — sits in plaintext in the DB. The repo's own
users named privacy/BYOK/no-telemetry as the hook (DEV-TRACKING "No build required",
four of seven comments); this is the class of gap that would poison that positioning.

## Verified facts (code-confirmed, not inferred)

**Write sites (plaintext today):**
- `routes/integrations.py:912` — `slack_oauth_callback`, `oauth_access_token=access_token` with a literal `# In production, encrypt this!` comment
- `routes/integrations.py:1089` — `intercom_oauth_callback`, no comment

**Read sites that must decrypt (exactly once, at the call site):**
- backend: `integrations.py:683` (`test_slack_integration` → `send_slack_message_oauth`), `feedback_sources.py:621` (truthiness guard) + `:637` (Bearer header, `list_slack_channels`)
- worker (no encryption module exists there — local `_decrypt` mirror required): `alerts.py:445`, `source_events.py:314` (Slack + Intercom `fetch_context`), `anomaly.py:270`, `notification_dispatch.py:104` + `:701`

**Truthiness traps:** Fernet ciphertext is a non-empty string, so every `if not
integration.oauth_access_token` / `and integration.oauth_access_token` guard keeps
passing. Nothing breaks loudly — instead the send paths would post **ciphertext as the
Bearer token** → 401 from the provider. Decrypt must happen at the send sites; guards
stay as-is (ciphertext is truthy).

**Worker precedent (the pattern to copy):** module-local `_decrypt(token)` with inline
`from cryptography.fernet import Fernet` + `os.environ["LLM_ENCRYPTION_KEY"]`
(zendesk_sync.py:80, hubspot_sync.py:45, salesforce_sync.py:80 …). zendesk_sync also
defines the R6 error contract for the worker: missing key → `{"status": "error",
"reason": "missing_encryption_key"}`, no retry.

**Backfill migration:** chained to head `a9b8c7d6e5f4` (currently the single head; CI
asserts exactly one). Repo convention: **zero migrations import `src.` modules**; the
one existing Fernet migration (`h1i2j3k4l5m6:122`) reads `os.environ` and imports
`cryptography.fernet` inline — but it **silently fell back to plaintext** when the key
was missing, which a security backfill must NOT do. `LLM_ENCRYPTION_KEY` is available at
migration time in production (Dockerfile runs `alembic upgrade head` in-container with
the compose-injected key) and in CI (dummy key set before upgrade; clean DB → zero
rows). Locally, `alembic/env.py` does not `load_dotenv()` — operators must export it.
Offline mode (`--sql`) cannot run a Python-transform backfill (all repo backfills are
online-only).

## Contradictions surfaced (flagged, not papered over)

1. **The false comment is already fixed.** `models/integration.py:19-25` no longer
   claims "encrypted at application level"; it now states plainly that tokens are
   plaintext, names the encrypting integrations, references this exact tracking entry,
   and says "Do not restore the old comment without doing the encryption." The card's
   "correct the false comment" item is therefore **already done** (DEV-TRACKING.md:505-507
   says the same). The fix no longer includes that step.
2. **Latent sibling defect found in the dig:** `worker-service/src/tasks/intercom_sync.py:76-80`
   `_decrypt` does `from src.utils.encryption import decrypt_api_key` — a module that
   does **not exist in the worker image**. Same family as the P0/P0b dead-import bugs;
   masked because tests monkeypatch `_decrypt`. Affects the *dedicated* Intercom
   token-paste table (`IntercomIntegration`), **not** the generic `integrations` table —
   out of scope for this card, but must be recorded as a follow-up in DEV-TRACKING so
   it is not re-discovered the hard way.
3. **`oauth_refresh_token` / `oauth_expires_at` are dead columns** for these providers
   (never written by either flow; zero read sites). Out of scope — do not touch.

## Open questions for the PRD

- **Fail-closed migration vs. operator who never set `LLM_ENCRYPTION_KEY`:** the app
  otherwise runs fine without it (integration saves 422). Fail-closed means `alembic
  upgrade head` **aborts the deploy** for those installs. Card mandates fail-loud;
  SELF_HOSTING.md callout needed. (Not a question of whether — how loud, and where
  documented.)
- **Already-encrypted rows:** a reconnect post-deploy rotates the token and would write
  ciphertext. The backfill must skip rows already Fernet-encrypted (prefix `gAAAAA` or
  try-decrypt-and-skip) — no double encryption.
- **`downgrade()`:** repo precedent is best-effort decrypt with `except Exception: pass`
  (h1i2j3k4l5m6:194-224). Mirror it or document destructive? (Precedent says mirror.)
- **Tests to pin:** `test_intercom.py:199` asserts stored token equals the raw
  `"xyztoken123"` — must flip to "ciphertext + decrypt round-trip". Any equivalent Slack
  callback assertion. Worker send-path tests must assert the decrypted token reaches the
  Bearer header (not ciphertext) — i.e. a regression test that would have caught the
  truthiness trap.

## Affected areas

| Area | Service | Files |
|---|---|---|
| OAuth write paths | backend-api | `src/api/routes/integrations.py` (912, 1089) |
| Backend read sites | backend-api | `integrations.py:683`, `feedback_sources.py:621,637` |
| Worker read sites | worker-service | `alerts.py:445`, `source_events.py:314`, `anomaly.py:270`, `notification_dispatch.py:104,701` |
| Backfill | backend-api | new `alembic/versions/*_encrypt_integration_oauth_tokens.py`, head `a9b8c7d6e5f4` |
| Tests | both | `test_intercom.py:199` flip; new encryption/decrypt/migration tests |
| Docs | repo | `SELF_HOSTING.md` fail-closed callout; DEV-TRACKING marker → FIXED in same commit |
