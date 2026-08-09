# Card — `oauth-tokens-stored-plaintext`

**Type:** bug (freeform — no GitHub issue)
**Branch:** `bug/oauth-tokens-stored-plaintext`
**Worktree:** `.claude/worktrees/bug-oauth-tokens-stored-plaintext`
**Opened:** 2026-08-09
**Traces to:** DEV-TRACKING P1 (`DEV-TRACKING.md:500-518`) — Post-1.0.0 User Feedback Backlog
**Picked by:** `rereflect-next` — highest-severity remaining item in the repo's own
highest-priority queue (DEV-TRACKING.md:39-41 says pick here before older roadmap sections).

## The problem

`Integration.oauth_access_token` is a plain `Text` column and
`services/backend-api/src/api/routes/integrations.py` never calls
`encrypt_api_key`/`decrypt_api_key` on the **Slack or Intercom OAuth paths** — while
every newer BYOK integration (Zendesk, Jira, Asana, HubSpot, Salesforce) does encrypt
(DEV-TRACKING.md:509-513). OAuth was simply never migrated when the encryption pattern
was introduced. Live Slack/Intercom tokens are stored in plaintext at rest on every
self-hosted install.

`services/backend-api/src/models/integration.py:19` carries the comment "OAuth tokens
(encrypted at application level before storage)" — **which is false**. A reader auditing
this file is actively misled into believing it is handled. The comment must be corrected
in the same commit as the fix (DEV-TRACKING.md:514-517).

The encryption fix needs a **backfill migration** for existing rows and was deliberately
kept out of `feat/integration-auth-tenancy-hardening` so a P0 wasn't held up behind a
data migration (DEV-TRACKING.md:501-503). It is the designated next card.

## The fix (minimal slice)

- Route the **Slack and Intercom OAuth connect/callback paths** in `routes/integrations.py`
  through the existing Fernet `encrypt_api_key`/`decrypt_api_key` helpers (the same
  pattern Zendesk/Jira/Asana/HubSpot/Salesforce already use) — encrypt on write, decrypt
  on read at the use site.
- **Alembic backfill migration** that encrypts existing plaintext rows in place. Must fail
  loudly (not silently leave rows plaintext) if the Fernet key is absent at migration time.
- Correct the false comment at `models/integration.py:19`.
- Pin with tests: stored value is ciphertext (not the raw token), round-trips through
  decrypt, existing plaintext rows migrate.

## Scope guards (from DEV-TRACKING + the card, do not expand)

- **This is a bug fix — no UI changes, no behavior changes** to the OAuth flows themselves.
- **Do not** bundle the sibling P1 `oauth-state-in-process-dict` (DEV-TRACKING.md:546-551)
  into this card; if the dig shows it's trivial to ride along, note it but keep this branch
  scoped to encryption-at-rest.
- **Do not** bundle the follow-up `linear-webhook-secret-plaintext` (the Linear webhook
  secret unencrypted) unless the dig shows the same migration can cover both cleanly —
  note it, keep the branch scoped.
- The migration must not depend on application code at upgrade time beyond what Alembic
  can import safely (follow the repo's existing migration conventions).
- Token read sites (`oauth_access_token` consumers) must be audited so decrypting happens
  exactly once, at the call site, with no double-decrypt.

## Related context

- Prior art — the encryption helpers: `encrypt_api_key`/`decrypt_api_key` usage in the
  Zendesk/Jira/Asana/HubSpot/Salesforce routes (Fernet, key from env).
- Prior art — backfill migrations in this repo: e.g. `public_id` backfill
  (`n3o4p5q6r7s8`), churn probability columns (`6e4501930bf0`) — see
  `services/backend-api/alembic/versions/`.
- Roadmap hygiene rule (DEV-TRACKING.md:497): "When closing work, correct the marker in
  the same commit" — the DEV-TRACKING P1 entry must be marked FIXED on the branch that
  ships the fix.
- False-comment class: the same "confident lie in the codebase" family as the P0/P0b
  dead-import bugs — a comment that asserts a security property that does not hold is
  worse than no comment.
