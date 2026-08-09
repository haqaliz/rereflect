# Spec — Backfill migration

**Aspect:** `backfill-migration` · PRD: `oauth-tokens-encryption-at-rest`

## Problem slice

Existing plaintext `oauth_access_token` rows in the `integrations` table must be
encrypted in place when this fix deploys, with a fail-closed behavior for installs
missing `LLM_ENCRYPTION_KEY`.

## In scope

- R5: new Alembic revision chained `down_revision = "a9b8c7d6e5f4"` (current single
  head; CI asserts exactly one head), no trailing comment on `down_revision` (false-
  fork trap, `d5e6f7a8b9c0:24`).
- Reads `LLM_ENCRYPTION_KEY` via `os.environ` at migration time; **hard abort**
  (`RuntimeError`, operator-actionable message) when unset — never the
  `h1i2j3k4l5m6:148` "store as-is" fallback. Decision confirmed 2026-08-09.
- Inline `from cryptography.fernet import Fernet`; **no `src.` imports** (repo
  convention: zero across 93 migrations).
- Per-row transform: `SELECT id, oauth_access_token FROM integrations WHERE
  oauth_access_token IS NOT NULL AND oauth_access_token != ''` → encrypt → `UPDATE`
  (`n3o4p5q6r7s8:27-32` shape).
- Idempotency: skip rows already Fernet-encrypted (`gAAAAA` prefix check) so rows
  written by the fixed runtime are never double-encrypted.
- `downgrade()`: best-effort decrypt back to plaintext (`except Exception: pass`,
  `h1i2j3k4l5m6:194-224` precedent).
- Online-only (no `--sql` support), consistent with every repo backfill.
- R6 (migration tests): seeded plaintext row → ciphertext after `upgrade`; already-
  encrypted row skipped (no double-encrypt); missing key (patched env) → raises;
  `downgrade` round-trips.

## Out of scope

- Runtime encrypt/decrypt (aspects `backend-encrypt-decrypt`,
  `worker-decrypt-mirrors`).
- `oauth_refresh_token` / `oauth_expires_at` (dead columns) and Linear's
  `webhook_secret` (separate card `linear-webhook-secret-plaintext`).

## Acceptance criteria

- `alembic upgrade head` on a DB with seeded plaintext rows yields ciphertext rows that
  decrypt to the originals.
- Rows already ciphertext (post-fix runtime writes) are untouched.
- Unset `LLM_ENCRYPTION_KEY` → migration raises with a message naming the env var and
  the remedy; nothing is left half-encrypted.
- `alembic heads` still prints exactly one head; `downgrade` restores plaintext.
- CI's clean-DB migration run passes (zero rows, fast path).

## Dependencies & sequencing

- Must ship in the same commit/branch as the runtime fix (R5 note in PRD).
- `alembic heads` verified live before authoring (house convention).

## Open questions / risks

- Offline mode (`--sql`) cannot run this migration — accepted, documented in the
  docstring.
- Dev `docker-compose.yml` does not inject `LLM_ENCRYPTION_KEY`; local dev runs of this
  migration abort unless the var is exported — acceptable, noted in `SELF_HOSTING.md`
  callout (aspect `docs-and-tracking`).
