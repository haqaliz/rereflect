# Spec — Docs & tracking

**Aspect:** `docs-and-tracking` · PRD: `oauth-tokens-encryption-at-rest`

## Problem slice

The roadmap-hygiene rule (DEV-TRACKING.md:497: "When closing work, correct the marker
in the same commit") and the decision-confirmed hard-abort behavior need operator-facing
documentation. All non-code artifacts for this fix.

## In scope

- R7a: `docs/SELF_HOSTING.md` — fail-closed upgrade callout: `alembic upgrade head`
  aborts when `LLM_ENCRYPTION_KEY` is unset; exact error text, remedy (generate a
  Fernet key, set the env var, re-run), and the note that installs upgrading from a
  version with plaintext tokens get them encrypted in place. Place it next to the
  existing integration/encryption docs.
- R7b: DEV-TRACKING P1 `oauth-tokens-stored-plaintext` (`DEV-TRACKING.md:500-518`)
  marked **FIXED** with the merge commit, the shipped summary (write/read encrypt-
  decrypt, worker mirrors, migration, intercom_sync fix), and any scope-guard notes.
- R7c: CHANGELOG entry (repo root `CHANGELOG.md`, conventional-commit style).
- R7d: DEV-TRACKING follow-up note for anything discovered but deliberately not bundled
  (`intercom-oauth-path-retirement` R9 note, if the dig confirmed nothing else).
- The docs commit lands in the same branch as the fix commits (single PR).

## Out of scope

- Any code changes (all other aspects).
- Updating the model comment at `models/integration.py:19-25` — already correct, must
  remain as-is unless the fix changes what it says (it does not).

## Acceptance criteria

- `SELF_HOSTING.md` documents the abort behavior with the exact error and remedy.
- DEV-TRACKING P1 entry reads FIXED with the merge commit, no stale unchecked boxes
  left open for this item.
- CHANGELOG entry present, matching the branch's commits.

## Dependencies & sequencing

- Last aspect: write it after the code aspects land, quoting the actual merge commit
  and exact error message from the migration.

## Open questions / risks

- None.
