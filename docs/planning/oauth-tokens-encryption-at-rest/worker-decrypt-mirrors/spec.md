# Spec — Worker decrypt mirrors (5 read sites + intercom_sync fix)

**Aspect:** `worker-decrypt-mirrors` · PRD: `oauth-tokens-encryption-at-rest`

## Problem slice

worker-service cannot import backend-api code (image ships only `worker-service/src` +
`analysis-engine/src/analyzer`), yet it reads `Integration.oauth_access_token` at 5
sites. Once the backend encrypts, the worker must decrypt with its own Fernet helper —
and its one existing attempt at a backend import (`intercom_sync.py:76-80`) is a
dead-import defect that must not be copied.

## In scope

- R3: module-local `_decrypt(token)` helper (inline `from cryptography.fernet import
  Fernet`, `os.environ["LLM_ENCRYPTION_KEY"]`; precedent `zendesk_sync.py:80`,
  `hubspot_sync.py:45`, `salesforce_sync.py:80`), missing key → `{"status": "error",
  "reason": "missing_encryption_key"}` + no retry (R6 contract of zendesk_sync).
- R2 (worker half): decrypt exactly once at `alerts.py:445`, `source_events.py:314`
  (Slack + Intercom), `anomaly.py:270`, `notification_dispatch.py:104`, `:701`.
  Truthiness guards at `alerts.py:356,417` and `anomaly.py:268` /
  `notification_dispatch.py:102,699` stay as-is.
  > **Note (2026-08-18, `worker-cleanup-smalls`):** `anomaly.py:270` and its guard no
  > longer exist — the anomaly Slack sender was dead code and was deleted; the worker
  > read sites are now `alerts.py:445`, `source_events.py:314`, `notification_dispatch.py:104`, `:701`.
- R4: fix `intercom_sync.py:76-80` `_decrypt` to use the same local Fernet helper
  instead of `from src.utils.encryption import decrypt_api_key`; pin with a test that
  calls it **without** monkeypatching `_decrypt`.
- R2 corrupt-ciphertext contract (worker): `InvalidToken`/missing key → `error` dict,
  no retry (non-transient), no task crash.
- R8: extend the existing cross-service import sweep-guard (if any) to fail on
  backend-only imports in worker-service (`src.utils`, `src.api`, `src.services`),
  covering the module-level import shape used by `intercom_sync._decrypt`; if no
  sweep-guard exists, add one (the "wired at one end, dead at the other" family guard).
- R6 (worker tests): each of the 5 send sites passes the decrypted token (Bearer-header
  assertions); missing-key and corrupt-ciphertext return the `error` dict without
  retrying; `intercom_sync._decrypt` round-trips a Fernet token without monkeypatching.

## Out of scope

- Backend write/read sites (aspect `backend-encrypt-decrypt`).
- The migration (aspect `backfill-migration`).
- `intercom-pull-replies-and-ratings` and other Intercom v2 items (separate cards).

## Acceptance criteria

- All 5 worker read sites send the decrypted token; ciphertext never reaches a Bearer
  header (regression-tested at each site).
- Missing key / corrupt ciphertext at any site produces the `error` dict and does not
  crash the Celery task or retry.
- `intercom_sync._decrypt` works in the worker image's import universe (test does not
  monkeypatch it).
- Worker suite green.

## Dependencies & sequencing

- Code-independent of the backend aspect, but must ship in the same branch/commit set
  (a merged migration without the worker decrypt breaks every Slack OAuth alert).
- R8 sweep-guard may touch backend-api tests too (imports sweep across services).

## Open questions / risks

- None beyond the PRD's R2 corrupt-ciphertext contract and the R8 sweep shape.
