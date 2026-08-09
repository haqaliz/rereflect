# PRD — OAuth tokens encryption at rest

**Slug:** `oauth-tokens-encryption-at-rest`
**Branch:** `bug/oauth-tokens-stored-plaintext`
**Type:** bug (freeform — no GitHub issue)
**Date:** 2026-08-09
**Card:** `docs/planning/_card/card.md` · **Understanding:** `docs/planning/_card/understanding.md`
**Traces to:** DEV-TRACKING P1 `oauth-tokens-stored-plaintext` (`DEV-TRACKING.md:500-518`)

---

## Problem Statement

Slack and Intercom OAuth flows in `services/backend-api/src/api/routes/integrations.py`
store the provider access token **in plaintext** in the generic `integrations` table
(`Integration.oauth_access_token`, plain `Text` column). Every newer BYOK integration
(Zendesk, Jira, Asana, HubSpot, Salesforce) encrypts at rest with Fernet
(`encrypt_api_key`/`decrypt_api_key` in `src/utils/encryption.py`, key from
`LLM_ENCRYPTION_KEY`); the OAuth paths were never migrated onto that pattern —
`slack_oauth_callback` (`integrations.py:912`) carries a literal
`# In production, encrypt this!` comment.

**For whom:** every self-hosting operator of Rereflect — MIT, BYOK, no-telemetry is the
product's hook (four of seven post-1.0.0 user comments named privacy/self-hosting/BYOK
as the reason they chose it, DEV-TRACKING.md:570-580).

