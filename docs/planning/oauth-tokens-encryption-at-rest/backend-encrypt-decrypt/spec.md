# Spec — Backend encrypt/decrypt (write sites + backend read sites)

**Aspect:** `backend-encrypt-decrypt` · PRD: `oauth-tokens-encryption-at-rest`

## Problem slice

Slack and Intercom OAuth callbacks store raw tokens (`integrations.py:912`, `:1089`);
the backend read sites (`test_slack_integration`, `list_slack_channels`) consume them
raw. This aspect encrypts on write and decrypts on read in backend-api only.

## In scope

- R1: `encrypt_api_key(access_token)` at `integrations.py:912` and `:1089`; missing
  `LLM_ENCRYPTION_KEY` → HTTP 422 with actionable message (`try/except ValueError`
  pattern from `zendesk_integration.py:414-424`).
- R2 (backend half): decrypt at `integrations.py:683` (`test_slack_integration`) and
  `feedback_sources.py:621`+`:637` (`list_slack_channels` — decrypt once per request).
- R2 corrupt-ciphertext contract (backend): `InvalidToken`/missing-key → failed-
  validation 4xx, never 500.
- R6 (backend tests): stored-value-is-ciphertext for both callbacks; Bearer-header
  tests assert the decrypted token; corrupt-ciphertext → 4xx test; flip
  `test_intercom.py:199` to ciphertext + round-trip; any Slack callback test asserting
  raw storage updated the same way.

## Out of scope

- Worker read sites (aspect `worker-decrypt-mirrors`).
- The migration (aspect `backfill-migration`).
- Any change to OAuth flow behavior or response shapes.

## Acceptance criteria

- `Integration.oauth_access_token` in DB after Slack/Intercom OAuth connect is Fernet
  ciphertext, and `decrypt_api_key(stored)` returns the original token.
- `test_slack_integration` and `list_slack_channels` still work, sending the decrypted
  token (regression: a test asserting the Bearer header is the raw token would have
  caught ciphertext-in-header).
- Corrupt ciphertext at a read site returns 4xx with an actionable message, never 500.
- Missing `LLM_ENCRYPTION_KEY` at a write site returns 422 with an actionable message.
- Backend suite green.

## Dependencies & sequencing

- Independent of the other three aspects in code, but the branch must not merge until
  `backfill-migration` + `worker-decrypt-mirrors` also land (single coherent deploy).

## Open questions / risks

- None beyond the PRD's R2 corrupt-ciphertext contract.
