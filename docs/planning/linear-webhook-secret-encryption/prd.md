# PRD — Encrypt Linear webhook secret at rest

**Slug:** `linear-webhook-secret-encryption`
**Type:** security bug fix (freeform card — no GitHub issue)
**Branch:** `bug/linear-webhook-secret-plaintext`
**Source:** `docs/planning/_card/card.md` + `docs/planning/_card/understanding.md`
**Template:** Lightweight Brief (single-service change; one engineer can hold it)

---

## Problem Statement

Linear's `webhook_secret` — the HMAC key that authenticates inbound Linear webhook
deliveries — is stored in plaintext in the database on every self-hosted install.

- **For whom:** every Rereflect operator with Linear connected. Anyone with read access to
  the `linear_integrations` table (a DB dump, a compromised backup, a curious operator
  shelling into the container) can forge Linear webhook deliveries — issue status changes
  that alter `workflow_status`, assignee/priority sync, and the timeline — because the
  secret that must prove authenticity is stored unencrypted beside the data it protects.
- **Evidence it's real (observed in code, 2026-08-09):**
  - `services/backend-api/src/models/linear_integration.py:19` — `webhook_secret =
    Column(String(255), nullable=False)`; no encryption, no encryption comment (contrast
    `access_token` at :13 which is Fernet-encrypted).
  - `services/backend-api/src/api/routes/linear_integration.py:394-435` — generated with
    `secrets.token_urlsafe(32)` and written raw at :423/:435; **zero** calls to
    `encrypt_api_key`/`decrypt_api_key` in the file (grep-verified).
  - `services/backend-api/src/api/routes/linear_webhook.py:68-69` — verification reads the
    stored value straight into `_verify_linear_signature` (:33-54) with no decryption.
  - Every other integration encrypts at rest (Zendesk, Jira, Asana, HubSpot, Salesforce
    tokens; Slack/Intercom OAuth tokens since PR #10, `737bbd5`) — Linear is the sole
    exception (DEV-TRACKING.md:427-429).

## Goals & Success Metrics

| Goal | How it's measured |
|---|---|
| No plaintext Linear credentials in the DB | Migration test asserts every existing plaintext row is encrypted in place; new rows never written plaintext |
| Verification still works | Full existing `test_linear_webhook.py` suite passes against ciphertext fixtures (HMAC semantics unchanged) |
| Fail-closed on key absence | Missing `LLM_ENCRYPTION_KEY` at migration → migration aborts with instructions (mirror `c7d8e9f0a1b2`); at callback → HTTP 422; at verify → no-match 401 (mirror Jira) |
| No double-decrypt, no plaintext leakage | Read-site audit: decrypt exactly once, at the single verify site |
| Guardrail persists | Sweep-guard test fails if any integration model/route stores a plaintext credential again |

## User Personas & Scenarios

- **Self-hosted operator with Linear connected:** connects via OAuth today; the fix is
  invisible — reconnecting or a running instance just works, with the secret encrypted.
- **Operator upgrading an existing install:** `alembic upgrade head` encrypts the existing
  row in place; the webhook keeps verifying without reconnection.
- **Attacker/credential exposure scenario:** a DB read no longer yields a forgeable secret.

## Requirements

### Must-have

1. **Encrypt on write** (`routes/linear_integration.py`): the OAuth-callback path stores
   `encrypt_api_key(webhook_secret)` at both write sites (:423 update, :435 create).
   The plaintext value is still handed to Linear's `create_webhook` API (:402) — encryption
   happens after that call, before persistence. Missing key → HTTP **422** with a clear
   message (mirror `integrations.py:909-915`).
2. **Decrypt on read, exactly once** (`routes/linear_webhook.py:57-72`): in
   `_find_integration_by_secret`, decrypt each candidate secret inside try/except
   (`InvalidToken`/`ValueError` → log + continue, no-match → 401) — the Jira shape
   (`jira_webhook.py:84-106`). **No fallback to treating a stored value as plaintext** —
   after the fix the DB contract is "always ciphertext".
3. **Backfill migration** (`alembic/versions/*.py`): encrypts existing plaintext
   `linear_integrations.webhook_secret` rows in place; fail-closed `RuntimeError` with
   generate-a-key instructions when `LLM_ENCRYPTION_KEY` is unset; skips rows already
   prefixed `gAAAAA` (idempotent); chained to current sole head `c7d8e9f0a1b2`;
   best-effort downgrade. No schema change (Fernet ciphertext for a 32-char secret
   ≈ 140 chars, fits `String(255)`).
4. **Tests (RED-first):**
   - Stored value is ciphertext, not the raw secret; decrypt round-trips.
   - Verify path accepts ciphertext-stored secrets (update existing fixtures to store
     `encrypt_api_key(secret)` with `TEST_FERNET_KEY` + `patch.dict`, the repo's pattern —
     `test_integrations.py:18,789-806`).
   - Callback with missing key → 422; verify with undecryptable/corrupt secret → 401.
   - Migration contract tests (mirror `tests/test_oauth_token_backfill_migration.py`):
     plaintext row encrypted + round-trips; already-Fernet row unchanged; NULL/empty
     untouched; missing key raises and leaves rows untouched; downgrade best-effort.
   - Sweep-guard: no integration stores plaintext credentials (see Should-have).
5. **DEV-TRACKING.md**: mark the `linear-webhook-secret-plaintext` follow-up entry FIXED
   in the shipping commit (roadmap-hygiene rule, DEV-TRACKING.md:497).

### Should-have

6. **Sweep-guard test** mirroring `test_webhook_verifiers_fail_closed.py` /
   `test_worker_import_sweep.py`: AST/source-level assertion that no integration route
   stores a webhook secret / credential without the encrypt helper (backend-only scope).

### Nice-to-have

7. Correct the `models/linear_integration.py:19` column comment to state Fernet-at-rest
   (there is currently no comment to correct — add one documenting the invariant).

## Technical Considerations

- **Services changed:** `services/backend-api` only (routes + model comment + alembic).
  No worker changes (worker has zero Linear code — grep-verified), no frontend changes.
- **Helpers:** `src/utils/encryption.py` `encrypt_api_key`/`decrypt_api_key` (Fernet,
  key = `LLM_ENCRYPTION_KEY` env var, lazy `ValueError` when unset).
- **Patterns mirrored:** encrypt-on-write + 422 (`integrations.py:909-915`),
  decrypt-once-in-`_find_integration_by_secret` + corrupt→no-match (`jira_webhook.py:84-106`),
  backfill (`c7d8e9f0a1b2` migration + its test file).
- **Multi-tenancy:** unaffected — verification iterates active integrations org-scoped by
  row, unchanged.
- **Migration constraint:** online-only, no dependency on app code beyond what Alembic
  imports safely; single alembic head preserved (CI asserts).
- **Test environment:** `LLM_ENCRYPTION_KEY` is not in conftest — set per-test with
  `patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY})`, `TEST_FERNET_KEY`
  defined per test file (`test_integrations.py:18`).

## Risks & Open Questions

- **Fixture drift (risk):** the three Linear test files store raw secrets
  (`test_linear_webhook.py:140`, `test_linear_oauth.py:67,460`,
  `test_linear_integration_rbac.py:57`). If any are missed, a plaintext-only path can pass
  tests while production stores ciphertext — the exact defect class this card fixes.
  Mitigation: every fixture that represents DB state after the fix stores ciphertext.
- **Disconnect leaves a stale secret (observed, not changed):** the disconnect path does
  not null `webhook_secret`; the backfill encrypts the stale value too — harmless, out of
  scope to change.
- **No rotate-secret endpoint (observed):** re-running OAuth connect overwrites the
  secret. Out of scope.
- **Open question — none.** All decisions are settled by repo convention (column width,
  fixture handling, missing-key codes, disconnect behavior). Flagged for review, not
  blocking.

## Out of Scope

- `slack-email-signature-enforcement` (shadow-verifier flip) — separate card
  (DEV-TRACKING.md:423-426).
- `oauth-state-in-process-dict` (OAuth state in a process-local dict) — separate card
  (DEV-TRACKING.md:571-576).
- Linear UI changes, rotate-secret endpoint, disconnect-clears-secret behavior.
- Worker-service changes; frontend changes; schema changes.

## Non-Functional Requirements

- **Security:** fail-closed everywhere; no plaintext logging; no plaintext in migration
  output; decrypt exactly once per read.
- **Compatibility:** existing installs upgrade via `alembic upgrade head` with no
  reconnection; HMAC verification semantics byte-identical for valid deliveries.
- **Testability:** full backend suite green (`pytest tests/ -v`), single alembic head.