**Cost of the status quo:** on any install, a live Slack token (full write access to the
workspace's channels) or Intercom token sits in plaintext in the DB. A compromised DB
backup, a logs dump, or a careless export hands over a working credential. This is the
class of gap that would poison the product's trust positioning — and the repo's own
model comment already admitted it ("stored in PLAINTEXT… Do not restore the old comment
without doing the encryption", `models/integration.py:19-25`).

**Verified, not inferred:** write sites `integrations.py:912` and `:1089` store raw
tokens; no `encrypt_api_key` call exists for Slack or the Intercom OAuth path anywhere
in the backend.

## Goals & Success Metrics

**Goal:** Slack and Intercom OAuth tokens are encrypted at rest with the same Fernet
mechanism every other integration uses, with zero behavior change to the OAuth flows.

| # | Success (testable) | Measure |
|---|---|---|
| G1 | A stored Slack/Intercom token is ciphertext, never the raw token | Stored value ≠ raw token; `decrypt_api_key` round-trips to the raw token |
| G2 | All 8 existing read sites still work, sending the **decrypted** token | Bearer-header tests assert the decrypted token, not ciphertext (regression test for the truthiness trap) |
| G3 | Existing plaintext rows are encrypted in place | Backfill migration test: seeded plaintext row → ciphertext after `upgrade` |
| G4 | No double-encryption, no corruption | Migration skips already-Fernet rows (`gAAAAA` prefix); decrypt round-trip stable |
| G5 | Missing `LLM_ENCRYPTION_KEY` fails loud, never silently leaves plaintext | Migration raises `RuntimeError` with an actionable message; worker read sites return the `missing_encryption_key` error contract |
| G6 | The known-broken sibling import is no longer shipped | `intercom_sync.py` uses the local worker `_decrypt` mirror; a test asserts it without monkeypatching `_decrypt` |

Non-goals for metrics: adoption numbers (single-tenant OSS; we don't collect them).

## User Personas & Scenarios

- **Self-hosting operator (primary).** Runs Rereflect on their own infra with their own
  keys. Their DB is their responsibility; a plaintext Slack token at rest is an
  unacceptable default. After this fix they get the same at-rest protection the newer
  integrations already have, with no setup change (they already set
  `LLM_ENCRYPTION_KEY` to use integration tokens) — and a loud, clear upgrade error if
  they somehow never set it.
- **Operator who never set `LLM_ENCRYPTION_KEY`.** Today the app works fine without it
  (only integration saves return 422). After this fix, `alembic upgrade head` aborts
  with an operator-actionable message until they set it. This is the intended,
  decision-confirmed behavior (hard abort, 2026-08-09) — documented in
  `docs/SELF_HOSTING.md`.
- **Maintainer/auditor.** `models/integration.py` already carries the corrective
  comment; after this fix the comment's promise and the code agree.

## Requirements

### Must-have

- **R1 — Encrypt on write.** `slack_oauth_callback` (`integrations.py:912`) and
  `intercom_oauth_callback` (`integrations.py:1089`) store
  `encrypt_api_key(access_token)` instead of the raw token. Missing
  `LLM_ENCRYPTION_KEY` at write time → HTTP 422 with an actionable message, mirroring
  the Zendesk/Jira/Asana/HubSpot/Salesforce routes' `try/except ValueError` pattern.
- **R2 — Decrypt on read, exactly once.** All 8 read sites pass the **decrypted** token
  to the downstream sender:
  - backend: `integrations.py:683` (`test_slack_integration`),
    `feedback_sources.py:621`+`:637` (`list_slack_channels` — decrypt once, use for
    both the guard semantics and the Bearer header);
  - worker: `alerts.py:445` (`send_slack_alert`), `source_events.py:314`
    (Slack + Intercom `fetch_context`), `anomaly.py:270`, `notification_dispatch.py:104`
    and `:701`.
  Truthiness guards (`if not integration.oauth_access_token`) stay as-is — ciphertext is
  truthy, so they keep working; decryption happens at the send site, never inside the
  send helpers (`send_slack_message_oauth`, `fetch_context`) and never as a model
  property (no stacking).
  **Corrupt-ciphertext contract (never a 500):** `decrypt_api_key` raises
  `cryptography.fernet.InvalidToken` on a value that cannot be decrypted (rotated
  `LLM_ENCRYPTION_KEY`, mismatched DB dump). Backend read sites catch it and return a
  failed-validation 4xx with an actionable message (mirroring the Zendesk helper's
  documented contract, `zendesk_integration.py:283-290`); worker read sites return the
  `{"status": "error", "reason": "..."}` dict with no retry (non-transient). Missing
  `LLM_ENCRYPTION_KEY` at read time follows the same non-500 shape on both sides.
- **R3 — Worker decryption uses a local Fernet mirror.** worker-service has no
  `src/utils/encryption.py` (its image ships only `worker-service/src` +
  `analysis-engine/src/analyzer`). Add the established module-local `_decrypt(token)`
  helper (inline `from cryptography.fernet import Fernet`, `os.environ[
  "LLM_ENCRYPTION_KEY"]`; precedent `zendesk_sync.py:80`, `hubspot_sync.py:45`,
  `salesforce_sync.py:80`) and use it at the 5 worker read sites. Missing key →
  `{"status": "error", "reason": "missing_encryption_key"}`, no retry (the R6 contract
  zendesk_sync already documents).
- **R4 — Fix the sibling dead import.** `worker-service/src/tasks/intercom_sync.py:76-80`
  `_decrypt` imports `from src.utils.encryption import decrypt_api_key` — a module that
  does not exist in the worker image (verified: no `utils/encryption.py` under
  worker-service). Same family as the P0/P0b dead-import bugs; masked because tests
  monkeypatch `_decrypt`. Point it at the same local Fernet mirror (decision confirmed
  2026-08-09) and pin with a test that calls it without monkeypatching.
- **R5 — Alembic backfill migration** (head `a9b8c7d6e5f4`, single head, CI-asserted):
  - chained `down_revision = "a9b8c7d6e5f4"`, no trailing comment (false-fork trap);
  - reads `LLM_ENCRYPTION_KEY` via `os.environ` at migration time; **hard abort**
    (`RuntimeError`, actionable message) when unset — never the
    `h1i2j3k4l5m6:148` "store as-is if no encryption key" fallback;
  - inline `from cryptography.fernet import Fernet`; **no `src.` imports** (repo
    convention: zero across 93 migrations);
  - per-row: `SELECT id, oauth_access_token FROM integrations WHERE
    oauth_access_token IS NOT NULL AND oauth_access_token != ''` → encrypt → `UPDATE`;
  - **idempotent:** skip rows already Fernet-encrypted (`gAAAAA` prefix or
    try-decrypt-and-skip), so rows written by the fixed runtime (post-deploy reconnects)
    are never double-encrypted;
  - `downgrade()`: best-effort decrypt back to plaintext (`except Exception: pass`
    per `h1i2j3k4l5m6:194-224` precedent);
  - offline mode (`--sql`) unsupported — all repo backfills are online-only.
- **R6 — Test pinning.** `test_intercom.py:199` flips from asserting the stored token
  equals `"xyztoken123"` to asserting ciphertext + decrypt round-trip. New tests cover:
  stored-value-is-ciphertext for both callbacks; decrypted token reaches the Bearer
  header at each read site (the regression that would have caught the truthiness trap);
  **missing-key and corrupt-ciphertext paths return the non-500 contract at a backend
  read site and the `error` dict at a worker read site**; migration encrypts seeded
  plaintext rows, skips already-encrypted rows, raises on missing key (patched env), and
  `downgrade` round-trips.
- **R7 — Docs + tracking in the same commit** (roadmap-hygiene rule,
  DEV-TRACKING.md:497): `docs/SELF_HOSTING.md` gets a fail-closed upgrade callout;
  DEV-TRACKING P1 `oauth-tokens-stored-plaintext` marked **FIXED** with the merge
  commit; CHANGELOG entry.

### Should-have

- **R8 — Sweep-guard test for the class.** A small test that enumerates worker-service
  imports and fails on any `from src.utils...` / `from src.api...` backend-only import
  (the "wired at one end, dead at the other" family). If one already exists, extend it
  to cover the module-level import shape used by `intercom_sync._decrypt`.

### Nice-to-have

- **R9 — `intercom-oauth-path-retirement` note.** The generic-table Intercom OAuth row
  (`integrations.py:1089`) is effectively write-only today (the dedicated
  `IntercomIntegration` token-paste path is the live one). Not changing it here; a
  DEV-TRACKING note can revisit retirement.

## Technical Considerations

- **Services changed:** backend-api (write + 3 backend read sites + migration),
  worker-service (5 read sites + local `_decrypt` + intercom_sync import fix). No
  frontend changes. No schema change (Fernet ciphertext fits the existing `Text`
  column).
- **Encryption mechanism:** `src/utils/encryption.py` — Fernet, `LLM_ENCRYPTION_KEY`
  env var, lazy per-call read (importing the module never fails without the key).
  Backend routes catch `ValueError` → HTTP 422 (existing pattern).
- **Worker constraint:** no shared Python package between backend and worker — the
  worker must carry its own Fernet helper (module-local `_decrypt`), byte-similar to
  the nine existing worker mirrors.
- **Migration availability of the key:** production Dockerfile runs
  `python -m alembic upgrade head` in-container before uvicorn with the
  compose-injected `LLM_ENCRYPTION_KEY`; CI sets a dummy key on a clean DB (zero rows →
  fast path). `alembic/env.py` does not `load_dotenv()` — local runs need the env var
  exported.
- **Multi-tenancy:** tokens are org-scoped rows in the `integrations` table; the fix
  touches no tenancy logic.
- **Deployment sequencing:** migration and runtime fix ship in the same commit/branch;
  the migration must be tolerant of rows written by the already-fixed runtime.

## Risks & Open Questions

| Risk | Mitigation |
|---|---|
| Truthiness trap: ciphertext passes `if not oauth_access_token` guards, so a missed read site silently sends ciphertext as Bearer → 401s | R2's exactly-once decrypt at each of the 8 verified read sites + R6 Bearer-header regression tests at each site |
| **Key rotation / restored DB dump makes stored ciphertext undecryptable** (`InvalidToken`) — same property every existing Fernet integration has | R2 corrupt-ciphertext contract: backend 4xx "failed validation" (never 500), worker `error` dict, no retry; accepted as a documented platform limitation (Zendesk precedent), no rotation-recovery mechanism invented in this card |
| Double-encrypt in the backfill (runtime already wrote ciphertext post-deploy) | R5 idempotency: skip rows already Fernet-encrypted |
| `alembic upgrade head` aborts for installs without `LLM_ENCRYPTION_KEY` | Decision-confirmed (hard abort, 2026-08-09); R7 callout in `SELF_HOSTING.md` with the exact error and remedy |
| Offline `--sql` migrations break on this backfill | R5 documents online-only (repo precedent) |
| Migration runs on a fresh DB where the `integrations` table does not exist | Non-risk, closed: the table is created in an early migration in the same chain, so it always exists at this point (no guarded-bind needed, unlike `hbsh5o3gbwv4`) |
| The worker's `_decrypt` copies drift from the backend's `decrypt_api_key` | Same key material + same Fernet format; byte-verified by round-trip tests in both services |

Open questions carried into planning: none unresolved at PRD level — the two
discretionary decisions (fail-closed behavior; intercom_sync fix) were confirmed with
the user on 2026-08-09.

## Out of Scope

- `oauth-refresh-token` / `oauth-expires-at` columns (dead for these providers; never
  written, zero read sites).
- `linear-webhook-secret-plaintext` (separate DEV-TRACKING item — same encryption
  family, different table; note, don't bundle).
- `oauth-state-in-process-dict` (P3 sibling — multi-replica OAuth state; separate card).
- Frontend changes; API contract changes (no new endpoints, no response shape changes —
  `IntegrationResponse` already whitelists fields and never exposes the token).
- Retiring the legacy Intercom OAuth path (`R9` note only).
- Any change to the OAuth flows' behavior itself.
